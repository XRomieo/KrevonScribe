"""Persisted user settings and Kaggle credential handling.

Settings live in the platform's standard per-user config directory so the
portable Windows build keeps its settings next to the user's profile rather than
beside the executable.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

APP_NAME = "Krevon Scribe"
# The name the app shipped under before it was branded. Settings saved by those
# builds are still read, so an upgrade does not silently lose a user's Kaggle
# username and output folders.
LEGACY_APP_NAME = "ResolveSubtitleTool"


def _config_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_dir() -> Path:
    """Per-user configuration directory for this app."""
    return _config_root() / APP_NAME


def legacy_config_dir() -> Path:
    return _config_root() / LEGACY_APP_NAME


def default_output_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


CONFIG_PATH = config_dir() / "settings.json"
LEGACY_CONFIG_PATH = legacy_config_dir() / "settings.json"


@dataclass
class Settings:
    """User-editable settings. Every field must be JSON-serialisable."""

    audio_dir: str = ""
    srt_dir: str = ""

    # Fonts cannot be applied through the Resolve API (see
    # docs/RESOLVE_API_FINDINGS.md). They are stored so the UI can remind the
    # user which typeface to set by hand on each subtitle track.
    font_en: str = "Helvetica Neue"
    font_ar: str = "Geeza Pro" if sys.platform == "darwin" else "Dubai"

    kaggle_username: str = ""
    whisper_model: str = "large-v2"
    whisper_detect_model: str = "large-v3"
    # How the two languages are told apart. "model" transcribes once with a
    # checkpoint fine-tuned on code-switched Arabic/English, which writes each
    # word in the script it was spoken in; "confidence" runs stock whisper four
    # times and infers the language from decoder confidence. Measured against
    # hand-marked spans: 94.7% against 65-78%.
    code_switch_method: str = "model"
    code_switch_model: str = "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched"
    # "split" never lets one cue hold both scripts, at the cost of some
    # very short cues; "mixed" keeps a sentence whole when the speaker switches
    # language inside it.
    cue_script_policy: str = "split"
    # Language hint passed to whisper. "auto" lets it detect; for code-switched
    # Arabic/English audio an explicit hint usually helps.
    whisper_language: str = "auto"

    # Share of letters in a cue that must be Arabic for it to route to the
    # Arabic track. 0.5 = majority script wins; 0.0 = any Arabic at all.
    arabic_threshold: float = 0.5

    # Which language gets auto-placed on the timeline. Only one can be, because
    # every append lands on the subtitle track that already holds cues.
    primary_language: str = "en"
    single_track: bool = True
    # Re-time cue text against the audio with CTC forced alignment after
    # transcribing. Whisper infers its timestamps and they drift; the aligner
    # measures them. Costs about a minute of GPU time.
    forced_alignment: bool = True
    # Delete existing subtitle tracks before importing. Off by default because
    # it throws away work; without it a second run refuses to place anything,
    # since Resolve sends every import to the track that already holds cues.
    replace_existing_subtitles: bool = False
    # "speechmatics" (Melia 1: one pass, native code-switching, per-word language
    # tags) or "kaggle" (free whisper on a Kaggle GPU).
    backend: str = "kaggle"
    speechmatics_api_key: str = ""

    def __post_init__(self) -> None:
        if not self.audio_dir:
            self.audio_dir = str(default_output_dir() / "audio")
        if not self.srt_dir:
            self.srt_dir = str(default_output_dir() / "srt")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load() -> Settings:
    """Read settings, ignoring unknown or corrupt content rather than failing.

    Falls back to the pre-rename location so upgrading does not reset the app.
    The old file is left alone; the next save writes to the new path.
    """
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        known = {f.name for f in fields(Settings)}
        return Settings(**{k: v for k, v in raw.items() if k in known})
    return Settings()


def save(settings: Settings) -> Path:
    """Persist settings atomically so a crash mid-write cannot corrupt them."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return CONFIG_PATH


# --------------------------------------------------------------------------
# Kaggle credentials
# --------------------------------------------------------------------------

def kaggle_dir() -> Path:
    return Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))


def kaggle_status() -> dict[str, Any]:
    """Report which Kaggle credential sources are present.

    The kaggle 2.2.x client tries an access token first (``KAGGLE_API_TOKEN`` or
    ``~/.kaggle/access_token``) and falls back to the legacy
    ``~/.kaggle/kaggle.json`` username/key pair. Both remain supported.
    """
    d = kaggle_dir()
    token_file = d / "access_token"
    json_file = d / "kaggle.json"
    username = ""
    if json_file.exists():
        try:
            username = json.loads(json_file.read_text(encoding="utf-8")).get("username", "")
        except (json.JSONDecodeError, OSError):
            username = ""
    return {
        "config_dir": str(d),
        "has_env_token": bool(os.environ.get("KAGGLE_API_TOKEN")),
        "has_token_file": token_file.exists(),
        "has_kaggle_json": json_file.exists(),
        "username": username,
        "configured": bool(
            os.environ.get("KAGGLE_API_TOKEN") or token_file.exists() or json_file.exists()
        ),
    }


def write_kaggle_json(username: str, key: str) -> Path:
    """Write legacy ``~/.kaggle/kaggle.json`` with owner-only permissions."""
    username, key = username.strip(), key.strip()
    if not username or not key:
        raise ValueError("Kaggle username and key are both required")
    d = kaggle_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "kaggle.json"
    path.write_text(json.dumps({"username": username, "key": key}), encoding="utf-8")
    # The kaggle client warns loudly if this file is group/world readable.
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows filesystems may not support chmod; harmless there.
    return path


def write_access_token(token: str) -> Path:
    """Write the newer ``~/.kaggle/access_token`` credential file."""
    token = token.strip()
    if not token:
        raise ValueError("Kaggle API token is required")
    d = kaggle_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "access_token"
    path.write_text(token, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
