"""Runs ON Kaggle, not locally.

Reads the audio file and job settings from the attached dataset, transcribes with
faster-whisper on the GPU, and writes ``/kaggle/working/segments.json`` as a list
of ``{"start": float, "end": float, "text": str}`` objects.

Requires the kernel to have GPU and internet enabled: internet is needed both to
pip-install faster-whisper and to pull the model weights on first run.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Overridable so the kernel logic can be exercised off Kaggle.
INPUT_ROOT = Path(os.environ.get("TRANSCRIBE_INPUT", "/kaggle/input"))
WORKING = Path(os.environ.get("TRANSCRIBE_OUTPUT", "/kaggle/working"))
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff"}

DEFAULTS = {
    # large-v2 writes better text than v3 on this material; v3 is the better
    # language *detector*. See docs/TRANSCRIPTION_FINDINGS.md for the numbers.
    "model": "large-v2",
    "detect_model": "large-v3",
    "language": "auto",      # "auto", or an ISO code such as "ar" / "en"
    "beam_size": 5,
    "vad_filter": True,
    "word_timestamps": False,
    "compute_type": "float16",
    "initial_prompt": "",
    # Code-switching: decide the language per region and force it there, rather
    # than letting whisper pick one language for the whole file.
    "code_switch": True,
    "languages": ["en", "ar"],
    # "model" transcribes once with a checkpoint fine-tuned on code-switched
    # Arabic/English, which writes each word in the script it was spoken in, so
    # the language is read off the text. "confidence" is the older route: two
    # models, four forced-language passes, language inferred from which decoder
    # was more sure. Scored against hand-marked spans on the test clip: 94.7%
    # for "model", 65-78% for "confidence". See docs/TRANSCRIPTION_FINDINGS.md.
    "code_switch_method": "model",
    "cs_model": "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched",
    "cs_language": "ar",
    # Shortest script run kept when it interrupts a longer stretch of the other
    # language. Below ~1s the merge is measurably worse; 1.0-3.0 all score the
    # same, so this sits in the middle of that plateau.
    "min_run": 1.5,
    "conf_slot": 0.25,
    "conf_smooth": 2.0,
    "min_span": 1.5,
    "max_gap": 0.8,
    "max_chars": 84,
    "max_duration": 6.0,
    "min_cue_duration": 0.25,
    # Forced alignment: whisper's own word times drift, so the cue text is
    # re-timed against the audio by a CTC aligner afterwards.
    "align": True,
    "align_chunk": 120.0,
    "align_pad": 2.0,
}


def log(msg):
    print(f"[transcribe] {msg}", flush=True)


def _pip(*packages):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", *packages]
    )


def ensure_dependency():
    try:
        import faster_whisper  # noqa: F401
        log("faster-whisper already present")
    except ImportError:
        log("installing faster-whisper…")
        _pip("faster-whisper")


def ensure_aligner_dependency():
    """uroman only; torchaudio ships with the Kaggle image and carries MMS_FA."""
    try:
        import uroman  # noqa: F401
        log("uroman already present")
    except ImportError:
        log("installing uroman…")
        _pip("uroman")


def find_inputs():
    """Locate the audio file and optional job.json inside the attached dataset."""
    if not INPUT_ROOT.is_dir():
        raise SystemExit(f"No dataset mounted at {INPUT_ROOT}")

    audio, job = None, {}
    for path in sorted(INPUT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "job.json":
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                log(f"ignoring unreadable job.json: {exc}")
        elif path.suffix.lower() in AUDIO_SUFFIXES and audio is None:
            audio = path

    if audio is None:
        found = [str(p.relative_to(INPUT_ROOT)) for p in INPUT_ROOT.rglob("*") if p.is_file()]
        raise SystemExit(f"No audio file found in the dataset. Contents: {found}")

    settings = dict(DEFAULTS)
    settings.update({k: v for k, v in job.items() if k in DEFAULTS})
    return audio, settings


def _gpu_name() -> str:
    try:
        import torch
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"
    except Exception:
        return "unknown"


def _compute_candidates(preferred: str, device: str, has_gpu: bool) -> list:
    """Order compute types best-first, filtered to what this device supports.

    Kaggle hands out either a T4 (compute 7.5, real float16) or a P100
    (compute 6.0, which CTranslate2 rejects for float16). Asking the runtime
    what it supports beats guessing from the GPU name.
    """
    if not has_gpu:
        return ["int8", "float32"]
    ladder = [preferred, "float16", "int8_float16", "bfloat16", "float32", "int8"]
    ordered = []
    for c in ladder:
        if c and c not in ordered:
            ordered.append(c)
    try:
        import ctranslate2
        supported = set(ctranslate2.get_supported_compute_types(device))
        log(f"supported compute types on {device}: {sorted(supported)}")
        filtered = [c for c in ordered if c in supported]
        if filtered:
            return filtered
    except Exception as exc:
        log(f"could not query supported compute types ({exc}); trying the full ladder")
    return ordered


def _load_model(WhisperModel, settings, device, has_gpu, name=None):
    """Load a model, stepping down the compute-type ladder on rejection."""
    name = name or settings["model"]
    candidates = _compute_candidates(settings.get("compute_type"), device, has_gpu)
    last = None
    for compute_type in candidates:
        try:
            return WhisperModel(name, device=device,
                                compute_type=compute_type), compute_type
        except ValueError as exc:
            log(f"compute_type={compute_type} rejected: {exc}")
            last = exc
    raise RuntimeError(f"No usable compute type on {device}. Last error: {last}")


def _release(model):
    """Free a model's GPU memory before loading the next one."""
    try:
        del model
        import gc
        gc.collect()
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


