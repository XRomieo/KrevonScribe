"""Tests for the kernel's code-switch language segmentation.

The kernel runs on Kaggle, but the decision logic is pure arithmetic over word
confidences and segment times, so it is exercised here without a GPU.
"""

import importlib.util
from pathlib import Path

import pytest

KERNEL = (
    Path(__file__).resolve().parents[1]
    / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"
)
SETTINGS = {"languages": ["en", "ar"], "conf_slot": 0.25, "conf_smooth": 3.0, "min_span": 1.5}


@pytest.fixture(scope="module")
def kernel():
    spec = importlib.util.spec_from_file_location("transcribe_kernel", KERNEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.log = lambda _msg: None
    return module


def words(intervals, probability=0.9, step=0.4):
    """Confident words tiling each interval."""
    out = []
    for a, b in intervals:
        t = a
        while t < b - 1e-9:
            out.append({"start": t, "end": min(b, t + step), "probability": probability})
            t += step
    return out


# --- language_spans_from_words -------------------------------------------

def test_one_language_throughout(kernel):
    wb = {"en": words([(0, 20)]), "ar": []}
    assert kernel.language_spans_from_words(wb, 20.0, SETTINGS) == [(0.0, 20.0, "en")]


def test_silence_from_one_decoder_hands_the_region_over(kernel):
    """Where a decoder emits no words it is saying 'not my language'."""
    wb = {"en": words([(0, 8), (14, 20)]), "ar": words([(8, 14)])}
    spans = kernel.language_spans_from_words(wb, 20.0, SETTINGS)
    langs = [l for _, _, l in spans]
    assert langs == ["en", "ar", "en"]
    mid = [(a + b) / 2 for a, b, _ in spans]
    assert mid[1] == pytest.approx(11.0, abs=1.5)


def test_higher_confidence_wins_where_both_produced_words(kernel):
    wb = {"en": words([(0, 20)], probability=0.95),
          "ar": words([(0, 20)], probability=0.30)}
    assert [l for _, _, l in kernel.language_spans_from_words(wb, 20.0, SETTINGS)] == ["en"]


def test_two_switches_are_both_recovered(kernel):
    wb = {"en": words([(0, 4), (10, 13)], probability=0.95),
          "ar": words([(4, 10), (13, 20)], probability=0.95)}
    langs = [l for _, _, l in kernel.language_spans_from_words(wb, 20.0, SETTINGS)]
    assert langs == ["en", "ar", "en", "ar"]


def test_brief_flicker_is_absorbed(kernel):
    wb = {"en": words([(0, 20)], probability=0.9),
          "ar": words([(9.6, 10.0)], probability=0.99)}
    assert kernel.language_spans_from_words(wb, 20.0, SETTINGS) == [(0.0, 20.0, "en")]


def test_spans_tile_without_gaps_or_overlaps(kernel):
    wb = {"en": words([(0, 8), (14, 20)]), "ar": words([(8, 14)])}
    spans = kernel.language_spans_from_words(wb, 20.0, SETTINGS)
    assert spans[0][0] == 0.0
    assert spans[-1][1] == pytest.approx(20.0)
    for earlier, later in zip(spans, spans[1:]):
        assert earlier[1] == later[0]


def test_adjacent_spans_never_share_a_language(kernel):
    wb = {"en": words([(0, 8), (14, 20)]), "ar": words([(8, 14)])}
    langs = [l for _, _, l in kernel.language_spans_from_words(wb, 20.0, SETTINGS)]
    assert all(a != b for a, b in zip(langs, langs[1:]))


def test_no_words_at_all_still_returns_a_span(kernel):
    spans = kernel.language_spans_from_words({"en": [], "ar": []}, 12.0, SETTINGS)
    assert spans == [(0.0, 12.0, "en")]


def test_zero_length_audio_does_not_crash(kernel):
    assert kernel.language_spans_from_words({"en": [], "ar": []}, 0.0, SETTINGS) == [
        (0.0, 0.0, "en")
    ]


# --- cues_from_words ------------------------------------------------------

CUE_SETTINGS = dict(SETTINGS, max_gap=0.8, max_chars=84, max_duration=6.0,
                    min_cue_duration=0.25)


def spoken(texts, start=0.0, step=0.4, probability=0.9):
    """Words laid end to end from ``start``."""
    out, t = [], start
    for text in texts:
        out.append({"start": t, "end": t + step, "probability": probability,
                    "word": " " + text})
        t += step
    return out


def test_cue_times_come_from_words_not_span_bounds(kernel):
    """The regression that snapped every cue to the grid and lost sync."""
    spans = [(0.0, 5.0, "en")]
    wb = {"en": spoken(["hello", "there"], start=1.37), "ar": []}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert cues[0]["start"] == 1.37
    assert cues[0]["end"] == pytest.approx(2.17)


def test_words_outside_the_span_are_excluded(kernel):
    # words at 0.0-0.4, 0.4-0.8, 0.8-1.2, 1.2-1.6, 1.6-2.0; the span ends at 1.0
    spans = [(0.0, 1.0, "en"), (1.0, 6.0, "ar")]
    wb = {"en": spoken(["one", "two", "three", "four", "five"]), "ar": []}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert " ".join(c["text"] for c in cues) == "one two"
    assert cues[-1]["end"] <= 1.0


def test_a_sentence_straddling_a_switch_is_split_not_dropped(kernel):
    """Whisper segments ignore language switches; word-level cutting keeps both."""
    spans = [(0.0, 2.0, "en"), (2.0, 4.0, "ar"), (4.0, 6.0, "en")]
    wb = {
        "en": spoken(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]),
        "ar": [],
    }
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert len(cues) == 2
    assert cues[0]["text"] == "a b c d e"
    assert cues[1]["text"].startswith("k") or cues[1]["start"] >= 4.0


