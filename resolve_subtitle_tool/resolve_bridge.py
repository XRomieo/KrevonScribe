"""Talks to DaVinci Resolve.

Every call used here was verified against Resolve Studio 21.0.0.47; see
docs/RESOLVE_API_FINDINGS.md for the evidence and for the limitations that
shape this module (no font API, and only one subtitle track can be populated).

Handles (resolve/project/timeline) are re-acquired on each operation rather than
cached, because a Resolve restart leaves stale proxies whose attribute lookups
silently return ``None``.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

Progress = Callable[[str], None]


class ResolveError(RuntimeError):
    """Base class for every failure originating from the Resolve integration."""


class ResolveNotRunning(ResolveError):
    pass


class NoProjectOpen(ResolveError):
    pass


class NoTimelineOpen(ResolveError):
    pass


def _module_dirs() -> list[Path]:
    """Candidate locations of Resolve's bundled scripting modules."""
    env = os.environ.get("RESOLVE_SCRIPT_API")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env) / "Modules")
    if sys.platform == "darwin":
        candidates.append(
            Path("/Library/Application Support/Blackmagic Design/DaVinci Resolve"
                 "/Developer/Scripting/Modules")
        )
    elif sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        candidates.append(
            Path(program_data) / "Blackmagic Design" / "DaVinci Resolve" / "Support"
            / "Developer" / "Scripting" / "Modules"
        )
    else:
        candidates.append(Path("/opt/resolve/Developer/Scripting/Modules"))
    return candidates


def connect():
    """Return the Resolve application object.

    Raises :class:`ResolveNotRunning` with an actionable message rather than
    letting an ImportError or a bare ``None`` escape.
    """
    for d in _module_dirs():
        if d.is_dir() and str(d) not in sys.path:
            sys.path.insert(0, str(d))
    try:
        import DaVinciResolveScript as dvr  # noqa: N813
    except ImportError as exc:
        raise ResolveNotRunning(
            "Could not load Resolve's scripting module. Checked: "
            + ", ".join(str(d) for d in _module_dirs())
            + ". Install DaVinci Resolve, or set RESOLVE_SCRIPT_API."
        ) from exc

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise ResolveNotRunning(
            "DaVinci Resolve is not running, or external scripting is disabled. "
            "Start Resolve and set Preferences > System > General > "
            "'External scripting using' to Local."
        )
    return resolve