# ------------------------------------------------- code-switch by script

# Same ranges as subtitle_utils.is_arabic_char. Duplicated rather than imported
# because this file is uploaded to Kaggle on its own, with no package around it.
_ARABIC_RANGES = (
    (0x0600, 0x06FF), (0x0750, 0x077F), (0x0870, 0x089F), (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF), (0xFE70, 0xFEFF), (0x10EC0, 0x10EFF),
)
_ARABIC_DIGITS = set(range(0x0660, 0x066A)) | set(range(0x06F0, 0x06FA))


def word_language(word, languages=("en", "ar")):
    """Which language a word is written in, or None if it carries no script.

    A code-switch checkpoint writes each word in the script it was spoken in, so
    this reads the language off the transcript instead of inferring it. Digits
    and punctuation are script-neutral and return None, so "؟" or "2024" does
    not start a new run on its own.
    """
    import unicodedata

    letters = [c for c in word
               if not c.isspace()
               and ord(c) not in _ARABIC_DIGITS
               and unicodedata.category(c).startswith("L")]
    if not letters:
        return None
    arabic = sum(1 for c in letters
                 if any(lo <= ord(c) <= hi for lo, hi in _ARABIC_RANGES))
    ar = "ar" if "ar" in languages else languages[-1]
    en = "en" if "en" in languages else languages[0]
    return ar if arabic * 2 >= len(letters) else en


def script_runs(words, min_run, languages=("en", "ar")):
    """Group words into runs of a single script, then drop momentary flickers.

    What is left to clean up is noise, not ambiguity: one mis-scripted word in
    the middle of a sentence. A short run is absorbed only when the *same*
    language sits on both sides of it — that is what makes it an interruption.
    A short run at either end is kept, because a genuine switch in the last
    second of a clip has nothing to interrupt and would otherwise be erased.
    """
    runs = []
    for word in words:
        lang = word_language(word["word"], languages)
        if lang is None:
            lang = runs[-1][2] if runs else languages[0]
        if runs and runs[-1][2] == lang:
            runs[-1][1] = float(word["end"])
        else:
            runs.append([float(word["start"]), float(word["end"]), lang])

    changed = True
    while changed and len(runs) > 2:
        changed = False
        for i in range(1, len(runs) - 1):
            if runs[i][1] - runs[i][0] < min_run and runs[i - 1][2] == runs[i + 1][2]:
                runs[i - 1][1] = runs[i + 1][1]
                del runs[i:i + 2]
                changed = True
                break
    return [(a, b, lang) for a, b, lang in runs]