def test_cue_breaks_on_a_long_pause(kernel):
    spans = [(0.0, 20.0, "en")]
    words = spoken(["before"], start=0.0) + spoken(["after"], start=5.0)
    cues = kernel.cues_from_words({"en": words}, spans, CUE_SETTINGS)
    assert [c["text"] for c in cues] == ["before", "after"]


def test_cue_breaks_at_sentence_end(kernel):
    spans = [(0.0, 20.0, "en")]
    wb = {"en": spoken(["Hello.", "Next", "one"])}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert [c["text"] for c in cues] == ["Hello.", "Next one"]


def test_arabic_question_mark_ends_a_cue(kernel):
    spans = [(0.0, 20.0, "ar")]
    wb = {"ar": spoken(["\u0644\u0645\u0627\u0630\u0627\u061f", "\u0645\u0627", "\u0647\u064a"])}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert len(cues) == 2


def test_cue_breaks_before_exceeding_max_duration(kernel):
    spans = [(0.0, 40.0, "en")]
    wb = {"en": spoken(["w"] * 40, step=0.5)}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert cues
    assert all(c["end"] - c["start"] <= CUE_SETTINGS["max_duration"] + 0.5 for c in cues)


def test_cue_breaks_before_exceeding_max_chars(kernel):
    spans = [(0.0, 60.0, "en")]
    wb = {"en": spoken(["abcdefgh"] * 30, step=0.1)}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert all(len(c["text"]) <= CUE_SETTINGS["max_chars"] + 10 for c in cues)


def test_each_language_only_contributes_its_own_spans(kernel):
    spans = [(0.0, 2.0, "en"), (2.0, 4.0, "ar")]
    wb = {"en": spoken(["eng"] * 10), "ar": spoken(["\u0639\u0631\u0628"] * 10)}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    for cue in cues:
        for a, b, lang in spans:
            if a <= (cue["start"] + cue["end"]) / 2 < b:
                assert cue["language"] == lang


def test_degenerate_words_are_ignored(kernel):
    spans = [(0.0, 10.0, "en")]
    wb = {"en": [
        {"start": 1.0, "end": 1.0, "probability": 0.9, "word": " zero"},
        {"start": 3.0, "end": 2.0, "probability": 0.9, "word": " reversed"},
        {"start": 4.0, "end": 4.4, "probability": 0.9, "word": " keep"},
    ]}
    assert [c["text"] for c in kernel.cues_from_words(wb, spans, CUE_SETTINGS)] == ["keep"]


def test_no_words_yields_no_cues(kernel):
    assert kernel.cues_from_words({"en": [], "ar": []}, [(0.0, 5.0, "en")], CUE_SETTINGS) == []


def test_cues_are_sorted_by_start(kernel):
    spans = [(0.0, 3.0, "en"), (3.0, 6.0, "ar"), (6.0, 9.0, "en")]
    wb = {"en": spoken(["a"] * 6, start=0.0) + spoken(["c"] * 6, start=6.0),
          "ar": spoken(["b"] * 6, start=3.0)}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert [c["start"] for c in cues] == sorted(c["start"] for c in cues)


def test_unreadably_short_cue_is_dropped(kernel):
    """Whisper's end-of-audio artefact ("You", "Thank you") arrives like this."""
    spans = [(0.0, 30.0, "en")]
    wb = {"en": [
        {"start": 1.0, "end": 2.0, "probability": 0.9, "word": " real speech."},
        {"start": 27.16, "end": 27.26, "probability": 0.2, "word": " You"},
    ]}
    cues = kernel.cues_from_words(wb, spans, CUE_SETTINGS)
    assert [c["text"] for c in cues] == ["real speech."]


def test_cue_exactly_at_the_duration_floor_is_kept(kernel):
    spans = [(0.0, 30.0, "en")]
    wb = {"en": [{"start": 1.0, "end": 1.25, "probability": 0.9, "word": " ok"}]}
    assert len(kernel.cues_from_words(wb, spans, CUE_SETTINGS)) == 1
