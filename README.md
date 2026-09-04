# Resolve EN/AR Subtitle Tool

Pulls audio out of a DaVinci Resolve timeline, transcribes it on a free Kaggle
GPU with faster-whisper, splits the result into English and Arabic subtitle
files, and imports them back into Resolve.

Runs on macOS and Windows. The Windows build is a portable folder — no
installer, no admin rights, no Python needed.

---

## Two corrections to the original plan

Both were established by probing a live Resolve install, not by reading docs.
The evidence is in [`docs/RESOLVE_API_FINDINGS.md`](docs/RESOLVE_API_FINDINGS.md)
and the re-runnable scripts in `scripts/probe_*.py`.

**Resolve Studio is not required.** Resolve's own README states the scripting
API is "a common superset of functions for both the Free and Studio versions".
Only Studio-gated features (its built-in transcription, voice isolation, Magic
Mask) return `False`. Nothing this tool needs is on that list.

**There is no font API.** `grep -i font` over the entire 112 KB scripting
reference returns zero matches, `TimelineItem.SetProperty` accepts only
transform and composite keys, and all 157 project and timeline settings contain
nothing about typefaces. The planned
`SetTrackSettings("subtitle", i, {"font": ...})` does not exist in any form.
Fonts are set by hand, once per subtitle track, in the Inspector. The app stores
your two font names and reminds you which to apply.

---

## What is automatic, and what is not

Automatic:

1. Mute the audio tracks you did not arm, render the rest to one 48 kHz /
   16-bit stereo WAV, restore the mute states afterwards.
2. Upload the WAV to a private Kaggle dataset, push a GPU kernel, poll it, and
   download `segments.json`.
3. Route every cue to English or Arabic by inspecting its script, and write
   `<name>.en.srt` and `<name>.ar.srt`.
4. Import both SRTs and place **one** language onto a new subtitle track,
   frame-accurately.

Manual, twice:

- **Drag the second SRT** from the Media Pool onto the empty subtitle track the
  tool creates for it. Resolve routes every scripted import to whichever
  subtitle track already holds cues — `trackIndex` is ignored, inserting or
  locking tracks does not redirect it, and appending onto an occupied track
  corrupts the timing. So only one language can be placed programmatically.
- **Set the font** on each subtitle track in the Inspector, for the reason above.

---

## Requirements

- DaVinci Resolve 18 or newer, **free or Studio**, running, with a timeline open
- Preferences → System → General → *External scripting using* set to **Local**
- A Kaggle account and API token (kaggle.com → Settings → API)
- An Arabic-capable font installed — Geeza Pro ships with macOS, Dubai with Windows

Transcription runs on Kaggle, so no GPU, no `faster-whisper`, and no model
downloads are needed locally.

---

## Install

### Windows — portable

Download `ResolveSubtitles-windows-portable.zip` from the Releases page, unzip
anywhere, and run `ResolveSubtitles.exe`. WebView2, which the UI renders in,
ships with Windows 10 and 11.

### macOS — from source

```bash
git clone <this repo> && cd DavinciAudioTranscription
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build.py --frontend-only   # needs bun, from https://bun.sh
.venv/bin/python app.py
```

To produce a `.app` bundle instead, install `requirements-dev.txt` and run
`python scripts/build.py`, which writes `dist/ResolveSubtitles.app`. It is
unsigned, so first launch needs right-click → Open.

---

## Using it

1. Open your timeline in Resolve, then start the app. The top rail should read
   **Connected** with your project, timeline and frame rate.
2. Arm the audio tracks to transcribe. Unarmed tracks are muted for the render
   and restored afterwards.
3. Add your Kaggle credentials once, under **Kaggle**.
4. Choose which language gets auto-placed, and set the Arabic threshold — the
   share of a cue's letters that must be Arabic script for it to route to the
   Arabic track. 50% means the majority script wins, so an English sentence
   containing one Arabic word stays on the English track. 0% sends any cue
   containing Arabic to the Arabic track.
5. Press **Transcribe**. Expect several minutes: upload, queue, model load, then
   transcription.
6. Finish the two manual steps described above.

**Audio file mode** transcribes a file from disk and writes both SRTs, but does
not import them, because the cue times are relative to that file rather than to
a timeline.

---

## How cues are routed

Whisper detects one language for a whole file, so a per-segment language tag is
not available. Each cue's text is inspected directly instead: the tool counts
letters in Arabic Unicode blocks against total letters, ignoring digits,
punctuation and whitespace, and compares the ratio to your threshold.

The honest limit: a subtitle track carries one font, so an English sentence with
an Arabic word inline renders entirely in one track's typeface. True per-word
font mixing would need Text+ generators instead of subtitle tracks, which is a
much heavier approach and is not what this builds.

---

## Layout

```
app.py                     entry point
app.spec                   PyInstaller bundle definition
resolve_subtitle_tool/
  main.py                  opens the pywebview window
  api_bridge.py            the js_api object exposed to the frontend
  pipeline.py              audio -> Kaggle -> SRTs -> Resolve
  resolve_bridge.py        Resolve: tracks, audio render, SRT import
  kaggle_runner.py         Kaggle: dataset, kernel, polling, download
  subtitle_utils.py        cue model, Arabic routing, SRT writing
  config.py                persisted settings and credentials
  kaggle_kernel/
    transcribe_kernel.py   runs on Kaggle, not locally
frontend/                  React + Tailwind + shadcn/ui, rendered in pywebview
scripts/
  build.py                 frontend + bundle build
  probe_*.py               the Resolve API experiments behind the findings doc
tests/                     64 tests, no Resolve or network needed
docs/RESOLVE_API_FINDINGS.md
```

`subtitle_utils.py` is dependency-free and holds the routing logic, so the test
suite runs anywhere without Resolve, a GPU, or network access.

---

## Troubleshooting

**"DaVinci Resolve is not running, or external scripting is disabled"** — start
Resolve and set Preferences → System → General → *External scripting using* to
**Local**.

**"Subtitle track(s) [1] already contain cues"** — Resolve would send the import
to that track and corrupt its timing. Clear or delete those subtitle tracks
first. The tool refuses rather than damage existing work.

**The window opens but stays on "Connecting…"** — the app retries the startup
handshake and then shows the actual error with a Retry button. If it names
Resolve, check the scripting preference above.

**The Kaggle kernel fails** — the log links the kernel page; its output shows
whether the GPU quota is exhausted or the model download failed. Kaggle allows
roughly 30 GPU-hours a week.

**Windows build is flagged by SmartScreen** — the executable is unsigned. Choose
*More info* → *Run anyway*, or sign it yourself.