def _ensure_ct2_model(repo):
    """Return a path faster-whisper can load, converting from transformers if needed.

    The code-switch checkpoints are published in transformers format and
    faster-whisper only loads CTranslate2, so they are converted on the fly
    (about a minute for the medium model). The output goes to /tmp rather than
    the kernel's working directory, which would otherwise be downloaded as
    several gigabytes of kernel "results".
    """
    if "/" not in repo:
        return repo                      # a plain whisper size like "large-v2"
    target = Path("/tmp") / ("ct2-" + repo.replace("/", "--"))
    if (target / "model.bin").is_file():
        log(f"reusing converted model at {target}")
        return str(target)
    try:
        import transformers  # noqa: F401
    except ImportError:
        log("installing transformers for the checkpoint conversion…")
        _pip("transformers")
    log(f"converting {repo} to CTranslate2 (about a minute)…")
    started = time.time()
    subprocess.check_call([
        "ct2-transformers-converter", "--model", repo,
        "--output_dir", str(target), "--force", "--quantization", "float32",
    ])
    log(f"converted in {time.time() - started:.1f}s")
    return str(target)


def transcribe_with_code_switch_model(WhisperModel, settings, device, has_gpu, pcm, sr):
    """One pass with a checkpoint that already writes both languages.

    The older route ran four forced-language passes and guessed the language
    from decoder confidence, because stock whisper commits to one language per
    file and *translates* the rest. A fine-tuned code-switch checkpoint does not:
    it emits Arabic script for Arabic speech and Latin for English, in the same
    sentence, so one pass gives both the text and the language.
    """
    languages = tuple(str(l) for l in settings["languages"])
    path = _ensure_ct2_model(str(settings["cs_model"]))
    model, compute_type = _load_model(WhisperModel, settings, device, has_gpu, path)
    log(f"code-switch model loaded (compute_type={compute_type})")

    language = settings["cs_language"] or None
    words = _pass_words(model, pcm, language, settings)
    log(f"  {len(words)} words")

    runs = script_runs(words, float(settings["min_run"]), languages)
    for a, b, lang in runs:
        log(f"  run {a:6.2f}-{b:6.2f}s -> {lang}")

    def owner(t):
        for a, b, lang in runs:
            if a <= t < b:
                return lang
        return runs[-1][2] if runs else languages[0]

    words_by_lang = {}
    for word in words:
        lang = owner((float(word["start"]) + float(word["end"])) / 2.0)
        words_by_lang.setdefault(lang, []).append(word)

    return cues_from_words(words_by_lang, runs, settings), runs


