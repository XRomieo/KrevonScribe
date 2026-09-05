"""Cue modelling, Arabic/English routing and SRT writing.

This module is deliberately dependency-free and knows nothing about Resolve or
Kaggle, so it can be tested standalone against a sample ``segments.json``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# Every Unicode block that carries Arabic script. Arabic Presentation Forms are
# included because some ASR output is normalised into them.
_ARABIC_RANGES: tuple[tuple[int, int], ...] = (
    (0x0600, 0x06FF),    # Arabic
    (0x0750, 0x077F),    # Arabic Supplement
    (0x0870, 0x089F),    # Arabic Extended-B
    (0x08A0, 0x08FF),    # Arabic Extended-A
    (0xFB50, 0xFDFF),    # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),    # Arabic Presentation Forms-B
    (0x10EC0, 0x10EFF),  # Arabic Extended-C
)

# Arabic-Indic digits are script-neutral in practice: a bare number should not
# drag an otherwise-English cue onto the Arabic track.
_ARABIC_DIGITS = frozenset(range(0x0660, 0x066A)) | frozenset(range(0x06F0, 0x06FA))

LANG_EN = "en"
LANG_AR = "ar"


def is_arabic_char(ch: str) -> bool:
    """True if ``ch`` belongs to an Arabic-script block."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES)


def _is_scriptful(ch: str) -> bool:
    """True for characters that carry script identity.

    Punctuation, whitespace, symbols and digits are excluded, so ``"...؟ 123"``
    does not count as evidence for either language.
    """
    if ch.isspace():
        return False
    if ord(ch) in _ARABIC_DIGITS:
        return False
    return unicodedata.category(ch).startswith("L")


def arabic_ratio(text: str) -> float:
    """Fraction of script-bearing characters in ``text`` that are Arabic.

    Returns ``0.0`` for text with no letters at all, so numeric-only cues route
    to English rather than raising.
    """
    letters = [c for c in text if _is_scriptful(c)]
    if not letters:
        return 0.0
    return sum(1 for c in letters if is_arabic_char(c)) / len(letters)


def classify(text: str, threshold: float = 0.5) -> str:
    """Route a cue to :data:`LANG_AR` or :data:`LANG_EN`.

    ``threshold`` is the share of letters that must be Arabic for the cue to be
    treated as Arabic. The default of 0.5 means "majority script wins", so a
    mostly-English sentence with one Arabic word stays on the English track.
    Lower it toward 0.0 to route any cue containing Arabic to the Arabic track.
    """
    return LANG_AR if arabic_ratio(text) >= threshold else LANG_EN


@dataclass(frozen=True)
class Cue:
    """One subtitle cue. ``start``/``end`` are seconds from the timeline start."""

    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"cue starts before zero: {self.start}")
        if self.end < self.start:
            raise ValueError(f"cue ends before it starts: {self.start} -> {self.end}")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def language(self, threshold: float = 0.5) -> str:
        return classify(self.text, threshold)


