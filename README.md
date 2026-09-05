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

Both languages go into **one** subtitle track, in time order. That is not a
compromise, it is the only arrangement that works: Resolve displays a single
subtitle track at a time, and it routes every programmatic append to the
already-populated track, so a second track could never be filled automatically
anyway. One track also means one font — pick one that covers Arabic and Latin
(Geeza Pro, Noto Sans Arabic) and set it in the Inspector, because Resolve
exposes no font API.

Set `single_track = false` to get the old behaviour instead: the primary
language placed automatically and the second staged in the Media Pool for you to
drag onto its own track.

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
one track carries one font. Set `cue_script_policy = "mixed"` to keep such a
sentence whole instead, at the cost of cues that mix Arabic and Latin.

Set `code_switch_method = "confidence"` to fall back to the older route (stock
whisper run four times, language inferred from decoder confidence). It scores
65–78% against the same spans and varies between runs, so it is only worth
reaching for if Hugging Face is unreachable.

`speechmatics` is the paid alternative, and needs less machinery still, because Melia
tags every word with the language it was spoken in — the split becomes a lookup
rather than an inference. It has not been run against real audio yet: the code and its
tests exist, but nobody has supplied an API key.

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

### Checking a build

```bash
python app.py --selftest          # or: ResolveSubtitles.exe --selftest
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

Whisper picks **one** language for an entire file, from its opening window. On a
bilingual timeline that is not a small inaccuracy: the losing language is
*translated* into the winning one's script rather than transcribed, so every cue
ends up on a single track and the tool does nothing useful. Measured on a real
27-second EN/AR clip, global auto-detect returned Arabic at p=0.89 and rendered
the English narration as Arabic text.

So the kernel segments by language first. It runs detection over overlapping
4-second windows, accumulates each window's probabilities into 1-second slots
weighted toward the window centre, and forces the winning language per span when
transcribing. Two details carry their weight:

- **Centre weighting**, because a flat vote across the window dilates every
  boundary by half a window and decodes the tail of an English sentence as
  Arabic.
- **Accumulating probabilities rather than median-filtering labels**, because a
  median filter erases a real switch that happens to be one slot wide — which is
  exactly what a short Arabic line between two English ones looks like.

Spans are decoded with two seconds of neighbouring audio for context and
segments whose midpoint falls outside the span are dropped. Whisper is markedly
worse on a bare two-second island than on the same words in context.

Only the candidate languages you configure are considered. Unrestricted
detection wanders off to Spanish or Tagalog on accented or noisy windows.

Routing to tracks then works on the text itself: the tool counts letters in
Arabic Unicode blocks against total letters, ignoring digits, punctuation and
whitespace, and compares the ratio to your threshold. Once each span is
transcribed in its own language, script and language agree.

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
