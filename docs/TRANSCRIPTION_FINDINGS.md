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

The real structure was later marked by hand in Resolve by the project owner and
is kept as `tests/fixtures/codeswitch_ground_truth.json`. It is the authority
every number below is scored against:

| Time | Language |
|---|---|
| 0.000–6.250 s | English |
| 6.250–11.333 s | Arabic |
| 11.333–14.500 s | English |
| 14.583–18.417 s | Arabic |
| 18.667–26.583 s | English |
| 26.667–27.375 s | Arabic |

My earlier estimate of these spans, inferred from windowed detection, was wrong
at every boundary — it put the first switch at 4.0 s rather than 6.25 s and
missed the final Arabic word entirely, calling it English ("Nothing." is in fact
`ولا شيء`). Scoring against inferred ground truth had been flattering the
detector to itself.

## A fine-tuned code-switch checkpoint beats all of the above

Stock whisper commits to one language per file and *translates* the rest, so
everything above is machinery for working around that. Checkpoints fine-tuned on
code-switched Arabic/English do not have the problem: they write Arabic speech
in Arabic script and English in Latin, in the same sentence. The language can
then be **read off the transcript** instead of inferred.

Scored per 10 ms against the hand-marked spans:

| Route | Language accuracy |
|---|---|
| `large-v2` + `large-v3` confidence spans (6 runs) | **65–78%**, varying run to run |
| `IbrahimAmin/code-switched-egyptian-arabic-whisper-small` | 93.5% |
| `Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched` | **94.7%** |

End to end on the timeline the chosen model scores **96.1%**, recovers exactly
six spans matching the six marked ones, and misroutes no cue at all — the only
remaining error is silence between cues that no cue covers.

At a switch the model sometimes emits the last word of one language and the
first of the next as a single token, ` secret؟هيكون`, having never seen a space
between them. Splitting such tokens at the script boundary and apportioning the
time by character count is worth **+1.4 points** on its own (94.7% → 96.1%), and
stops two sentences being welded into one cue.

What the difference looks like in the text, same audio:

- stock `large-v2` forced to Arabic: `حسناً, الآن حان الوقت للحمام البقر` — a
  hallucinated "pigeon-cow bath"; the English words are translated away.
- code-switch checkpoint: `Okay, so now time for the chickens, بدنا نحمل ال
  chickens, ال chicken bath.` — the English is kept as English.

The dialect is Levantine (`بدنا`, `هيكون`, `مافي`), not the Egyptian the model
card advertises, and it transcribes it anyway.

Both checkpoints are Apache-2.0. They ship in transformers format, so the kernel
converts to CTranslate2 on the fly (51 s for the medium model) into `/tmp` —
not `/kaggle/working`, which would be downloaded back as gigabytes of "results".

### Cleaning up the script runs

Grouping words by script leaves the occasional mis-scripted word mid-sentence. A
short run is absorbed only when the *same* language sits on both sides of it, so
that it is genuinely an interruption:

| Minimum run | Absorb any short run | Absorb interruptions only |
|---|---|---|
| 0.5 s | 86.7% | 87.6% |
| 1.0 s | 93.8% | **94.7%** |
| 1.5 s | 93.8% | **94.7%** |
| 3.0 s | 93.8% | **94.7%** |

Absorbing indiscriminately erases the real 0.71 s Arabic run that ends the clip,
because it is shorter than the threshold; requiring matching neighbours protects
it, since an edge run has nothing to interrupt. The default is 1.5 s, the middle
of the flat 1.0–3.0 s plateau.

## Whisper's timestamps drift; forced alignment fixes it

The render is not the problem: cross-correlating Resolve's rendered audio
against the source video gives a **0 ms** offset. Whisper *infers* timestamps
from its own decoder rather than measuring them, and they drift.

Cue text is therefore re-timed against the audio with torchaudio's `MMS_FA` CTC
aligner. uroman transliterates both scripts, so one pass handles the bilingual
transcript rather than one pass per language.

| Transcription route | Median correction | Worst |
|---|---|---|
| `large-v2` + `large-v3` confidence spans | 0.306 s | 2.526 s |
| code-switch checkpoint | 0.065 s | 0.320 s |

The second row is the more interesting one: the fine-tuned model's own
timestamps are already close, and alignment mostly confirms them. The 2.5 s
worst case in the first row is what "the subtitles don't match the audio" was.

Kaggle hands out P100s (sm_60) and recent torch builds ship no kernels for that
architecture, so `torch.cuda.is_available()` returns True and the first CUDA op
then dies with "no kernel image is available". The device is probed with a
throwaway op instead; alignment falls back to CPU, which costs seconds at this
length. CTranslate2 is unaffected — it carries its own kernels, which is why
faster-whisper runs on the GPU regardless.

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
