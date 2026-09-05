"""Transcribe via the Speechmatics batch API using the Melia 1 model.

Melia handles code-switching in a single pass and tags **every word** with the
language it was spoken in, which is the thing whisper cannot do: whisper commits
to one language for a whole file and translates the rest into it. That tag makes
the English/Arabic split a lookup rather than an inference, so none of the
span-detection machinery in the Kaggle kernel is needed here.

On the published Arabic-English code-switching benchmark Melia 1 scores a 15.1%
mixed error rate against 33.2% for the next best model tested.

Talks to the REST API directly rather than pulling in the vendor SDK: submit a
job, poll it, fetch the json-v2 transcript.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import requests

Progress = Callable[[str], None]

DEFAULT_ENDPOINT = "https://asr.api.speechmatics.com/v2"

# Sentence-final punctuation in both scripts; Arabic uses its own question mark
# and full stop, which the Latin set does not cover.
SENTENCE_END = (".", "!", "?", "؟", "۔", "…")


class SpeechmaticsError(RuntimeError):
    pass


@dataclass
class SpeechmaticsResult:
    segments: list[dict]
    job_id: str
    meta: dict = field(default_factory=dict)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key.strip()}"}


def submit(
    audio_path: Path,
    api_key: str,
    *,
    languages: Sequence[str] = ("en", "ar"),
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 120.0,
) -> str:
    """Upload the audio and return the job id."""
    config = {
        "type": "transcription",
        "transcription_config": {
            # Melia switches languages on its own; the codes are hints only, and
            # it rejects the "auto" option and the bilingual pack codes.
            "model": "melia",
            "language_hints": list(languages),
        },
    }
    with audio_path.open("rb") as handle:
        response = requests.post(
            f"{endpoint.rstrip('/')}/jobs/",
            headers=_headers(api_key),
            files={"data_file": (audio_path.name, handle, "application/octet-stream")},
            data={"config": json.dumps(config)},
            timeout=timeout,
        )
    if response.status_code == 401:
        raise SpeechmaticsError(
            "Speechmatics rejected the API key. Check it in Settings, or make a "
            "new one at https://portal.speechmatics.com/manage-access/"
        )
    if response.status_code == 403:
        raise SpeechmaticsError(
            "Speechmatics refused the job (403). Your starting credit may be "
            "spent; check the balance at https://portal.speechmatics.com/"
        )
    if not response.ok:
        raise SpeechmaticsError(
            f"Submitting the job failed ({response.status_code}): {response.text[:400]}"
        )
    job_id = (response.json() or {}).get("id")
    if not job_id:
        raise SpeechmaticsError(f"No job id in the response: {response.text[:400]}")
    return str(job_id)


def wait(
    job_id: str,
    api_key: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    poll_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
    progress: Progress | None = None,
) -> None:
    say = progress or (lambda _m: None)
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        response = requests.get(
            f"{endpoint.rstrip('/')}/jobs/{job_id}", headers=_headers(api_key), timeout=60
        )
        if not response.ok:
            raise SpeechmaticsError(
                f"Checking the job failed ({response.status_code}): {response.text[:300]}"
            )
        job = (response.json() or {}).get("job", {})
        status = str(job.get("status", "")).lower()
        if status != last:
            say(f"Speechmatics job {status}.")
            last = status
        if status == "done":
            return
        if status in {"rejected", "deleted", "expired"}:
            errors = job.get("errors") or job.get("error") or ""
            raise SpeechmaticsError(f"The job was {status}. {errors}")
        time.sleep(poll_seconds)
    raise SpeechmaticsError("Timed out waiting for Speechmatics to finish the job.")


def fetch_transcript(
    job_id: str, api_key: str, *, endpoint: str = DEFAULT_ENDPOINT
) -> dict:
    response = requests.get(
        f"{endpoint.rstrip('/')}/jobs/{job_id}/transcript",
        headers=_headers(api_key),
        params={"format": "json-v2"},
        timeout=120,
    )
    if not response.ok:
        raise SpeechmaticsError(
            f"Fetching the transcript failed ({response.status_code}): {response.text[:300]}"
        )
    return response.json()


def _normalise_language(raw: str, languages: Sequence[str]) -> str:
    """Map a returned tag onto one of our two buckets.

    Speechmatics may report a dialect ("ar-EG") or a language we did not ask
    for; anything unrecognised falls back to the first configured language so a
    cue is never silently lost.
    """
    tag = (raw or "").strip().lower().replace("_", "-")
    base = tag.split("-")[0]
    for lang in languages:
        if base == str(lang).lower():
            return str(lang)
    return str(languages[0]) if languages else base or "en"


def cues_from_transcript(
    transcript: dict,
    *,
    languages: Sequence[str] = ("en", "ar"),
    max_gap: float = 0.8,
    max_chars: int = 84,
    max_duration: float = 6.0,
    min_duration: float = 0.25,
) -> list[dict]:
    """Group the word-level results into cues, breaking when the language changes.

    Punctuation results carry no language of their own, so they attach to the
    cue in progress instead of starting a new one.
    """
    cues: list[dict] = []
    current: list[dict] = []
    current_lang: str | None = None

    def flush() -> None:
        nonlocal current, current_lang
        if not current:
            return
        text = "".join(w["text"] for w in current).strip()
        start, end = current[0]["start"], current[-1]["end"]
        if text and end - start >= min_duration:
            cues.append({"start": round(start, 3), "end": round(end, 3),
                         "text": text, "language": current_lang})
        current = []

    for item in transcript.get("results") or []:
        alternatives = item.get("alternatives") or []
        if not alternatives:
            continue
        content = alternatives[0].get("content", "")
        if not content:
            continue
        start = float(item.get("start_time", 0.0))
        end = float(item.get("end_time", start))
        is_punctuation = item.get("type") == "punctuation"

        if is_punctuation:
            if current:
                current[-1] = dict(current[-1], text=current[-1]["text"] + content,
                                   end=max(current[-1]["end"], end))
                if content in SENTENCE_END:
                    flush()
                    current_lang = None
            continue

        lang = _normalise_language(alternatives[0].get("language", ""), languages)
        if current_lang is None:
            current_lang = lang
        elif lang != current_lang:
            flush()
            current_lang = lang

        if current:
            text_so_far = "".join(w["text"] for w in current).strip()
            if (
                start - current[-1]["end"] > max_gap
                or len(text_so_far) >= max_chars
                or end - current[0]["start"] > max_duration
            ):
                flush()
        current.append({"start": start, "end": end, "text": " " + content})

    flush()
    cues.sort(key=lambda c: (c["start"], c["language"]))
    return cues


def transcribe(
    audio_path: str | Path,
    api_key: str,
    *,
    languages: Sequence[str] = ("en", "ar"),
    endpoint: str = DEFAULT_ENDPOINT,
    progress: Progress | None = None,
    poll_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
) -> SpeechmaticsResult:
    say = progress or (lambda _m: None)
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise SpeechmaticsError(f"Audio file not found: {audio_path}")
    if not (api_key or "").strip():
        raise SpeechmaticsError(
            "No Speechmatics API key. Add one in Settings — a new account gets "
            "$100 of credit, no card: https://portal.speechmatics.com/"
        )

    say(f"Uploading {audio_path.name} ({audio_path.stat().st_size / 1e6:.1f} MB) to Speechmatics…")
    job_id = submit(audio_path, api_key, languages=languages, endpoint=endpoint)
    say(f"Job {job_id} submitted.")
    wait(job_id, api_key, endpoint=endpoint, poll_seconds=poll_seconds,
         timeout_seconds=timeout_seconds, progress=say)
    transcript = fetch_transcript(job_id, api_key, endpoint=endpoint)
    cues = cues_from_transcript(transcript, languages=languages)
    say(f"Transcribed {len(cues)} cues.")

    metadata = transcript.get("metadata") or {}
    counts: dict[str, int] = {}
    for cue in cues:
        counts[cue["language"]] = counts.get(cue["language"], 0) + 1
    return SpeechmaticsResult(
        segments=cues,
        job_id=job_id,
        meta={
            "backend": "speechmatics",
            "model": "melia",
            "duration": metadata.get("duration"),
            "language_counts": counts,
            "segment_count": len(cues),
        },
    )
