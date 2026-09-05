"""Drives a Kaggle GPU kernel to transcribe an audio file.

One run: upload/version a private dataset holding the audio, push a script
kernel that reads it, poll until the kernel finishes, download ``segments.json``.

Kaggle's own client prints to stdout and raises assorted exception types; this
module funnels everything into :class:`KaggleRunError` with a readable message.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

Progress = Callable[[str], None]

def _kernel_source() -> Path:
    """Locate transcribe_kernel.py from source or from a PyInstaller bundle."""
    candidates = [Path(__file__).parent / "kaggle_kernel" / "transcribe_kernel.py"]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(
            Path(bundle) / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


KERNEL_SOURCE = _kernel_source()

# Kaggle slugs: lowercase alphanumerics and hyphens, 6-50 characters.
_SLUG_RE = re.compile(r"[^a-z0-9-]+")

TERMINAL_OK = {"complete"}
TERMINAL_BAD = {"error", "cancelacknowledged", "cancelrequested"}


class KaggleRunError(RuntimeError):
    pass


def slugify(name: str, fallback: str = "resolve-subs") -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug) or fallback
    if len(slug) < 6:
        slug = f"{slug}-audio"[:50]
    return slug[:50].strip("-")


@dataclass
class RunResult:
    segments: list[dict]
    meta: dict
    kernel_ref: str
    dataset_ref: str
    output_dir: Path
    elapsed_seconds: float


def _api():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise KaggleRunError(
            "The 'kaggle' package is not installed. Run: pip install kaggle"
        ) from exc
    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as exc:
        raise KaggleRunError(
            "Kaggle authentication failed. Add credentials in Settings — either an "
            "API token (~/.kaggle/access_token) or a username/key pair "
            f"(~/.kaggle/kaggle.json). Original error: {exc}"
        ) from exc
    return api


def _status_name(status) -> str:
    """Normalise the several shapes kernels_status returns across versions."""
    if isinstance(status, dict):
        raw = status.get("status") or status.get("Status") or ""
    else:
        raw = getattr(status, "status", None) or getattr(status, "Status", "") or status
    name = getattr(raw, "name", None) or str(raw)
    return name.rsplit(".", 1)[-1].replace("_", "").lower()


def _status_error(status) -> str:
    if isinstance(status, dict):
        return status.get("failureMessage") or status.get("failure_message") or ""
    return getattr(status, "failure_message", "") or getattr(status, "failureMessage", "") or ""


def transcribe(
    audio_path: str | Path,
    username: str,
    *,
    model: str = "large-v2",
    detect_model: str = "large-v3",
    language: str = "auto",
    code_switch: bool = True,
    languages: Sequence[str] = ("en", "ar"),
    align: bool = True,
    code_switch_method: str = "model",
    cs_model: str = "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched",
    cue_script_policy: str = "split",
    slug: str | None = None,
    output_dir: str | Path | None = None,
    progress: Progress | None = None,
    poll_seconds: float = 15.0,
    timeout_seconds: float = 5400.0,
) -> RunResult:
    """Transcribe ``audio_path`` on Kaggle and return the parsed segments."""
    say = progress or (lambda _m: None)
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise KaggleRunError(f"Audio file not found: {audio_path}")
    username = username.strip()
    if not username:
        raise KaggleRunError("Your Kaggle username is required to name the dataset.")

    # Kaggle derives the real slug from the *title*, ignoring the id we send, so
    # title and id must agree exactly or later lookups 404. Reserve room for the
    # "-run" suffix up front rather than truncating the title afterwards.
    base = slug or slugify(f"resolve-subs-{audio_path.stem}")
    base = base[:46].strip("-")
    kernel_title = f"{base}-run"
    dataset_ref = f"{username}/{base}"
    kernel_ref = f"{username}/{kernel_title}"
    started = time.time()

    api = _api()
    staging = Path(tempfile.mkdtemp(prefix="resolve-subs-"))
    try:
        # ---- dataset: audio + job settings -------------------------------
        ds_dir = staging / "dataset"
        ds_dir.mkdir()
        say(f"Staging {audio_path.name} ({audio_path.stat().st_size / 1e6:.1f} MB)…")
        shutil.copy2(audio_path, ds_dir / audio_path.name)
        (ds_dir / "job.json").write_text(
            json.dumps(
                {
                    "model": model,
                    "detect_model": detect_model,
                    "language": language,
                    "code_switch": bool(code_switch),
                    "languages": list(languages),
                    "align": bool(align),
                    "code_switch_method": code_switch_method,
                    "cs_model": cs_model,
                    "cue_script_policy": cue_script_policy,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        (ds_dir / "dataset-metadata.json").write_text(
            json.dumps({"title": base, "id": dataset_ref,
                        "licenses": [{"name": "CC0-1.0"}]}, indent=1),
            encoding="utf-8",
        )

        exists = True
        try:
            api.dataset_status(dataset_ref)
        except Exception:
            exists = False

        say("Uploading audio to a private Kaggle dataset…")
        try:
            if exists:
                api.dataset_create_version(
                    str(ds_dir), version_notes=f"audio {int(started)}",
                    quiet=True, convert_to_csv=False, dir_mode="zip",
                )
            else:
                api.dataset_create_new(
                    str(ds_dir), public=False, quiet=True,
                    convert_to_csv=False, dir_mode="zip",
                )
        except Exception as exc:
            raise KaggleRunError(f"Uploading the dataset failed: {exc}") from exc

        _wait_for_dataset(api, dataset_ref, say, timeout_seconds=600)

        # ---- kernel ------------------------------------------------------
        k_dir = staging / "kernel"
        k_dir.mkdir()
        shutil.copy2(KERNEL_SOURCE, k_dir / "transcribe_kernel.py")
        (k_dir / "kernel-metadata.json").write_text(
            json.dumps({
                "id": kernel_ref,
                "title": kernel_title,
                "code_file": "transcribe_kernel.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": True,
                "enable_gpu": True,
                "enable_internet": True,
                "dataset_sources": [dataset_ref],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            }, indent=1),
            encoding="utf-8",
        )
        say("Pushing the GPU kernel…")
        try:
            api.kernels_push(str(k_dir))
        except Exception as exc:
            raise KaggleRunError(f"Pushing the kernel failed: {exc}") from exc

        # ---- poll --------------------------------------------------------
        say("Queued on Kaggle. This usually takes several minutes.")
        deadline = time.time() + timeout_seconds
        last = None
        while True:
            if time.time() > deadline:
                raise KaggleRunError(
                    f"Timed out after {timeout_seconds / 60:.0f} min. The kernel may "
                    f"still be running: https://www.kaggle.com/code/{kernel_ref}"
                )
            time.sleep(poll_seconds)
            try:
                status = api.kernels_status(kernel_ref)
            except Exception as exc:
                say(f"(status check failed, retrying: {exc})")
                continue
            name = _status_name(status)
            if name != last:
                say(f"Kernel status: {name}")
                last = name
            if name in TERMINAL_OK:
                break
            if name in TERMINAL_BAD:
                raise KaggleRunError(
                    f"The Kaggle kernel failed ({name}). "
                    f"{_status_error(status)} "
                    f"Logs: https://www.kaggle.com/code/{kernel_ref}"
                )

        # ---- download ----------------------------------------------------
        out_dir = Path(output_dir) if output_dir else staging / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        say("Downloading results…")
        try:
            api.kernels_output(kernel_ref, str(out_dir), force=True, quiet=True)
        except Exception as exc:
            raise KaggleRunError(f"Downloading kernel output failed: {exc}") from exc

        seg_file = _find(out_dir, "segments.json")
        if seg_file is None:
            raise KaggleRunError(
                "The kernel finished but produced no segments.json. Check the log at "
                f"https://www.kaggle.com/code/{kernel_ref}"
            )
        segments = json.loads(seg_file.read_text(encoding="utf-8"))
        meta_file = _find(out_dir, "meta.json")
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file else {}

        say(f"Transcribed {len(segments)} segments.")
        return RunResult(
            segments=segments, meta=meta, kernel_ref=kernel_ref,
            dataset_ref=dataset_ref, output_dir=out_dir,
            elapsed_seconds=round(time.time() - started, 1),
        )
    finally:
        # Keep the downloaded output if it lives under the staging dir.
        if output_dir is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _wait_for_dataset(api, ref: str, say: Progress, timeout_seconds: float) -> None:
    """Block until Kaggle finishes ingesting the uploaded dataset."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            status = str(api.dataset_status(ref) or "").lower()
        except Exception:
            status = ""
        if "ready" in status:
            say("Dataset ready.")
            return
        if "error" in status:
            raise KaggleRunError(f"Kaggle failed to process the dataset: {status}")
        time.sleep(5)
    say("Dataset still processing; continuing anyway.")


def _find(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.is_file():
        return direct
    return next((p for p in root.rglob(name) if p.is_file()), None)


def detect_username() -> str:
    """Ask Kaggle who the stored credentials belong to.

    A token-only setup has no username on disk, but the client introspects the
    token during ``authenticate()``, so the answer is available afterwards. Used
    to fill in the dataset owner without asking the user to retype it.
    """
    try:
        api = _api()
    except KaggleRunError:
        return ""
    for source in (getattr(api, "config_values", None) or {},):
        for key in ("username", "CONFIG_NAME_USER", "user"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(getattr(api, "username", "") or "").strip()