def _current(resolve):
    """Return ``(project, timeline)``, raising clear errors when either is absent."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        raise NoProjectOpen("No project is open in Resolve.")
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise NoTimelineOpen(
            f"Project '{project.GetName()}' has no timeline open. "
            "Open a timeline and try again."
        )
    return project, timeline


@dataclass
class AudioTrack:
    index: int
    name: str
    sub_type: str
    enabled: bool
    clip_count: int


@dataclass
class TimelineInfo:
    product: str
    version: str
    project: str
    timeline: str
    fps: float
    start_frame: int
    end_frame: int
    audio_tracks: list[AudioTrack]
    subtitle_track_count: int
    populated_subtitle_tracks: list[int]

    @property
    def has_content(self) -> bool:
        return self.end_frame > self.start_frame

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["audio_tracks"] = [t.__dict__ for t in self.audio_tracks]
        d["has_content"] = self.has_content
        return d


def get_info() -> TimelineInfo:
    """Snapshot of what the tool needs to know about the open timeline."""
    resolve = connect()
    project, timeline = _current(resolve)

    tracks = []
    for i in range(1, timeline.GetTrackCount("audio") + 1):
        tracks.append(
            AudioTrack(
                index=i,
                name=timeline.GetTrackName("audio", i) or f"Audio {i}",
                sub_type=timeline.GetTrackSubType("audio", i) or "",
                enabled=bool(timeline.GetIsTrackEnabled("audio", i)),
                clip_count=len(timeline.GetItemListInTrack("audio", i) or []),
            )
        )

    sub_count = timeline.GetTrackCount("subtitle")
    populated = [
        i for i in range(1, sub_count + 1)
        if timeline.GetItemListInTrack("subtitle", i)
    ]

    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except (TypeError, ValueError):
        fps = 24.0

    return TimelineInfo(
        product=resolve.GetProductName(),
        version=resolve.GetVersionString(),
        project=project.GetName(),
        timeline=timeline.GetName(),
        fps=fps,
        start_frame=timeline.GetStartFrame(),
        end_frame=timeline.GetEndFrame(),
        audio_tracks=tracks,
        subtitle_track_count=sub_count,
        populated_subtitle_tracks=populated,
    )


def export_timeline_audio(
    track_indices: Sequence[int],
    out_dir: str | Path,
    basename: str = "timeline_audio",
    progress: Progress | None = None,
    poll_seconds: float = 0.5,
    timeout_seconds: float = 3600.0,
) -> Path:
    """Render the selected audio tracks to a single 48 kHz / 16-bit stereo WAV.

    Tracks not in ``track_indices`` are muted for the duration of the render and
    their original enabled state is restored afterwards, including on failure.
    """
    say = progress or (lambda _m: None)
    resolve = connect()
    project, timeline = _current(resolve)

    total = timeline.GetTrackCount("audio")
    wanted = {int(i) for i in track_indices}
    if not wanted:
        raise ResolveError("Select at least one audio track to export.")
    invalid = sorted(i for i in wanted if not 1 <= i <= total)
    if invalid:
        raise ResolveError(
            f"Audio track(s) {invalid} do not exist; the timeline has {total}."
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original = {i: bool(timeline.GetIsTrackEnabled("audio", i)) for i in range(1, total + 1)}
    job_id = None
    try:
        for i in range(1, total + 1):
            timeline.SetTrackEnable("audio", i, i in wanted)
        say(f"Muted {total - len(wanted)} of {total} audio tracks.")

        # SetCurrentRenderFormatAndCodec('wav','lpcm') returns False on 21.0.0;
        # the stock preset is what actually configures a WAV-only render.
        if not project.LoadRenderPreset("Audio Only"):
            raise ResolveError("Could not load Resolve's 'Audio Only' render preset.")
        ok = project.SetRenderSettings({
            "TargetDir": str(out_dir),
            "CustomName": basename,
            "ExportVideo": False,
            "ExportAudio": True,
            "AudioCodec": "lpcm",
            "AudioBitDepth": 16,
            "AudioSampleRate": 48000,
        })
        if not ok:
            raise ResolveError("Resolve rejected the audio render settings.")

        job_id = project.AddRenderJob()
        if not job_id:
            raise ResolveError("Resolve did not create a render job.")
        say("Rendering audio…")
        if not project.StartRendering([job_id], isInteractiveMode=False):
            raise ResolveError("Resolve failed to start the render.")

        deadline = time.monotonic() + timeout_seconds
        while project.IsRenderingInProgress():
            if time.monotonic() > deadline:
                raise ResolveError(f"Audio render timed out after {timeout_seconds:.0f}s.")
            time.sleep(poll_seconds)

        status = project.GetRenderJobStatus(job_id) or {}
        if status.get("JobStatus") != "Complete":
            raise ResolveError(f"Audio render did not complete: {status}")
    finally:
        for i, was_enabled in original.items():
            timeline.SetTrackEnable("audio", i, was_enabled)
        if job_id:
            project.DeleteAllRenderJobs()

    expected = out_dir / f"{basename}.wav"
    if expected.exists():
        say(f"Rendered {expected.name}.")
        return expected
    # Resolve occasionally decorates the filename; fall back to the newest WAV.
    candidates = sorted(out_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise ResolveError(f"Render reported success but no WAV appeared in {out_dir}.")
    say(f"Rendered {candidates[-1].name}.")
    return candidates[-1]


def _import_srt(project, srt_path: Path):
    """Import an SRT using an existing project handle.

    MediaPoolItems are bound to the connection that created them, so the caller
    must pass the same ``project`` it will append with -- mixing objects from
    two ``scriptapp()`` calls makes AppendToTimeline fail silently.
    """
    if not srt_path.is_file():
        raise ResolveError(f"Subtitle file not found: {srt_path}")
    items = project.GetMediaPool().ImportMedia([str(srt_path)]) or []
    if not items:
        raise ResolveError(
            f"Resolve refused to import {srt_path.name}. Only SRT is accepted "
            "(ASS/SSA and FCPXML captions are rejected)."
        )
    return items[0]


def import_srt_to_pool(srt_path: str | Path):
    """Import an SRT into the Media Pool and return its MediaPoolItem."""
    resolve = connect()
    project, _ = _current(resolve)
    return _import_srt(project, Path(srt_path))


def place_srt_on_timeline(
    srt_path: str | Path,
    track_name: str | None = None,
    progress: Progress | None = None,
) -> int:
    """Import an SRT and place its cues on a new subtitle track.

    Returns the number of cues placed. Cues land at
    ``timeline_start + cue_time``, so the SRT must be timed from the start of
    the timeline.

    Only works when no subtitle track already holds cues: Resolve routes every
    append to the populated track regardless of ``trackIndex``, and appending
    onto an occupied track corrupts the timing.
    """
    say = progress or (lambda _m: None)
    resolve = connect()
    project, timeline = _current(resolve)

    if timeline.GetEndFrame() <= timeline.GetStartFrame():
        # Appending to a zero-duration timeline crashed Resolve during probing.
        raise ResolveError(
            "The timeline is empty. Add media before importing subtitles."
        )

    populated = [
        i for i in range(1, timeline.GetTrackCount("subtitle") + 1)
        if timeline.GetItemListInTrack("subtitle", i)
    ]
    if populated:
        raise ResolveError(
            f"Subtitle track(s) {populated} already contain cues. Resolve sends "
            "every import to the populated track, which would corrupt their "
            "timing. Clear or delete those tracks, then retry."
        )

    # Verified order: create the track first, then import, then append.
    if timeline.GetTrackCount("subtitle") == 0:
        timeline.AddTrack("subtitle")
    target = timeline.GetTrackCount("subtitle")

    item = _import_srt(project, Path(srt_path))

    # Only the plain-list form works; the clipInfo dict silently no-ops here.
    if not project.GetMediaPool().AppendToTimeline([item]):
        raise ResolveError("Resolve did not place the subtitle clip on the timeline.")

    placed = 0
    for i in range(1, timeline.GetTrackCount("subtitle") + 1):
        cues = timeline.GetItemListInTrack("subtitle", i) or []
        if cues:
            target, placed = i, len(cues)
            break
    if track_name:
        timeline.SetTrackName("subtitle", target, track_name)
    say(f"Placed {placed} cues on subtitle track {target}.")
    return placed


def clear_subtitle_tracks(progress: Progress | None = None) -> int:
    """Delete every subtitle track, so a re-run starts from a clean timeline.

    Deleting is the only reliable reset: Resolve routes every import to whichever
    track already holds cues, so a leftover track from a previous run silently
    captures the next one. Returns the number of tracks removed.

    Destructive by design — the caller is responsible for meaning it.
    """
    say = progress or (lambda _m: None)
    resolve = connect()
    _, timeline = _current(resolve)

    removed = 0
    # Delete from the top down; removing a lower track renumbers the ones above.
    for index in range(timeline.GetTrackCount("subtitle"), 0, -1):
        if timeline.DeleteTrack("subtitle", index):
            removed += 1
        else:
            raise ResolveError(f"Resolve refused to delete subtitle track {index}.")
    if removed:
        say(f"Removed {removed} existing subtitle track(s).")
    return removed


def add_empty_subtitle_track(name: str | None = None) -> int:
    """Add an empty subtitle track for the user to drag the second SRT onto."""
    resolve = connect()
    _, timeline = _current(resolve)
    if not timeline.AddTrack("subtitle"):
        raise ResolveError("Resolve refused to add a subtitle track.")
    index = timeline.GetTrackCount("subtitle")
    if name:
        timeline.SetTrackName("subtitle", index, name)
    return index
