"""End-to-end run: audio -> Kaggle transcription -> SRTs -> back into Resolve."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from . import kaggle_runner, resolve_bridge, speechmatics_runner, subtitle_utils
from .config import Settings

Progress = Callable[[str], None]


@dataclass
class RunOutcome:
    audio_path: str
    combined_srt: str
    en_srt: str
    ar_srt: str
    en_cues: int
    ar_cues: int
    combined_cues: int
    placed_language: str | None
    placed_cues: int
    manual_srt: str | None
    manual_track_index: int | None
    detected_language: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _stamp(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "timeline"
    return f"{safe}_{_dt.datetime.now():%Y%m%d_%H%M%S}"


def run(
    settings: Settings,
    *,
    audio_source: str = "timeline",
    track_indices: Sequence[int] = (),
    audio_file: str | None = None,
    import_to_resolve: bool = True,
    progress: Progress | None = None,
) -> RunOutcome:
    """Execute one full transcription run.

    ``audio_source`` is ``"timeline"`` (render the selected audio tracks out of
    Resolve) or ``"file"`` (use ``audio_file`` from disk).
    """
    say = progress or (lambda _m: None)
    warnings: list[str] = []

    # ---- 1. audio ---------------------------------------------------------
    if audio_source == "timeline":
        info = resolve_bridge.get_info()
        if not info.has_content:
            raise resolve_bridge.ResolveError("The open timeline is empty.")
        say(f"Timeline '{info.timeline}' at {info.fps:g} fps.")
        base = _stamp(f"{info.project}_{info.timeline}")
        audio = resolve_bridge.export_timeline_audio(
            track_indices or [t.index for t in info.audio_tracks],
            settings.audio_dir, base, progress=say,
        )
    else:
        if not audio_file:
            raise ValueError("Choose an audio file, or switch to timeline mode.")
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

    outcome = RunOutcome(
        audio_path=str(audio), combined_srt=str(combined_srt),
        en_srt=str(en_srt), ar_srt=str(ar_srt),
        en_cues=len(english), ar_cues=len(arabic), combined_cues=len(combined),
        placed_language=None, placed_cues=0,
        manual_srt=None, manual_track_index=None,
        detected_language=detected, warnings=warnings,
    )

    # ---- 4. back into Resolve --------------------------------------------
    if not import_to_resolve:
        return outcome
    if audio_source != "timeline":
        warnings.append(
            "Manual-file mode does not import into Resolve, because the cue times "
            "are relative to that file rather than to a timeline."
        )
        return outcome

    if settings.replace_existing_subtitles:
        try:
            resolve_bridge.clear_subtitle_tracks(progress=say)
        except resolve_bridge.ResolveError as exc:
            warnings.append(f"Could not clear the existing subtitle tracks: {exc}")
            say(f"! {exc}")

    if settings.single_track:
        # Resolve only ever displays one subtitle track, so both languages share
        # it. This is also the only arrangement it can populate automatically:
        # every append lands on the already-filled track, so a second track
        # would always need dragging by hand.
        if combined:
            try:
                placed = resolve_bridge.place_srt_on_timeline(
                    combined_srt, "Subtitles", progress=say
                )
                outcome.placed_language, outcome.placed_cues = "mixed", placed
            except resolve_bridge.ResolveError as exc:
                warnings.append(f"Could not place the subtitles: {exc}")
                say(f"! {exc}")
        warnings.append(
            f"One track carries both languages, so it carries one font: choose one "
            f"that covers Arabic and Latin (for example {settings.font_ar}). "
            f"Resolve exposes no font API, so set it in the Inspector."
        )
        return outcome

    primary = settings.primary_language if settings.primary_language in ("en", "ar") else "en"
    pairs = {"en": (en_srt, english, settings.font_en, "Subs EN"),
             "ar": (ar_srt, arabic, settings.font_ar, "Subs AR")}
    secondary = "ar" if primary == "en" else "en"

    # Only the language that actually has cues is worth placing.
    if not pairs[primary][1] and pairs[secondary][1]:
        say(f"No {primary.upper()} cues; placing {secondary.upper()} instead.")
        primary, secondary = secondary, primary

    p_srt, p_cues, p_font, p_name = pairs[primary]
    if p_cues:
        try:
            placed = resolve_bridge.place_srt_on_timeline(p_srt, p_name, progress=say)
            outcome.placed_language, outcome.placed_cues = primary, placed
        except resolve_bridge.ResolveError as exc:
            warnings.append(f"Could not place the {primary.upper()} subtitles: {exc}")
            say(f"! {exc}")

    s_srt, s_cues, s_font, s_name = pairs[secondary]
    if s_cues:
        # Resolve routes every append to the already-populated track, so the
        # second language cannot be placed automatically. Import it to the Media
        # Pool and give the user an empty track to drop it on.
        try:
            resolve_bridge.import_srt_to_pool(s_srt)
            index = resolve_bridge.add_empty_subtitle_track(s_name)
            outcome.manual_srt, outcome.manual_track_index = str(s_srt), index
            say(
                f"{s_srt.name} is in the Media Pool. Drag it onto subtitle track "
                f"{index} ('{s_name}') to finish."
            )
        except resolve_bridge.ResolveError as exc:
            warnings.append(f"Could not stage the {secondary.upper()} subtitles: {exc}")

    warnings.append(
        f"Set the fonts by hand in the Inspector — {settings.font_en} for English, "
        f"{settings.font_ar} for Arabic. Resolve exposes no font API."
    )
    return outcome
