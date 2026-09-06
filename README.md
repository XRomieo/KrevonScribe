# Krevon Scribe

Transcribes English and Arabic together on a free Kaggle GPU and writes a
subtitle file. Point it at an audio file, wait, drag the `.srt` onto your
timeline.

Runs on macOS and Windows. The Windows build is a portable folder — no
installer, no admin rights, no Python needed.

---

## Why there is no editor integration

An earlier version drove DaVinci Resolve directly: it rendered the timeline's
audio out, transcribed it, and imported the cues back onto a subtitle track.
That is gone. It needed Resolve installed, running, licensed, with external
scripting switched on and a native library that loads into the Python process —
and it failed differently on every machine, always at the point where the user
had already waited several minutes for a GPU.

SRT costs nothing and works everywhere. Resolve, Premiere Pro, Final Cut,
CapCut, DaVinci on someone else's laptop, a web player — they all read the same
file, and dragging it onto a track is one gesture. The work worth doing was
never the import; it was getting two languages out of one recording correctly.

The Resolve API experiments behind that decision are still here, in
[`docs/RESOLVE_API_FINDINGS.md`](docs/RESOLVE_API_FINDINGS.md) and the
re-runnable `scripts/probe_*.py`. They are a record, not a dependency: nothing
in the app imports them.

---

## What you get

Every run writes three files next to each other:

| file | what is in it |
|---|---|
| `<name>.srt` | both languages, in time order — **this is the one to drag in** |
| `<name>.en.srt` | the English cues only |
| `<name>.ar.srt` | the Arabic cues only |

The combined file is what most people want: one subtitle track, everything in
it. A track carries one font, so pick one that covers Arabic and Latin — Geeza
Pro on macOS, Dubai on Windows, Noto Sans Arabic anywhere. If you would rather
give each language its own typeface, drop the two split files onto two tracks
instead.

No cue holds both scripts by default: the speaker switches language inside a
sentence, and one track carries one font. Turn off **Never mix scripts in one
cue** in Settings to keep such a sentence whole instead.

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
against language spans marked by hand.

Set `code_switch_method = "confidence"` in `settings.json` to fall back to the
older route (stock whisper run four times, language inferred from decoder
confidence). It scores 65–78% against the same spans and varies between runs, so
it is only worth reaching for if Hugging Face is unreachable.

`speechmatics` is the paid alternative, and needs less machinery still, because
Melia tags every word with the language it was spoken in — the split becomes a
lookup rather than an inference. It has not been run against real audio yet: the
code and its tests exist, but nobody has supplied an API key.

## Requirements