def language_spans_from_words(words_by_lang, total, settings):
    """Decide which language owns each moment, from per-word confidences.

    Each candidate language has already transcribed the whole file, so for any
    instant we can ask which language's decoder was more sure of itself. That
    beats a standalone language detector on two counts: the confidences come
    from the same acoustic model that will produce the subtitles, and *silence*
    is evidence — where a decoder emitted no words at all, it is telling us the
    audio is not its language.

    Pure arithmetic over word lists, so it can be tested without a GPU.
    """
    langs = list(words_by_lang)
    slot = float(settings["conf_slot"])
    smooth = float(settings["conf_smooth"])
    if total <= 0 or not langs:
        return [(0.0, max(total, 0.0), (langs or ["en"])[0])]

    n = max(1, int(total / slot + 0.999))
    conf = {}
    for lang, words in words_by_lang.items():
        acc = [0.0] * n
        cnt = [0] * n
        for w in words:
            i0 = max(0, int(w["start"] / slot))
            i1 = min(n, max(i0 + 1, int(w["end"] / slot + 0.999)))
            for i in range(i0, i1):
                acc[i] += float(w["probability"])
                cnt[i] += 1
        # No word here means this decoder heard nothing it recognised: score 0,
        # not "unknown". That is what separates the two languages in practice.
        conf[lang] = [acc[i] / cnt[i] if cnt[i] else 0.0 for i in range(n)]

    half = max(1, int((smooth / slot) / 2))
    smoothed = {}
    for lang, series in conf.items():
        out = []
        for i in range(n):
            lo, hi = max(0, i - half), min(n, i + half + 1)
            window = series[lo:hi]
            out.append(sum(window) / len(window))
        smoothed[lang] = out

    labels = []
    for i in range(n):
        best = max(langs, key=lambda l: smoothed[l][i])
        if smoothed[best][i] <= 0.0:
            best = labels[-1] if labels else langs[0]
        labels.append(best)

    spans = []
    for i, lang in enumerate(labels):
        a, b = i * slot, min(total, (i + 1) * slot)
        if spans and spans[-1][2] == lang:
            spans[-1][1] = b
        else:
            spans.append([a, b, lang])
    spans[0][0] = 0.0
    spans[-1][1] = total

    min_span = float(settings["min_span"])
    merged = []
    for span in spans:
        if merged and (span[1] - span[0]) < min_span:
            merged[-1][1] = span[1]
        else:
            merged.append(span)
    while len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_span:
        merged[1][0] = merged[0][0]
        merged.pop(0)

    final = []
    for span in merged:
        if final and final[-1][2] == span[2]:
            final[-1][1] = span[1]
        else:
            final.append(span)
    return [(a, b, lang) for a, b, lang in final]


def cues_from_words(words_by_lang, spans, settings):
    """Rebuild cues from the words each language owns.

    Whisper's own segment boundaries are placed for readability and pay no
    attention to where the speaker switched language, so a segment routinely
    straddles a switch. Keeping or dropping such a segment whole is wrong both
    ways: dropping it loses a real sentence, keeping it drags in text the model
    hallucinated over the other language's audio. Selecting at word level cuts
    exactly at the switch.

    Cues break on a span boundary, on a pause longer than ``max_gap``, at
    sentence-ending punctuation, and before a cue grows past ``max_chars`` or
    ``max_duration``. Times come from the words themselves, never from the span
    grid.
    """
    max_gap = float(settings["max_gap"])
    max_chars = int(settings["max_chars"])
    max_duration = float(settings["max_duration"])
    sentence_end = tuple(".!?\u061f\u06d4\u2026")

    def owner(t):
        for a, b, lang in spans:
            if a <= t < b:
                return lang
        return spans[-1][2] if spans else None

    cues = []
    for lang, words in words_by_lang.items():
        current = []
        for word in words:
            start_t, end_t = float(word["start"]), float(word["end"])
            if end_t <= start_t:
                continue
            if owner((start_t + end_t) / 2.0) != lang:
                if current:
                    cues.append(_finish_cue(current, lang))
                    current = []
                continue
            if current:
                previous = current[-1]
                text_so_far = "".join(w["word"] for w in current).strip()
                if (
                    start_t - float(previous["end"]) > max_gap
                    or len(text_so_far) >= max_chars
                    or end_t - float(current[0]["start"]) > max_duration
                    or text_so_far.endswith(sentence_end)
                ):
                    cues.append(_finish_cue(current, lang))
                    current = []
            current.append(word)
        if current:
            cues.append(_finish_cue(current, lang))

    # A tenth-of-a-second cue is unreadable, and it is usually whisper's
    # end-of-audio artefact ("You", "Thank you") rather than speech.
    floor = float(settings["min_cue_duration"])
    cues = [c for c in cues if c["text"] and (c["end"] - c["start"]) >= floor]
    cues.sort(key=lambda c: (c["start"], c["language"]))
    return cues


# Punctuation that belongs to the *previous* sentence. A cue break lands
# between a word and the stop that follows it, so the stop would otherwise open
# the next cue (".In this episode…").
_LEADING_PUNCTUATION = " .,;:!?\u060c\u061b\u061f\u06d4\u2026-"


