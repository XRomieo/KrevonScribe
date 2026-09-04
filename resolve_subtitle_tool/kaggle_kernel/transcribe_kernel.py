"""Runs ON Kaggle, not locally.

Reads the audio file and job settings from the attached dataset, transcribes with
faster-whisper on the GPU, and writes ``/kaggle/working/segments.json`` as a list
of ``{"start": float, "end": float, "text": str}`` objects.

Requires the kernel to have GPU and internet enabled: internet is needed both to
pip-install faster-whisper and to pull the model weights on first run.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Overridable so the kernel logic can be exercised off Kaggle.
INPUT_ROOT = Path(os.environ.get("TRANSCRIBE_INPUT", "/kaggle/input"))
WORKING = Path(os.environ.get("TRANSCRIBE_OUTPUT", "/kaggle/working"))
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff"}

DEFAULTS = {
    "model": "large-v3",
    "language": "auto",      # "auto", or an ISO code such as "ar" / "en"
    "beam_size": 5,
    "vad_filter": True,
    "word_timestamps": False,
    "compute_type": "float16",
    "initial_prompt": "",
    # Code-switching: detect language per window and force it per span, instead
    # of letting whisper pick one language for the whole file.
    "code_switch": True,
    "languages": ["en", "ar"],
    "detect_window": 4.0,
    "detect_hop": 1.0,
    "min_span": 1.5,
    "span_pad": 2.0,
}


def log(msg):
    print(f"[transcribe] {msg}", flush=True)


def ensure_dependency():
    try:
        import faster_whisper  # noqa: F401
        log("faster-whisper already present")
        return
    except ImportError:
        pass
    log("installing faster-whisper…")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "faster-whisper"]
    )


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


def _load_model(WhisperModel, settings, device, has_gpu):
    """Load the model, stepping down the compute-type ladder on rejection."""
    candidates = _compute_candidates(settings.get("compute_type"), device, has_gpu)
    last = None
    for compute_type in candidates:
        try:
            return WhisperModel(settings["model"], device=device,
                                compute_type=compute_type), compute_type
        except ValueError as exc:
            log(f"compute_type={compute_type} rejected: {exc}")
            last = exc
    raise RuntimeError(f"No usable compute type on {device}. Last error: {last}")


def detect_language_spans(model, pcm, sr, settings):
    """Map the audio to contiguous single-language spans.

    Whisper decides one language for the whole file from its first window, so a
    clip that switches between English and Arabic comes back entirely in one of
    them — the other language gets *translated* into that script rather than
    transcribed. Detecting per window and forcing the language per span is what
    keeps the two apart.

    Detection windows overlap and each one votes, weighted by its probability,
    into every slot it covers. Accumulating probabilities rather than smoothing
    hard labels matters: a median filter over labels erases a genuine switch
    that happens to be one slot wide, which is exactly how a short Arabic line
    between two English ones gets lost.

    Only the configured candidate languages are considered; unrestricted
    detection wanders off to Spanish or Tagalog on accented or noisy windows.
    """
    langs = [str(l) for l in settings["languages"]]
    win = float(settings["detect_window"])
    hop = float(settings["detect_hop"])
    total = len(pcm) / sr
    if total <= 0 or not langs:
        return [(0.0, max(total, 0.0), (langs or ["en"])[0])]

    n_slots = max(1, int(total / hop + 0.999))
    acc = [{l: 0.0 for l in langs} for _ in range(n_slots)]
    votes = [0] * n_slots

    t = 0.0
    while t < total:
        a, b = int(t * sr), min(len(pcm), int((t + win) * sr))
        if (b - a) / sr < 1.0:
            break
        try:
            _, _, all_probs = model.detect_language(audio=pcm[a:b])
        except Exception as exc:
            log(f"language detection failed at {t:.1f}s ({exc}); skipping window")
            t += hop
            continue
        if not isinstance(all_probs, dict):
            all_probs = {k: float(v) for k, v in (all_probs or [])}
        probs = {l: float(all_probs.get(l, 0.0)) for l in langs}
        # Weight the vote toward the window centre. A flat vote across the whole
        # window dilates every boundary by half a window, which would transcribe
        # the tail of an English sentence with Arabic forced (and vice versa).
        centre = (t + b / sr) / 2.0
        half = max((b / sr - t) / 2.0, 1e-6)
        first = int(t / hop)
        last = min(n_slots, int((b / sr) / hop + 0.999))
        for i in range(first, last):
            slot_centre = (i + 0.5) * hop
            weight = 1.0 - abs(slot_centre - centre) / half
            if weight <= 0.0:
                continue
            for l in langs:
                acc[i][l] += probs[l] * weight
            votes[i] += 1
        t += hop

    labels = []
    for i in range(n_slots):
        if votes[i]:
            labels.append(max(acc[i].items(), key=lambda kv: kv[1])[0])
        else:
            labels.append(labels[-1] if labels else langs[0])

    spans = []
    for i, lang in enumerate(labels):
        a = i * hop
        b = min(total, (i + 1) * hop)
        if spans and spans[-1][2] == lang:
            spans[-1][1] = b
        else:
            spans.append([a, b, lang])
    spans[0][0] = 0.0
    spans[-1][1] = total

    # Absorb spans too short to transcribe usefully into their neighbour.
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

    # A neighbour absorb can leave two same-language spans adjacent.
    final = []
    for span in merged:
        if final and final[-1][2] == span[2]:
            final[-1][1] = span[1]
        else:
            final.append(span)

    for a, b, lang in final:
        log(f"  span {a:6.2f}-{b:6.2f}s -> {lang}")
    return [(a, b, lang) for a, b, lang in final]


def transcribe_spans(model, pcm, sr, spans, settings):
    """Transcribe each span with its own language forced, then re-offset times.

    Each span is decoded with a little neighbouring audio included. Whisper is
    much weaker on a bare two-second island than on the same words with context
    around them, so the padding buys real accuracy; segments whose midpoint
    falls outside the span belong to the neighbour and are dropped.
    """
    total = len(pcm) / sr
    pad = float(settings["span_pad"])
    out = []
    for a, b, lang in spans:
        pa, pb = max(0.0, a - pad), min(total, b + pad)
        clip = pcm[int(pa * sr):int(pb * sr)]
        if len(clip) < sr // 2:
            continue
        segments, _ = model.transcribe(
            clip,
            language=lang,
            beam_size=int(settings["beam_size"]),
            vad_filter=bool(settings["vad_filter"]),
            word_timestamps=bool(settings["word_timestamps"]),
            initial_prompt=settings["initial_prompt"] or None,
            condition_on_previous_text=False,
        )
        kept = dropped = 0
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            start, end = pa + seg.start, pa + seg.end
            midpoint = (start + end) / 2.0
            if not (a <= midpoint < b):
                dropped += 1
                continue
            out.append({
                "start": round(max(a, start), 3),
                "end": round(min(b, end), 3),
                "text": text,
                "language": lang,
            })
            kept += 1
        log(f"  {lang} span {a:.2f}-{b:.2f}s -> {kept} segments ({dropped} from padding)")
    out.sort(key=lambda s: s["start"])
    return out


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
    model, compute_type = _load_model(WhisperModel, settings, device, has_gpu)
    log(f"model loaded in {time.time() - started:.1f}s (compute_type={compute_type})")

    language = None if settings["language"] in ("auto", "", None) else settings["language"]
    code_switch = bool(settings["code_switch"]) and language is None

    if code_switch:
        from faster_whisper import decode_audio

        sr = 16000
        pcm = decode_audio(str(audio), sampling_rate=sr)
        duration = len(pcm) / sr
        log(f"code-switch pass over {duration:.2f}s using {settings['languages']}")
        spans = detect_language_spans(model, pcm, sr, settings)
        out = transcribe_spans(model, pcm, sr, spans, settings)
        span_summary = [
            {"start": round(a, 2), "end": round(b, 2), "language": lang} for a, b, lang in spans
        ]
        counts = {}
        for seg in out:
            counts[seg["language"]] = counts.get(seg["language"], 0) + 1
        detected = max(counts, key=counts.get) if counts else (settings["languages"] or ["en"])[0]
        detected_p = None
    else:
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
