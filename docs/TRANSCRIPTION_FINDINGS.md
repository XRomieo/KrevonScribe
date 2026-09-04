# Transcription findings

Measured on a real 27.4 s bilingual EN/AR clip pulled from a Resolve timeline
(320 kbps AAC source, continuous background music, no silence below −35 dB
anywhere). Every number here came from a run on a Kaggle P100.

## Whisper picks one language for the whole file, and that breaks the tool

Global auto-detect returned **Arabic at p=0.89** and rendered the English
narration *as Arabic text* — "chicken bath" came back as `حمام الحمام`. Every
cue would have landed on the Arabic track.

`multilingual=True` did not help: it still reported one language for the file.
Per-VAD-region detection did not either, because with music under the whole clip
VAD sees a single 27 s speech region.

The real structure, established by windowed detection and confirmed
independently by word-confidence collapse in a forced-English pass:

| Time | Language |
|---|---|
| 0.0–4.0 s | English |
| 4.0–10.0 s | Arabic |
| 10.0–13.8 s | English |
| 13.8–17.5 s | Arabic |
| 18.0–27.4 s | English |

## Two models, because detection and transcription want opposite things

| Model | As detector | As transcriber |
|---|---|---|
| `small` | boundaries badly misplaced | — |
| `medium` | collapses to one English span | — |
| `large-v2` | **fails** — spans wildly wrong | **best text** |
| `large-v3` | **accurate to ~0.5 s** | weaker text |

`large-v2` fails at detection *because* it is good: it fluently translates in
either direction, so it is confident on both languages everywhere and the
confidences stop discriminating. `large-v3` is less willing to translate, and
that lack of confidence on the wrong language is the entire signal.

So detection runs on `large-v3` and transcription on `large-v2`.

## Decode the whole file, not the spans

Decoding only a span is cheaper and measurably worse. On the 4.75–9.5 s Arabic
span, `large-v2` returned **7 words** from a padded 8.75 s slice, against a full
sentence for the same audio inside a whole-file pass. Whisper needs the
surrounding context. Both models now read the entire file.

## Why the earlier cues were out of sync

Two bugs, both fixed:

1. Segments were clamped to their span (`min(b, end)`), so cue times snapped to
   the analysis grid — every subtitle landed on an integer second.
2. Selection was per whisper-segment. Whisper places segment boundaries for
   readability and ignores language switches, so a segment straddling a switch
   was either dropped whole (losing a real sentence) or kept whole (dragging in
   text hallucinated over the other language's audio).

Cues are now rebuilt from **words**, cut exactly at the switch, timed by the
words themselves.

## Parameters, and how they were chosen

- `conf_smooth = 2.0` — swept 1.0/1.5/2.0/3.0 against the clip. Span structure
  is stable across the whole range, so the algorithm is not sensitive to it;
  2.0 produced the fewest fragments and kept "There's a secret to chicken bath?"
  whole, which sharper settings truncate.
- Centre-weighted window votes, not flat — a flat vote dilates every boundary by
  half a window (truth 4–8 s came back as 2–10 s).
- Probability accumulation, not median-filtering of labels — a median filter
  erases a genuine switch one slot wide, which is exactly what the 13.8–17.5 s
  Arabic looked like.
- `min_cue_duration = 0.25` — removes whisper's end-of-audio artefact ("You",
  "Thank you"), which arrived at 0.1 s with word probability 0.03.

## Known limits

- One boundary fragment survives per switch in the worst case (a cue such as
  `البيضاء.` at 0.45 mean word probability). A confidence filter cannot remove
  it safely: the legitimate cue "Nothing." scores 0.41 on the same clip.
- Cost is four full-file passes plus two model loads: **~78–100 s of GPU for
  27 s of audio**, most of it fixed model-loading time. A long timeline scales
  roughly with duration; set `detect_model` equal to `model` to halve the work
  when the audio is monolingual.
- Arabic accuracy is limited by the source. This clip has music under every
  second of speech and short, accented, dialectal utterances.