def _finish_cue(words, lang):
    text = "".join(w["word"] for w in words).lstrip(_LEADING_PUNCTUATION).strip()
    return {
        "start": round(float(words[0]["start"]), 3),
        "end": round(float(words[-1]["end"]), 3),
        "text": text,
        "language": lang,
    }


# --------------------------------------------------------------- alignment

# The MMS aligner's dictionary is lowercase Latin plus an apostrophe: nothing else.
_ROMAN_KEEP = re.compile(r"[^a-z']")


def _make_romaniser():
    """Return a callable that transliterates any script into Latin.

    uroman covers both of our scripts in one call — Arabic is transliterated and
    Latin passes through nearly unchanged — which is what lets a *bilingual*
    transcript be aligned in a single pass instead of one pass per language.
    """
    import uroman as uroman_module

    instance = uroman_module.Uroman()
    return instance.romanize_string


def _romanised(word, romanise):
    try:
        text = romanise(word)
    except Exception:
        text = word
    return _ROMAN_KEEP.sub("", str(text).lower())


def _chunk_cues(cues, order, chunk_seconds):
    """Group cues into windows no longer than ``chunk_seconds``.

    Aligning a whole feature-length timeline in one pass would blow up memory,
    and a local window also stops one bad match from dragging the rest with it.
    """
    chunks, current = [], []
    for i in order:
        if current and cues[i]["end"] - cues[current[0]]["start"] > chunk_seconds:
            chunks.append(current)
            current = []
        current.append(i)
    if current:
        chunks.append(current)
    return chunks


def _alignment_device(torch, device):
    """Pick a device torch can actually execute on.

    CTranslate2 running on the GPU says nothing about torch: Kaggle hands out
    P100s (sm_60), and recent torch builds ship no kernels for them, so the
    first CUDA op dies with "no kernel image is available". Probe with a
    throwaway op instead of trusting ``cuda.is_available()``.
    """
    if device != "cuda":
        return "cpu"
    try:
        torch.zeros(8, device="cuda").add_(1).cpu()
        return "cuda"
    except Exception as exc:
        log(f"  torch cannot use this GPU ({exc}); aligning on CPU instead")
        return "cpu"


def align_cues(cues, pcm, sr, settings, device):
    """Re-time cues against the audio using CTC forced alignment.

    Whisper *infers* timestamps from its own decoder rather than measuring them,
    and they drift — which is exactly what makes subtitles land off the speech.
    Forced alignment asks a different question: given text we already trust,
    where in the audio does each word actually occur? Only start/end change here;
    the text is never touched.

    Any chunk that fails keeps whisper's original times, because a confidently
    wrong alignment is worse than a drifting one.
    """
    stats = {"aligned": 0, "kept": 0, "chunks": 0}
    if not cues:
        return cues, stats

    import numpy as np
    import torch
    from torchaudio.pipelines import MMS_FA as bundle

    romanise = _make_romaniser()
    device = _alignment_device(torch, device)
    stats["device"] = device
    model = bundle.get_model().to(device)
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()

    order = sorted(range(len(cues)), key=lambda i: cues[i]["start"])
    words_by_cue = {}
    for i in order:
        romanised = [_romanised(tok, romanise) for tok in cues[i]["text"].split()]
        words_by_cue[i] = [r for r in romanised if r]

    total = len(pcm) / sr
    pad = float(settings["align_pad"])
    aligned = {}

    for chunk in _chunk_cues(cues, order, float(settings["align_chunk"])):
        entries = [(i, r) for i in chunk for r in words_by_cue[i]]
        if not entries:
            continue
        stats["chunks"] += 1
        a = max(0.0, min(cues[i]["start"] for i in chunk) - pad)
        b = min(total, max(cues[i]["end"] for i in chunk) + pad)
        slice_ = pcm[int(a * sr):int(b * sr)]
        if len(slice_) < sr // 10:
            continue
        try:
            waveform = torch.from_numpy(np.ascontiguousarray(slice_)).unsqueeze(0)
            with torch.inference_mode():
                emission, _ = model(waveform.to(device))
                spans = aligner(emission[0], tokenizer([r for _, r in entries]))
            # The model strides the waveform, so frame indices map back to
            # samples through this ratio rather than a fixed hop.
            ratio = waveform.size(1) / emission.size(1)
        except Exception as exc:
            log(f"  alignment failed for {a:.1f}-{b:.1f}s, keeping whisper times: {exc}")
            continue

        per_cue = {}
        for (index, _), span in zip(entries, spans):
            start = a + ratio * span[0].start / sr
            end = a + ratio * span[-1].end / sr
            lo, hi = per_cue.get(index, (start, end))
            per_cue[index] = (min(lo, start), max(hi, end))
        for index, (start, end) in per_cue.items():
            if end > start:
                aligned[index] = (start, end)

    out = []
    for i, cue in enumerate(cues):
        new = dict(cue)
        times = aligned.get(i)
        if times:
            shift = times[0] - cue["start"]
            new["start"], new["end"] = round(times[0], 3), round(times[1], 3)
            new["shift"] = round(shift, 3)
            stats["aligned"] += 1
        else:
            stats["kept"] += 1
        out.append(new)
    out.sort(key=lambda c: (c["start"], c.get("language", "")))

    shifts = [abs(c["shift"]) for c in out if "shift" in c]
    if shifts:
        stats["median_shift"] = round(sorted(shifts)[len(shifts) // 2], 3)
        stats["max_shift"] = round(max(shifts), 3)
    return out, stats


def _pass_words(model, audio, lang, settings, offset=0.0):
    """One forced-language decode, returned as absolute-timed words."""
    segments, _ = model.transcribe(
        audio,
        language=lang,
        beam_size=int(settings["beam_size"]),
        vad_filter=bool(settings["vad_filter"]),
        word_timestamps=True,          # required: drives both the language
        initial_prompt=settings["initial_prompt"] or None,   # decision and cues
        condition_on_previous_text=False,
    )
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"start": offset + w.start, "end": offset + w.end,
                          "probability": w.probability, "word": w.word})
    return words


