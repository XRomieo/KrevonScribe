# Krevon Scribe

Pulls audio out of a DaVinci Resolve timeline, transcribes English and Arabic
together on a free Kaggle GPU, and puts the subtitles back on the timeline.

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
The font is set by hand, once, in the Inspector. The app names the one you
picked when the run finishes.

---

## What is automatic, and what is not

Both languages go into **one** subtitle track, in time order. That is not a
compromise, it is the only arrangement that works: Resolve displays a single
subtitle track at a time, and it routes every programmatic append to the
already-populated track, so a second track could never be filled automatically
anyway. One track also means one font — pick one that covers Arabic and Latin
(Geeza Pro, Noto Sans Arabic) and set it in the Inspector.

Set `single_track = false` in `settings.json` to get the old behaviour instead:
the primary language placed automatically and the second staged in the Media
Pool for you to drag onto its own track.

## Choosing a transcription backend

| | `kaggle` (default) | `speechmatics` |
|---|---|---|
| Model | `whisper-medium-arabic-codeswitched` | Melia 1 |
| Arabic/English code-switching | native, one pass | native, one pass |
| Language accuracy on the test clip | **96.1%** | not yet measured |
| Language per word | read off the script | reported by the model |
| Timestamps | re-timed by CTC forced alignment | reported by the model |
| Cost | free | $100 starting credit, no card |
| Setup | Kaggle account, phone-verified | one API key |
| Sends audio to | Kaggle | Speechmatics |

`kaggle` is the default and is free. It transcribes once with a checkpoint
fine-tuned on code-switched Arabic/English, which writes Arabic speech in Arabic
script and English in Latin *within the same sentence* — so the language is read
off the transcript rather than guessed. Whisper's timestamps drift, so the cue
text is then re-timed against the audio by a CTC forced aligner. Both steps are
measured in [docs/TRANSCRIPTION_FINDINGS.md](docs/TRANSCRIPTION_FINDINGS.md)
against language spans marked by hand in Resolve.

No cue holds both scripts: the speaker switches language inside a sentence, and
one track carries one font. Turn off **Never mix scripts in one cue** in Settings
to keep such a sentence whole instead.

Set `code_switch_method = "confidence"` in `settings.json` to fall back to the
older route (stock whisper run four times, language inferred from decoder
confidence). It scores 65–78% against the same spans and varies between runs, so
it is only worth reaching for if Hugging Face is unreachable.

`speechmatics` is the paid alternative, and needs less machinery still, because
Melia tags every word with the language it was spoken in — the split becomes a
lookup rather than an inference. It has not been run against real audio yet: the
code and its tests exist, but nobody has supplied an API key.

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

Download `KrevonScribe-windows-portable.zip` from the Releases page, unzip
anywhere, and run `KrevonScribe.exe`. WebView2, which the UI renders in, ships
with Windows 10 and 11.

### macOS — from source

```bash
git clone <this repo> && cd DavinciAudioTranscription
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build.py --frontend-only   # needs bun, from https://bun.sh
.venv/bin/python app.py
```

To produce a `.app` bundle instead, install `requirements-dev.txt` and run
`python scripts/build.py`, which writes `dist/KrevonScribe.app`. It is unsigned,
so first launch needs right-click → Open.

### Checking a build

```bash
python app.py --selftest          # or: KrevonScribe.exe --selftest
```

Imports what the app imports and exercises the cue logic end to end, without
needing Resolve, credentials or a network. It exists because a PyInstaller
bundle fails in a particular way — every file present, and then an import that
only happens at runtime missing on the user's machine — which checking the
folder contents cannot catch. CI runs it against the built Windows executable.
Since a windowed Windows build has no console, `--selftest-out <path>` writes
the report to a file.

