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

INPUT_ROOT = Path("/kaggle/input")
WORKING = Path("/kaggle/working")
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff"}

DEFAULTS = {
    "model": "large-v3",
    "language": "auto",      # "auto", or an ISO code such as "ar" / "en"
    "beam_size": 5,
    "vad_filter": True,
    "word_timestamps": False,
    "compute_type": "float16",
    "initial_prompt": "",
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
    compute_type = settings["compute_type"] if has_gpu else "int8"
    if not has_gpu:
        log("WARNING: no GPU visible — falling back to CPU, this will be slow.")
    log(f"device={device} compute_type={compute_type}")

    started = time.time()
    model = WhisperModel(settings["model"], device=device, compute_type=compute_type)
    log(f"model loaded in {time.time() - started:.1f}s")

    language = None if settings["language"] in ("auto", "", None) else settings["language"]
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
    for seg in segments:                    # generator: consuming it does the work
        text = (seg.text or "").strip()
        if text:
            out.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": text})
        if len(out) % 25 == 0 and out:
            log(f"  {len(out)} segments… ({seg.end:.0f}s of audio)")

    WORKING.mkdir(parents=True, exist_ok=True)
    (WORKING / "segments.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (WORKING / "meta.json").write_text(
        json.dumps(
            {
                "detected_language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration": round(info.duration, 3),
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