def transcribe_code_switched(WhisperModel, settings, device, has_gpu, pcm, sr):
    """Find the language spans with one model, then transcribe them with another.

    Two models because the jobs want opposite things. Detection needs a model
    that is *unconvincing* on the wrong language — that lack of confidence is
    the whole signal — and large-v3 is, while large-v2 fluently translates in
    either direction and so cannot tell them apart. Transcription just wants the
    best text, which is large-v2. Smaller models are not an option for the
    detection half: medium collapses to a single span and small misplaces the
    boundaries badly.

    When both names match, the detection passes are reused and nothing is
    decoded twice.
    """
    total = len(pcm) / sr
    langs = [str(l) for l in settings["languages"]]
    detect_name = str(settings["detect_model"] or settings["model"])
    transcribe_name = str(settings["model"])

    model, compute_type = _load_model(WhisperModel, settings, device, has_gpu, detect_name)
    log(f"detection model {detect_name} loaded (compute_type={compute_type})")
    words_by_lang = {}
    for lang in langs:
        words_by_lang[lang] = _pass_words(model, pcm, lang, settings)
        log(f"  {detect_name}/{lang}: {len(words_by_lang[lang])} words")

    spans = language_spans_from_words(words_by_lang, total, settings)
    for a, b, lang in spans:
        log(f"  span {a:6.2f}-{b:6.2f}s -> {lang}")

    if transcribe_name != detect_name:
        _release(model)
        model, compute_type = _load_model(
            WhisperModel, settings, device, has_gpu, transcribe_name
        )
        log(f"transcription model {transcribe_name} loaded (compute_type={compute_type})")
        # Full file per language, not span by span. Decoding just a span is
        # cheaper but measurably worse: on an eight-second slice large-v2
        # returned seven words where the same audio inside the whole file gave a
        # complete sentence. Whisper needs the surrounding context.
        words_by_lang = {}
        for lang in langs:
            words_by_lang[lang] = _pass_words(model, pcm, lang, settings)
            log(f"  {transcribe_name}/{lang}: {len(words_by_lang[lang])} words")

    return cues_from_words(words_by_lang, spans, settings), spans