def format_timestamp(seconds: float) -> str:
    """Render seconds as an SRT timestamp (``HH:MM:SS,mmm``)."""
    if seconds < 0:
        raise ValueError(f"negative timestamp: {seconds}")
    # Round to milliseconds first so 59.9999 becomes 00:01:00,000 rather than
    # 00:00:59,1000.
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s, m, h = total_s % 60, (total_s // 60) % 60, total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_segments(path: str | Path) -> list[Cue]:
    """Read the ``segments.json`` produced by the Kaggle kernel."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):          # tolerate {"segments": [...]} shape
        raw = raw.get("segments", [])
    return cues_from_segments(raw)


def cues_from_segments(segments: Iterable[dict]) -> list[Cue]:
    """Build cues from raw whisper segments, dropping empty text."""
    cues: list[Cue] = []
    for seg in segments:
        text = _clean(str(seg.get("text", "")))
        if not text:
            continue
        cues.append(Cue(start=float(seg["start"]), end=float(seg["end"]), text=text))
    return cues


def _clean(text: str) -> str:
    """Collapse whitespace and strip zero-width/bidi control characters.

    Whisper occasionally emits bidi marks around code-switched spans; Resolve
    renders them as stray glyphs, and they would also skew the script ratio.
    """
    text = text.replace("​", "").replace("‎", "").replace("‏", "")
    text = text.replace("‪", "").replace("‫", "").replace("‬", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def split_by_language(
    cues: Sequence[Cue], threshold: float = 0.5
) -> tuple[list[Cue], list[Cue]]:
    """Partition cues into ``(english, arabic)``. Every cue lands in exactly one."""
    english: list[Cue] = []
    arabic: list[Cue] = []
    for cue in cues:
        (arabic if cue.language(threshold) == LANG_AR else english).append(cue)
    return english, arabic


def split_tagged_segments(
    segments: Iterable[dict], threshold: float = 0.5
) -> tuple[list[Cue], list[Cue]]:
    """Split segments into (english, arabic), trusting a language tag if present.

    A backend that reports the spoken language per word — Speechmatics Melia
    does — knows better than we can infer from the script. Falling back to
    script classification matters for the whisper path, and also for a tagged
    cue whose text is genuinely the other script (a transliterated name).
    """
    english: list[Cue] = []
    arabic: list[Cue] = []
    for segment in segments:
        text = _clean(str(segment.get("text", "")))
        if not text:
            continue
        cue = Cue(float(segment["start"]), float(segment["end"]), text)
        tag = str(segment.get("language", "") or "").strip().lower().split("-")[0]
        if tag == LANG_AR:
            arabic.append(cue)
        elif tag == LANG_EN:
            english.append(cue)
        elif classify(text, threshold) == LANG_AR:
            arabic.append(cue)
        else:
            english.append(cue)
    return english, arabic


def merge_for_single_track(
    *groups: Sequence[Cue], min_duration: float = 0.12, min_display: float = 0.9
) -> list[Cue]:
    """Interleave several languages into one non-overlapping, ordered track.

    Resolve shows one subtitle track at a time, so both languages have to share
    a track to be watchable — and a single track cannot hold overlapping cues.
    Where two cues collide the earlier one is trimmed to end where the next
    begins.

    A cue shorter than ``min_display`` is then held on screen into the silence
    after it, up to that length, rather than being deleted: a real word said
    quickly ("Why?", 0.18 s) is worth reading, and the gap before the next cue
    costs nothing. Only what still cannot reach ``min_duration`` — a fragment
    with no room at all — is dropped.
    """
    merged = sorted(
        (cue for group in groups for cue in group), key=lambda c: (c.start, c.end)
    )
    out: list[Cue] = []
    for cue in merged:
        if out and cue.start < out[-1].end:
            trimmed_end = min(out[-1].end, cue.start)
            if trimmed_end - out[-1].start >= min_duration:
                out[-1] = Cue(out[-1].start, trimmed_end, out[-1].text)
            else:
                out.pop()
        if cue.end - cue.start >= min_duration:
            out.append(cue)

    for i, cue in enumerate(out):
        if cue.end - cue.start >= min_display:
            continue
        # Never past the next cue: the track holds one subtitle at a time.
        ceiling = out[i + 1].start if i + 1 < len(out) else cue.start + min_display
        end = min(cue.start + min_display, ceiling)
        if end > cue.end:
            out[i] = Cue(cue.start, end, cue.text)
    return out


def render_srt(cues: Sequence[Cue], offset: float = 0.0) -> str:
    """Render cues as SRT text.

    Resolve places an imported SRT at ``timeline_start + cue_time``, so cue times
    measured from the start of the exported audio are used as-is and ``offset``
    stays 0 for the normal timeline path. It exists for the manual-file mode,
    where the audio may begin partway into the timeline.
    """
    blocks = []
    for index, cue in enumerate(sorted(cues, key=lambda c: (c.start, c.end)), start=1):
        start = format_timestamp(cue.start + offset)
        end = format_timestamp(cue.end + offset)
        blocks.append(f"{index}\n{start} --> {end}\n{cue.text}\n")
    # SRT readers are happiest with a trailing blank line and CRLF-free output;
    # Resolve accepts LF.
    return "\n".join(blocks)


def write_srt(cues: Sequence[Cue], path: str | Path, offset: float = 0.0) -> Path:
    """Write cues to ``path`` as UTF-8 SRT and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_srt(cues, offset), encoding="utf-8")
    return out
