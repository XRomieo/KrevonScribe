# DaVinci Resolve scripting API — verified findings

All results below were obtained empirically against a live Resolve install, not from
documentation. Re-runnable probes live in `scripts/probe_*.py`.

| | |
|---|---|
| Product | DaVinci Resolve **Studio** |
| Version | `21.0.0.47` |
| Platform | macOS (Darwin 27.0.0, Apple Silicon) |
| Probed | 2026-09-04 |

## Free vs Studio

The plan assumed Resolve Studio was a hard requirement. It is not. The README shipped
with Resolve states:

> The DaVinci Resolve scripting APIs cover a common superset of functions for both the
> Free and Studio versions of the application.

Only genuinely Studio-gated *features* return `False` (transcription, voice isolation,
Magic Mask, AI tools). **Nothing this tool needs is on that list** — track enumeration,
track enable/disable, rendering, and media import all exist in free Resolve.

`fusionscript.so` imports cleanly under both Python 3.9 and 3.14, so it uses the stable
ABI and does not pin us to an old interpreter.

## What works

### Connect
```python
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")   # None if Resolve isn't running
```

### Audio track enumeration and muting
`GetTrackCount("audio")`, `GetTrackName`, `GetTrackSubType`, `GetIsTrackEnabled`, and
`GetItemListInTrack` all behave as documented. `SetTrackEnable("audio", i, False)`
mutes a track and is confirmed by `GetIsTrackEnabled`. This is the mechanism for
isolating a subset of audio tracks before rendering.

### Audio-only WAV render
Verified end to end. `SetCurrentRenderFormatAndCodec("wav", "lpcm")` returns `False`
and leaves the format reading `unknown` — ignore it. Load the stock preset instead:

```python
project.LoadRenderPreset("Audio Only")           # -> True
project.SetRenderSettings({
    "TargetDir": out_dir,
    "CustomName": "name",
    "ExportVideo": False,
    "ExportAudio": True,
    "AudioCodec": "lpcm",
    "AudioBitDepth": 16,
    "AudioSampleRate": 48000,
})
job = project.AddRenderJob()
project.StartRendering([job], isInteractiveMode=False)
```

Produced `pcm_s16le, 48000 Hz, 2 ch, 10.000 s` for a 10 s timeline in 757 ms.
Poll with `IsRenderingInProgress()`; `GetRenderJobStatus(job)` returns
`{'JobStatus': 'Complete', 'CompletionPercentage': 100, ...}`.

### SRT import into the Media Pool
```python
items = mediaPool.ImportMedia(["/path/to/subs.srt"])
items[0].GetClipProperty("Type")      # "Subtitle"
items[0].GetClipProperty("Duration")  # "00:00:07:00"
items[0].GetClipProperty("Start TC")  # "00:00:00:12"  (first cue at 0.5 s @ 24 fps)
```
Arabic text round-trips correctly.

### Placing an SRT on a subtitle track
Only the **plain-list** form works:
```python
mediaPool.AppendToTimeline([clip])     # works
```
The dict form silently no-ops for subtitle clips, and its `trackIndex` / `recordFrame`
keys are **ignored**.

Placement rule, confirmed with a controlled calibration (`probe_14`), stable across
repeats:

```
placed_frame = timeline.GetStartFrame() + srt_cue_time_in_frames
```

| SRT first cue | clip Start TC | placed frame | offset from timeline start |
|---|---|---|---|
| `00:00:00,500` | `00:00:00:12` | 86412 | 12 (= 0.5 s) |
| `00:00:10,500` | `00:00:10:12` | 86652 | 252 (= 10.5 s) |
| `00:00:00,500` (repeat) | `00:00:00:12` | 86412 | 12 |

So SRT timecodes are interpreted **relative to timeline start**. Whisper timings taken
from audio exported at the timeline start drop in directly, with no compensation.

## What does NOT work

### Setting a font — no API exists
There is **no font key anywhere** in Resolve 21's scripting surface:

- `grep -i font` over the entire 112 KB `README.txt` returns **zero** matches.
- `TimelineItem.SetProperty` supports only transform/crop/composite/retime keys.
- Dumping all 157 project settings and all 157 timeline settings yields only
  `limitSubtitleCPL` and `limitSubtitleCaptionDurationSec` — no typeface, size, or colour.

The plan's `SetTrackSettings("subtitle", index, {"font": ...})` **does not exist** in any
form. Fonts must be set once by hand in the Inspector. This is a hard limitation, not a
version quirk.

### Only one subtitle track can be populated
Every append lands on whichever subtitle track already holds cues. Exhaustively tested:

| Attempt | Result |
|---|---|
| `trackIndex` in the clipInfo dict | ignored |
| Add empty track at end, then append | still lands on the occupied track |
| Insert track at `{"index": 1}` to shift the full one up | still follows the occupied track object |
| Bounce `SetCurrentTimeline` away and back to clear cached state | still follows the occupied track |
| `SetTrackLock` the occupied track to force the append elsewhere | append silently does nothing |

Appending a second SRT onto an already-occupied track also **corrupts timing** — the new
cues are pushed past the existing content (`86712` instead of the correct `86652`).

Consequence: exactly one language can be auto-placed on the timeline. The second SRT is
imported into the Media Pool for the user to drag onto a second track — a single drag,
alongside the font step that is manual regardless.

### Other rejected import routes
| Route | Result |
|---|---|
| `ImportMedia(["file.ass"])` — styled ASS/SSA | returns `[]`, rejected outright |
| `timeline.ImportIntoTimeline("file.srt")` | `False` (AAF only) |
| `mediaPool.ImportTimelineFromFile("file.srt")` | `None` |
| FCPXML 1.10 `<caption>` with `<text-style font=...>`, `SRT` role | timeline imports, **captions silently dropped** |
| Same with `iTT`/`ITT` caption role | captions silently dropped |
| OTIO export | subtitle tracks omitted entirely from the export |
| Undocumented methods (`ImportSubtitle`, `AddSubtitles`, 8 more names) | none exist on Timeline / MediaPool / Project / Resolve |

ASS was the most promising route, since it carries per-cue font styling in the file
itself and would have solved fonts and import together. Resolve does not accept it.

## Stability note

Resolve **crashed** (process gone, no crash report) during `probe_03`, which appended a
subtitle clip to a zero-duration empty timeline. Guard against appending to a timeline
with no video/audio content.

Remote object handles do not survive a Resolve restart — a stale proxy makes attribute
lookups return `None`, surfacing as `TypeError: 'NoneType' object is not callable`.
Re-acquire `resolve`/`project`/`timeline` handles rather than caching them across a run.

Note that `getattr` on a `PyRemoteObject` returns `None` for unknown names instead of
raising, so probe for a method with `is not None` rather than `try/except`.