The Windows portable build is produced by
[`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml) on
every push to `main`, and attached to a GitHub Release when a `v*` tag is
pushed. PyInstaller cannot cross-compile, so the `.exe` must be built on
Windows; that workflow is the only supported way to produce it.

---

## Using it

1. Open your timeline in Resolve, then start the app. The top bar should read
   **Resolve connected** and the page should name your timeline.
2. Tick the audio tracks to transcribe. Unticked tracks are muted for the render
   and switched back on afterwards.
3. Add your Kaggle token once, under the settings button. The app offers this as
   the first thing it asks for.
4. Press **Make subtitles**. Expect several minutes: render, upload, GPU queue,
   transcription, alignment. The page shows which stage it is on and how long
   each one took; the raw log is one click away.
5. When it finishes you see the actual cues, each in its own script and
   direction, and the one manual step left: set the subtitle track's font in the
   Inspector.

**File mode** transcribes a file from disk and writes the subtitle files, but
does not import them, because the cue times are relative to that file rather
than to a timeline.

If a run fails with *"Subtitle track(s) [1] already contain cues"*, the page
offers to clear those tracks and run again. Resolve sends every scripted import
to the track that already holds cues, so a second run cannot place anything
until they are cleared.

---

## How cues are routed

Stock Whisper picks **one** language for an entire file, from its opening
window. On a bilingual timeline that is not a small inaccuracy: the losing
language is *translated* into the winning one's script rather than transcribed.
Measured on a real 27-second EN/AR clip, global auto-detect returned Arabic at
p=0.89 and rendered the English narration as Arabic text.

The default route sidesteps that entirely. A checkpoint fine-tuned on
code-switched Arabic/English writes each word in the script it was spoken in,
so the language is **read off the transcript** instead of inferred:

- Words are grouped into runs by script. A short run is absorbed into its
  neighbours only when the *same* language sits on both sides of it — otherwise
  a genuine 0.71 s Arabic ending gets erased for being short.
- At a switch the model sometimes fuses the last word of one language and the
  first of the next into one token (` secret؟هيكون`). Those are split at the
  script boundary and their time apportioned by character count.
- Arabic punctuation after an English word (`Why؟`) is corrected per mark, from
  the nearest preceding letter, because a cue may legitimately hold both.
- Cue text is then re-timed against the audio by a CTC forced aligner. Whisper
  infers its timestamps rather than measuring them; alignment took the median
  correction from 0.306 s to 0.065 s and the worst case from 2.526 s to 0.320 s.

Every number above is scored against language spans marked by hand in Resolve
and kept as `tests/fixtures/codeswitch_ground_truth.json`.

The honest limit: a subtitle track carries one font, so an English sentence with
an Arabic word inline renders entirely in one track's typeface. True per-word
font mixing would need Text+ generators instead of subtitle tracks, which is a
much heavier approach and is not what this builds.

---

## Layout

```
app.py                     entry point
app.spec                   PyInstaller bundle definition
assets/                    the Krevon mark, and the .icns / .ico built from it
resolve_subtitle_tool/
  main.py                  opens the pywebview window
  api_bridge.py            the js_api object exposed to the frontend
  pipeline.py              audio -> Kaggle -> SRTs -> Resolve
  resolve_bridge.py        Resolve: tracks, audio render, SRT import
  kaggle_runner.py         Kaggle: dataset, kernel, polling, download
  speechmatics_runner.py   the paid alternative backend
  subtitle_utils.py        cue model, Arabic routing, SRT writing
  config.py                persisted settings and credentials
  kaggle_kernel/
    transcribe_kernel.py   runs on Kaggle, not locally
frontend/                  React + Tailwind, rendered in pywebview
  src/lib/stages.ts        maps the backend's log lines onto run stages
scripts/
  build.py                 frontend + bundle build
  make_icons.py            SVG -> .icns / .ico (macOS only; results committed)
  probe_*.py               the Resolve API experiments behind the findings doc
tests/                     190 tests, no Resolve or network needed
docs/RESOLVE_API_FINDINGS.md
docs/TRANSCRIPTION_FINDINGS.md
```

`subtitle_utils.py` is dependency-free and holds the routing logic, so the test
suite runs anywhere without Resolve, a GPU, or network access.

Settings live in the platform's per-user config directory, under
`Krevon Scribe`. Settings written by the earlier `ResolveSubtitleTool` builds
are still read, so upgrading does not reset your setup.

---

## Troubleshooting

**"DaVinci Resolve is not running, or external scripting is disabled"** — start
Resolve and set Preferences → System → General → *External scripting using* to
**Local**.

**"Subtitle track(s) [1] already contain cues"** — Resolve would send the import
to that track and corrupt its timing. Use the **Clear those tracks and run
again** button the failure offers, or turn on *Clear subtitle tracks before
importing* in Settings. The tool refuses by default rather than damage existing
work.

**The window opens but stays on "Starting up…"** — the app retries the startup
handshake and then shows the actual error with a Try again button. If it names
Resolve, check the scripting preference above.

**The Kaggle kernel fails** — the log links the kernel page; its output shows
whether the GPU quota is exhausted or the model download failed. Kaggle allows
roughly 30 GPU-hours a week.

**Windows build is flagged by SmartScreen** — the executable is unsigned. Choose
*More info* → *Run anyway*, or sign it yourself.

**Windows: "Failed to resolve Python.Runtime.Loader.Initialize"** — Windows
marks files extracted from a downloaded zip as untrusted, and .NET then refuses
to load the assembly pywebview draws its window through. Builds now ship a
`KrevonScribe.exe.config` that lifts the restriction. On an older build, clear
the mark by hand from the unzipped folder:

```powershell
Get-ChildItem -Recurse | Unblock-File
```

Unzipping to a local drive rather than a network drive avoids it as well.

**Windows: the window is blank, or the app says it needs WebView2** — the UI
needs the Microsoft Edge WebView2 runtime and .NET Framework 4.6.2 or newer.
Windows 11 and current Windows 10 have both. Without them pywebview silently
falls back to the Internet Explorer engine, which cannot run the UI at all, so
the app now checks and says so rather than opening a blank window. Install the
free Evergreen Runtime from
<https://developer.microsoft.com/microsoft-edge/webview2/>.

**Windows: the window opens but says it could not start** — the frontend is
served over `127.0.0.1` rather than `file://`, because pywebview does not fully
support `file://` and on Windows the page rendered while the JavaScript bridge
never attached. If this reappears, the error names what the bridge is exposing;
"nothing" means the bridge never arrived.