def main():
    ensure_dependency()
    from faster_whisper import WhisperModel

    audio, settings = find_inputs()
    log(f"audio: {audio.name} ({audio.stat().st_size / 1e6:.1f} MB)")
    log(f"settings: {settings}")

    # Fall back to CPU so the job still produces output if no GPU was attached.
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except Exception:
        has_gpu = False
    device = "cuda" if has_gpu else "cpu"
    if not has_gpu:
        log("WARNING: no GPU visible — falling back to CPU, this will be slow.")
    log(f"device={device} gpu={_gpu_name()}")

    started = time.time()
    language = None if settings["language"] in ("auto", "", None) else settings["language"]
    code_switch = bool(settings["code_switch"]) and language is None
    sr = 16000
    pcm = None

    if code_switch:
        from faster_whisper import decode_audio

        pcm = decode_audio(str(audio), sampling_rate=sr)
        duration = len(pcm) / sr
        method = str(settings["code_switch_method"] or "model")
        log(f"code-switch pass ({method}) over {duration:.2f}s using {settings['languages']}")
        if method == "model":
            out, spans = transcribe_with_code_switch_model(
                WhisperModel, settings, device, has_gpu, pcm, sr
            )
        else:
            out, spans = transcribe_code_switched(
                WhisperModel, settings, device, has_gpu, pcm, sr
            )
        span_summary = [
            {"start": round(a, 2), "end": round(b, 2), "language": lang} for a, b, lang in spans
        ]
        counts = {}
        for seg in out:
            counts[seg["language"]] = counts.get(seg["language"], 0) + 1
        detected = max(counts, key=counts.get) if counts else (settings["languages"] or ["en"])[0]
        detected_p = None
    else:
        model, compute_type = _load_model(WhisperModel, settings, device, has_gpu)
        log(f"model loaded in {time.time() - started:.1f}s (compute_type={compute_type})")
        segments, info = model.transcribe(
            str(audio),
            language=language,
            beam_size=int(settings["beam_size"]),
            vad_filter=bool(settings["vad_filter"]),
            word_timestamps=bool(settings["word_timestamps"]),
            initial_prompt=settings["initial_prompt"] or None,
            # Stops whisper looping a hallucinated phrase across a long silence.
            condition_on_previous_text=False,
        )
        log(f"detected language: {info.language} (p={info.language_probability:.2f})")
        out = []
        for seg in segments:                # generator: consuming it does the work
            text = (seg.text or "").strip()
            if text:
                out.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                            "text": text, "language": info.language})
            if len(out) % 25 == 0 and out:
                log(f"  {len(out)} segments… ({seg.end:.0f}s of audio)")
        duration = info.duration
        span_summary = []
        detected = info.language
        detected_p = round(info.language_probability, 4)

    # Forced alignment last, so it re-times whichever path produced the cues.
    align_stats = {}
    if bool(settings["align"]) and out:
        try:
            ensure_aligner_dependency()
            if pcm is None:
                from faster_whisper import decode_audio

                pcm = decode_audio(str(audio), sampling_rate=sr)
            log("aligning cue text to the audio…")
            out, align_stats = align_cues(out, pcm, sr, settings, device)
            log(f"alignment: {align_stats}")
        except Exception as exc:
            # Whisper's drifting times still make usable subtitles; no alignment
            # at all is better than failing the whole run over it.
            log(f"WARNING: forced alignment unavailable, keeping whisper times: {exc}")
            align_stats = {"error": str(exc)}

    WORKING.mkdir(parents=True, exist_ok=True)
    (WORKING / "segments.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (WORKING / "meta.json").write_text(
        json.dumps(
            {
                "detected_language": detected,
                "language_probability": detected_p,
                "code_switch": code_switch,
                "spans": span_summary,
                "alignment": align_stats,
                "duration": round(duration, 3),
                "segment_count": len(out),
                "model": settings["model"],
                "device": device,
                "elapsed_seconds": round(time.time() - started, 1),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    log(f"wrote {len(out)} segments in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
