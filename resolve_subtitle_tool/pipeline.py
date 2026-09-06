"""End-to-end run: an audio file -> transcription -> subtitle files on disk.

The output is plain SRT, which every editor reads. Krevon Scribe deliberately
does not drive an editor itself: doing that meant one vendor's scripting API,
one more thing to install, and a different failure on every machine. Dragging
the finished .srt onto a timeline is one gesture and works in Resolve, Premiere,
Final Cut, CapCut and anything else.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import kaggle_runner, speechmatics_runner, subtitle_utils
from .config import Settings

Progress = Callable[[str], None]

# How many cues travel back to the UI for the preview. Enough to scroll through
# and judge the result; a feature-length recording is not worth serialising whole.
PREVIEW_LIMIT = 400


@dataclass
class RunOutcome:
    audio_path: str
    # Both languages in time order, which is what one subtitle track wants.
    combined_srt: str
    # The same cues split by language, for anyone who wants a track each so the
    # two scripts can carry different fonts.
    en_srt: str
    ar_srt: str
    en_cues: int
    ar_cues: int
    combined_cues: int
    detected_language: str
    # The first cues themselves, so the UI can show what was actually written
    # rather than only how many. Each is {"start", "end", "text"}.
    preview: list[dict] = field(default_factory=list)
    preview_truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _stamp(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "audio"
    return f"{safe}_{_dt.datetime.now():%Y%m%d_%H%M%S}"


def run(
    settings: Settings,
    *,
    audio_file: str | None = None,
    progress: Progress | None = None,
) -> RunOutcome:
    """Transcribe ``audio_file`` and write the subtitle files."""
    say = progress or (lambda _m: None)
    warnings: list[str] = []

    # ---- 1. audio ---------------------------------------------------------
    if not audio_file:
        raise ValueError("Choose an audio file to transcribe.")
    audio = Path(audio_file)
    if not audio.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio}")
    base = _stamp(audio.stem)
    say(f"Using {audio.name}.")

    # ---- 2. transcribe ----------------------------------------------------
    if settings.backend == "speechmatics":
        result = speechmatics_runner.transcribe(
            audio,
            settings.speechmatics_api_key,
            languages=("en", "ar"),
            progress=say,
        )
        counts = result.meta.get("language_counts") or {}
        detected = "+".join(sorted(counts)) or "unknown"
        say(f"Melia tagged {len(result.segments)} cues: {counts}.")
    else:
        say("Sending to Kaggle…")
        result = kaggle_runner.transcribe(
            audio,
            username=settings.kaggle_username,
            model=settings.whisper_model,
            detect_model=settings.whisper_detect_model,
            language=settings.whisper_language,
            align=settings.forced_alignment,
            code_switch_method=settings.code_switch_method,
            cs_model=settings.code_switch_model,
            cue_script_policy=settings.cue_script_policy,
            output_dir=Path(settings.srt_dir) / "_kaggle" / base,
            progress=say,
        )
        detected = str(result.meta.get("detected_language", "") or "unknown")
        say(f"Whisper reported language '{detected}' over {len(result.segments)} segments.")

    # ---- 3. split + write -------------------------------------------------
    if not result.segments:
        raise RuntimeError("The transcription backend returned no usable cues.")
    english, arabic = subtitle_utils.split_tagged_segments(
        result.segments, settings.arabic_threshold
    )
    if not english and not arabic:
        raise RuntimeError("The transcription backend returned no usable cues.")
    say(f"Routed {len(english)} cues to English and {len(arabic)} to Arabic.")

    srt_dir = Path(settings.srt_dir)
    en_srt = subtitle_utils.write_srt(english, srt_dir / f"{base}.en.srt")
    ar_srt = subtitle_utils.write_srt(arabic, srt_dir / f"{base}.ar.srt")
    combined = subtitle_utils.merge_for_single_track(english, arabic)
    combined_srt = subtitle_utils.write_srt(combined, srt_dir / f"{base}.srt")
    say(f"Wrote {combined_srt.name} ({len(combined)} cues), plus the split files.")

    return RunOutcome(
        audio_path=str(audio), combined_srt=str(combined_srt),
        en_srt=str(en_srt), ar_srt=str(ar_srt),
        en_cues=len(english), ar_cues=len(arabic), combined_cues=len(combined),
        detected_language=detected,
        preview=[{"start": c.start, "end": c.end, "text": c.text}
                 for c in combined[:PREVIEW_LIMIT]],
        preview_truncated=len(combined) > PREVIEW_LIMIT,
        warnings=warnings,
    )
