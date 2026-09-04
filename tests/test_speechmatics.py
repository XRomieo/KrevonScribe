"""Tests for parsing the Speechmatics json-v2 transcript into cues.

No network: these drive the parser with the response shape the batch API
documents (word and punctuation results, each alternative carrying a language).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool.speechmatics_runner import (  # noqa: E402
    SpeechmaticsError,
    _normalise_language,
    cues_from_transcript,
    transcribe,
)


def word(content, start, end, language="en", type_="word"):
    return {
        "type": type_,
        "start_time": start,
        "end_time": end,
        "alternatives": [{"content": content, "confidence": 0.9, "language": language}],
    }


def test_single_language_becomes_one_cue():
    t = {"results": [word("Hello", 0.0, 0.4), word("there", 0.4, 0.9)]}
    cues = cues_from_transcript(t)
    assert len(cues) == 1
    assert cues[0]["text"] == "Hello there"
    assert cues[0]["language"] == "en"


def test_language_change_starts_a_new_cue():
    """The whole point of Melia: the split is a lookup, not an inference."""
    t = {"results": [
        word("Hello", 0.0, 0.4, "en"),
        word("مرحبا", 0.5, 1.0, "ar"),
        word("again", 1.1, 1.6, "en"),
    ]}
    cues = cues_from_transcript(t)
    assert [c["language"] for c in cues] == ["en", "ar", "en"]
    assert [c["text"] for c in cues] == ["Hello", "مرحبا", "again"]


def test_cue_times_come_from_the_words():
    t = {"results": [word("Hello", 1.37, 1.9), word("there", 1.9, 2.62)]}
    cues = cues_from_transcript(t)
    assert cues[0]["start"] == 1.37
    assert cues[0]["end"] == 2.62


def test_punctuation_attaches_and_does_not_start_a_cue():
    t = {"results": [
        word("Hello", 0.0, 0.4),
        word(",", 0.4, 0.4, "en", "punctuation"),
        word("there", 0.5, 1.0),
    ]}
    cues = cues_from_transcript(t)
    assert len(cues) == 1
    assert cues[0]["text"] == "Hello, there"


def test_sentence_end_punctuation_closes_a_cue():
    t = {"results": [
        word("One", 0.0, 0.4),
        word(".", 0.4, 0.4, "en", "punctuation"),
        word("Two", 0.6, 1.0),
    ]}
    assert [c["text"] for c in cues_from_transcript(t)] == ["One.", "Two"]


def test_arabic_question_mark_closes_a_cue():
    t = {"results": [
        word("لماذا", 0.0, 0.6, "ar"),
        word("؟", 0.6, 0.6, "ar", "punctuation"),
        word("ما", 0.8, 1.2, "ar"),
    ]}
    assert len(cues_from_transcript(t)) == 2


def test_long_pause_splits_a_cue():
    t = {"results": [word("before", 0.0, 0.5), word("after", 5.0, 5.5)]}
    assert [c["text"] for c in cues_from_transcript(t)] == ["before", "after"]


def test_cue_respects_max_duration():
    results = [word(f"w{i}", i * 0.5, i * 0.5 + 0.5) for i in range(40)]
    cues = cues_from_transcript({"results": results}, max_duration=6.0)
    assert all(c["end"] - c["start"] <= 6.5 for c in cues)


def test_unreadably_short_cue_is_dropped():
    t = {"results": [word("hi", 1.0, 1.05)]}
    assert cues_from_transcript(t, min_duration=0.25) == []


def test_empty_transcript_yields_no_cues():
    assert cues_from_transcript({"results": []}) == []
    assert cues_from_transcript({}) == []


def test_results_without_alternatives_are_skipped():
    t = {"results": [{"type": "word", "start_time": 0.0, "end_time": 1.0},
                     word("kept", 1.0, 1.5)]}
    assert [c["text"] for c in cues_from_transcript(t)] == ["kept"]


def test_dialect_tags_map_onto_the_configured_bucket():
    assert _normalise_language("ar-EG", ("en", "ar")) == "ar"
    assert _normalise_language("en-US", ("en", "ar")) == "en"


def test_unexpected_language_falls_back_rather_than_dropping_the_cue():
    assert _normalise_language("fr", ("en", "ar")) == "en"
    t = {"results": [word("bonjour", 0.0, 0.8, "fr")]}
    assert len(cues_from_transcript(t)) == 1


def test_missing_api_key_is_reported_clearly(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    with pytest.raises(SpeechmaticsError, match="No Speechmatics API key"):
        transcribe(audio, "  ")


def test_missing_audio_is_reported_clearly(tmp_path):
    with pytest.raises(SpeechmaticsError, match="Audio file not found"):
        transcribe(tmp_path / "nope.wav", "key")
