"""Preflight for the Kaggle transcription path.

``python -m resolve_subtitle_tool.check_kaggle`` answers the two questions that
actually stop a run: are credentials installed, and does this account get a GPU
with internet? The first is a local file check plus an authenticated API call.
The second cannot be read from any endpoint — Kaggle exposes no "am I phone
verified" field — so ``--full`` pushes a tiny script kernel that reports what it
was given. It costs about a minute of quota and settles the question for real.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from . import config
from .kaggle_runner import (
    KaggleRunError,
    _api,
    _status_error,
    _status_name,
    detect_username,
)

SMOKE_SOURCE = '''\
import json, socket, subprocess, sys
info = {"python": sys.version.split()[0]}
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True, timeout=60)
    info["gpu"] = out.stdout.strip() or out.stderr.strip() or "none"
except Exception as exc:
    info["gpu"] = f"unavailable: {exc}"
try:
    socket.create_connection(("pypi.org", 443), timeout=15).close()
    info["internet"] = "yes"
except Exception as exc:
    info["internet"] = f"no: {exc}"
print(json.dumps(info))
open("/kaggle/working/smoke.json", "w").write(json.dumps(info))
'''


def _line(ok: bool | None, label: str, detail: str = "") -> None:
    mark = {True: "  ok  ", False: " FAIL ", None: "  ??  "}[ok]
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))


def check_credentials() -> bool:
    status = config.kaggle_status()
    found = bool(status.get("configured"))
    where = []
    if status.get("has_env_token"):
        where.append("KAGGLE_API_TOKEN env var")
    if status.get("has_token_file"):
        where.append(str(config.kaggle_dir() / "access_token"))
    if status.get("has_kaggle_json"):
        where.append(str(config.kaggle_dir() / "kaggle.json"))
    _line(found, "Credentials on disk", ", ".join(where) or "nothing found")
    if not found:
        print(
            "\n       Easiest — log in through the browser:\n"
            "         kaggle auth login\n\n"
            "       Or create a token at https://www.kaggle.com/settings (API section)\n"
            "       and save it in the app's Settings tab, or by hand:\n"
            "         mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/\n"
            "         chmod 600 ~/.kaggle/kaggle.json\n"
        )
    return found


def check_auth() -> tuple[bool, object | None]:
    try:
        api = _api()
    except KaggleRunError as exc:
        _line(False, "Authentication", str(exc).split("Original error:")[-1].strip())
        return False, None
    user = detect_username() or "(username not reported)"
    _line(True, "Authentication", f"signed in as {user}")
    return True, api


def check_api(api) -> bool:
    try:
        api.kernels_list(mine=True, page_size=1)
    except Exception as exc:
        _line(False, "API reachable", str(exc)[:200])
        return False
    _line(True, "API reachable", "kernel listing responded")
    return True


def check_gpu_and_internet(api, timeout: float = 900.0) -> bool:
    """Push a throwaway kernel that reports its own hardware and connectivity."""
    user = detect_username()
    if not user:
        _line(None, "GPU + internet", "cannot determine username; skipping")
        return False
    slug = "resolve-subs-preflight"
    ref = f"{user}/{slug}"
    print(f"\nPushing preflight kernel {ref} (GPU + internet requested)…")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "preflight.py").write_text(SMOKE_SOURCE, encoding="utf-8")
        (folder / "kernel-metadata.json").write_text(
            json.dumps(
                {
                    "id": ref,
                    "title": slug,
                    "code_file": "preflight.py",
                    "language": "python",
                    "kernel_type": "script",
                    "is_private": True,
                    "enable_gpu": True,
                    "enable_internet": True,
                    "dataset_sources": [],
                    "competition_sources": [],
                    "kernel_sources": [],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        try:
            api.kernels_push(str(folder))
        except Exception as exc:
            _line(False, "Kernel push", str(exc)[:300])
            return False

        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            time.sleep(10)
            try:
                status = api.kernels_status(ref)
            except Exception as exc:
                _line(False, "Kernel status", str(exc)[:200])
                return False
            name = _status_name(status)
            if name != last:
                print(f"    status: {name}")
                last = name
            if name in {"complete"}:
                break
            if name in {"error", "cancelacknowledged", "cancelrequested"}:
                _line(False, "Preflight kernel", _status_error(status) or name)
                return False
        else:
            _line(False, "Preflight kernel", "timed out waiting for the run")
            return False

        with tempfile.TemporaryDirectory() as out:
            try:
                api.kernels_output(ref, path=out)
            except Exception as exc:
                _line(False, "Kernel output", str(exc)[:200])
                return False
            smoke = Path(out) / "smoke.json"
            if not smoke.is_file():
                _line(False, "Preflight result", "smoke.json missing from output")
                return False
            info = json.loads(smoke.read_text(encoding="utf-8"))

    gpu = str(info.get("gpu", ""))
    net = str(info.get("internet", ""))
    gpu_ok = bool(gpu) and "unavailable" not in gpu and gpu != "none"
    net_ok = net == "yes"
    _line(gpu_ok, "GPU allocated", gpu or "none")
    _line(net_ok, "Internet in kernel", net)
    if not (gpu_ok and net_ok):
        print(
            "\n       Both need a phone-verified Kaggle account:\n"
            "       https://www.kaggle.com/settings → Phone Verification\n"
        )
    print(f"\n       Delete the preflight kernel any time: https://www.kaggle.com/{ref}")
    return gpu_ok and net_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="also run a throwaway kernel to prove GPU and internet are granted",
    )
    args = parser.parse_args(argv)

    print("Kaggle preflight\n")
    if not check_credentials():
        return 1
    ok, api = check_auth()
    if not ok:
        return 1
    if not check_api(api):
        return 1
    if args.full:
        if not check_gpu_and_internet(api):
            return 1
    else:
        _line(
            None,
            "GPU + internet",
            "not checked; re-run with --full to prove it (~1 min of quota)",
        )
    print("\nReady." if args.full else "\nCredentials look good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