- A Kaggle account and API token (kaggle.com → Settings → API)
- An audio file: WAV, FLAC, MP3, M4A, AAC, OGG or Opus
- An Arabic-capable font in whatever you edit in — Geeza Pro ships with macOS,
  Dubai with Windows

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
git clone <this repo> && cd KrevonScribe
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build.py --frontend-only   # needs bun, from https://bun.sh
.venv/bin/python app.py
```

To produce a `.app` bundle instead, install `requirements-dev.txt` and run
`python scripts/build.py`, which writes `dist/KrevonScribe.app`. It is unsigned,
so first launch needs right-click → Open.

### Windows — from source

```powershell
git clone <this repo>; cd KrevonScribe
py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\build.py            # needs bun, from https://bun.sh
.\.venv\Scripts\python.exe app.py
```

`scripts/build.py` with no flags produces the portable folder in
`dist/KrevonScribe/`, the same layout CI ships; `--frontend-only` stops after
the frontend and leaves `python app.py` to run from source. Both work.

Python 3.12 is what CI builds with, so it is the version to match when the
output is going to be released. The tests, the frontend build and the app
itself were also run on 3.14, where `pywebview`, `pythonnet` and `pyinstaller`
all still have wheels, so a newer interpreter is fine for working on the app.

### Icons

`assets/krevon.ico` and `assets/krevon.icns` are committed, because PyInstaller
needs them at bundle time. `python scripts/make_icons.py --ico` rebuilds the
Windows one from `assets/krevon-icon.svg` on any platform; `--icns` rebuilds the
macOS one and needs `iconutil`.

### Window chrome

The Windows build draws its own title bar so the bar matches the app's dark
palette instead of the system's white-on-grey caption. Going frameless gives up
the resize border, title-bar dragging, and the minimize/maximize/close buttons;
`window_chrome.py` buys each of them back with the Win32 calls that do those
jobs. macOS keeps its native title bar.

### Checking a build

```bash
python app.py --selftest          # or: KrevonScribe.exe --selftest
```

Imports what the app imports and exercises the cue logic end to end, without
needing credentials or a network. It exists because a PyInstaller bundle fails
in a particular way — every file present, and then an import that only happens
at runtime missing on the user's machine — which checking the folder contents
cannot catch. CI runs it against the built Windows executable. Since a windowed
Windows build has no console, `--selftest-out <path>` writes the report to a
file.

The Windows portable build is produced by
[`.github/workflows/build-windows.yml`](.github/workflows/build-windows.yml) on
every push to `main`, and attached to a GitHub Release when a `v*` tag is
pushed. PyInstaller cannot cross-compile, so the `.exe` must be built on
Windows; that workflow is the only supported way to produce it.

---

## Using it

1. Add your Kaggle token once, under the settings button. The app offers this as
   the first thing it asks for.
2. Choose an audio file. If the audio lives in an edit, export or bounce it
   first — any of the listed formats will do.
3. Press **Make subtitles**. Expect several minutes: upload, GPU queue,
   transcription, alignment. The page shows which stage it is on and how long
   each one took; the raw log is one click away.
4. When it finishes you see the actual cues, each in its own script and
   direction, and the file to drag in. **Show subtitle file** opens the folder
   with it selected.

Cue times are relative to the start of the audio file, so drop the `.srt` at the
same point on the timeline that the audio starts.

---

## How cues are routed

Stock Whisper picks **one** language for an entire file, from its opening
window. On bilingual audio that is not a small inaccuracy: the losing language
is *translated* into the winning one's script rather than transcribed. Measured
on a real 27-second EN/AR clip, global auto-detect returned Arabic at p=0.89 and
rendered the English narration as Arabic text.

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

Every number above is scored against hand-marked language spans, kept as
`tests/fixtures/codeswitch_ground_truth.json`.

The honest limit: a subtitle track carries one font, so an English sentence with
an Arabic word inline renders entirely in one track's typeface. True per-word
font mixing needs styled titles rather than subtitle cues, which is a much
heavier approach and is not what this builds.

---

## Layout

```
app.py                     entry point
app.spec                   PyInstaller bundle definition
assets/                    the Krevon mark, and the .icns / .ico built from it
resolve_subtitle_tool/
  main.py                  opens the pywebview window
  api_bridge.py            the js_api object exposed to the frontend
  pipeline.py              audio file -> Kaggle -> SRTs on disk
  kaggle_runner.py         Kaggle: dataset, kernel, polling, download
  speechmatics_runner.py   the paid alternative backend
  subtitle_utils.py        cue model, Arabic routing, SRT writing
  config.py                persisted settings and credentials
  window_chrome.py         custom title bar on Windows (frameless)
  kaggle_kernel/
    transcribe_kernel.py   runs on Kaggle, not locally
frontend/                  React + Tailwind, rendered in pywebview
  src/lib/stages.ts        maps the backend's log lines onto run stages
scripts/
  build.py                 frontend + bundle build
  make_icons.py            SVG -> .icns / .ico
  probe_*.py               the Resolve API experiments, kept as a record
tests/                     no network, no GPU, no editor needed
docs/RESOLVE_API_FINDINGS.md
docs/TRANSCRIPTION_FINDINGS.md
```

The package is still called `resolve_subtitle_tool` for the same reason the
probe scripts are still here: renaming it churns every import, the PyInstaller
spec and the settings-migration path, for a directory name no user ever sees.

`subtitle_utils.py` is dependency-free and holds the routing logic, so the test
suite runs anywhere without a GPU or network access.

Settings live in the platform's per-user config directory, under
`Krevon Scribe`. Settings written by the earlier `ResolveSubtitleTool` builds
are still read, so upgrading does not reset your setup.

---

## Troubleshooting

**The Kaggle kernel fails** — the log links the kernel page; its output shows
whether the GPU quota is exhausted or the model download failed. Kaggle allows
roughly 30 GPU-hours a week.

**The window opens but stays on "Starting up…"** — the app retries the startup
handshake and then shows the actual error with a Try again button.

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

**Windows: the app freezes for twenty seconds on every page load** — fixed.
pywebview builds its JavaScript bridge by walking every public attribute of the
`Api` object and recursing into any that is a plain object. The native window
was reachable that way, and the .NET graph behind it returns a new object on
every read, so pywebview's `id()`-based cycle guard never fired and the walk ran
until the stack was exhausted. Attributes on `Api` that are not meant for
JavaScript must start with an underscore; `tests/test_api_bridge.py` enforces it.

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
