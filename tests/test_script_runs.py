"""Tests for reading the spoken language off the script it was written in.

A code-switch checkpoint writes Arabic speech in Arabic script and English in
Latin, so language detection reduces to grouping words by script and cleaning up
the occasional mis-scripted word. These are the rules for that cleanup.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"
GROUND_TRUTH = ROOT / "tests" / "fixtures" / "codeswitch_ground_truth.json"


@pytest.fixture(scope="module")
def kernel():
    spec = importlib.util.spec_from_file_location("transcribe_kernel", KERNEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.log = lambda _msg: None
    return module


def words(spec, step=0.2):
    """Words tiling a timeline: ``spec`` is a list of (start, end, text)."""
    out = []
    for start, end, text in spec:
        t = start
        while t < end - 1e-9:
            out.append({"start": round(t, 3), "end": round(min(end, t + step), 3),
                        "word": text, "probability": 0.9})
            t += step
    return out


# --- word_language --------------------------------------------------------

def test_latin_words_are_english(kernel):
    assert kernel.word_language("chicken") == "en"


def test_arabic_words_are_arabic(kernel):
    assert kernel.word_language("الحمام") == "ar"


def test_punctuation_alone_has_no_language(kernel):
    # Returning None keeps "؟" from starting a run of its own.
    assert kernel.word_language(" ؟") is None
    assert kernel.word_language("...") is None


def test_digits_are_script_neutral(kernel):
    assert kernel.word_language("2024") is None
    assert kernel.word_language("١٩٩٠") is None


def test_a_mixed_token_goes_with_its_majority_script(kernel):
    assert kernel.word_language("الchicken") == "en"
    assert kernel.word_language("الحمامbath") == "ar"


def test_arabic_punctuation_attached_to_a_latin_word_stays_english(kernel):
    assert kernel.word_language("secret؟") == "en"


# --- script_runs ----------------------------------------------------------

def test_a_single_language_is_one_run(kernel):
    runs = kernel.script_runs(words([(0, 5, "hello")]), 1.5)
    assert [r[2] for r in runs] == ["en"]


def test_a_genuine_switch_becomes_two_runs(kernel):
    runs = kernel.script_runs(words([(0, 5, "hello"), (5, 10, "مرحبا")]), 1.5)
    assert [r[2] for r in runs] == ["en", "ar"]
    assert runs[0][1] == pytest.approx(5.0)


def test_one_mis_scripted_word_mid_sentence_is_absorbed(kernel):
    spec = [(0, 5, "hello"), (5, 5.2, "مرحبا"), (5.2, 10, "hello")]
    runs = kernel.script_runs(words(spec), 1.5)
    assert [r[2] for r in runs] == ["en"]


def test_a_short_switch_at_the_end_survives(kernel):
    # The clip really does end with 0.7s of Arabic; nothing follows it, so it is
    # not an interruption and must not be merged away.
    spec = [(0, 26.6, "hello"), (26.6, 27.3, "ولاشي")]
    runs = kernel.script_runs(words(spec), 1.5)
    assert [r[2] for r in runs] == ["en", "ar"]


def test_a_short_switch_at_the_start_survives(kernel):
    spec = [(0, 0.6, "مرحبا"), (0.6, 10, "hello")]
    runs = kernel.script_runs(words(spec), 1.5)
    assert [r[2] for r in runs] == ["ar", "en"]


def test_a_long_switch_between_two_stretches_is_kept(kernel):
    spec = [(0, 5, "hello"), (5, 9, "مرحبا"), (9, 14, "hello")]
    runs = kernel.script_runs(words(spec), 1.5)
    assert [r[2] for r in runs] == ["en", "ar", "en"]


def test_flanking_languages_must_match_for_a_merge(kernel):
    # A short run between two *different* languages is a real boundary, not a
    # flicker: absorbing it would have to invent which side it belongs to.
    spec = [(0, 5, "hello"), (5, 5.3, "مرحبا"), (5.3, 10, "hello"), (10, 15, "مرحبا")]
    runs = kernel.script_runs(words(spec), 1.5)
    assert [r[2] for r in runs] == ["en", "ar"]


def test_no_words_makes_no_runs(kernel):
    assert kernel.script_runs([], 1.5) == []


def test_runs_tile_the_timeline_without_gaps_or_overlap(kernel):
    spec = [(0, 3, "hello"), (3, 6, "مرحبا"), (6, 9, "hello")]
    runs = kernel.script_runs(words(spec), 1.5)
    for earlier, later in zip(runs, runs[1:]):
        assert earlier[1] == later[0]


# --- against the hand-marked spans ---------------------------------------

def test_scores_above_ninety_five_percent_on_the_marked_clip(kernel):
    """Regression guard on the real numbers, not a synthetic case.

    The word list is the code-switch model's actual output for the test clip;
    the spans are the ones the project owner marked by hand in Resolve.
    """
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "codeswitch_words.json").read_text(encoding="utf-8")
    )
    runs = kernel.script_runs(kernel.split_mixed_words(fixture["words"]), 1.5)

    spans = [(s["start"], s["end"], s["language"]) for s in truth["spans"]]
    total = spans[-1][1]
    step, correct, counted = 0.01, 0, 0
    t = step / 2
    while t < total:
        expected = next((l for a, b, l in spans if a <= t < b), None)
        if expected is not None:
            counted += 1
            got = next((l for a, b, l in runs if a <= t < b), None)
            if got == expected:
                correct += 1
        t += step
    accuracy = correct / counted
    assert accuracy > 0.95, f"language accuracy fell to {accuracy:.1%}"
    assert len(runs) == len(spans), f"found {len(runs)} runs, expected {len(spans)}"


# --- cue text tidying -----------------------------------------------------

def test_a_cue_does_not_open_with_the_previous_sentence_stop(kernel):
    # The break falls between "غير" and the "..", so the stop would otherwise
    # lead the next cue.
    cue = kernel._finish_cue(
        [{"start": 1.0, "end": 1.2, "word": ".."},
         {"start": 1.2, "end": 1.8, "word": "there's"}],
        "en",
    )
    assert cue["text"] == "there's"


def test_trailing_punctuation_is_left_alone(kernel):
    cue = kernel._finish_cue(
        [{"start": 0.0, "end": 0.5, "word": "Nothing."}], "en"
    )
    assert cue["text"] == "Nothing."


def test_arabic_question_marks_do_not_lead_a_cue(kernel):
    cue = kernel._finish_cue(
        [{"start": 0.0, "end": 0.2, "word": "؟"},
         {"start": 0.2, "end": 0.9, "word": "لماذا"}],
        "ar",
    )
    assert cue["text"] == "لماذا"


def test_words_are_separated_across_a_script_change(kernel):
    # Whisper gives Latin tokens a leading space and Arabic tokens none, so the
    # two fuse without help.
    cue = kernel._finish_cue(
        [{"start": 0.0, "end": 0.6, "word": " secret؟"},
         {"start": 0.6, "end": 1.2, "word": "هيكون"}],
        "en",
    )
    assert cue["text"] == "secret؟ هيكون"


def test_existing_spacing_is_not_doubled(kernel):
    cue = kernel._finish_cue(
        [{"start": 0.0, "end": 0.4, "word": "chicken"},
         {"start": 0.4, "end": 0.9, "word": " bath"}],
        "en",
    )
    assert cue["text"] == "chicken bath"


# --- split_mixed_words ----------------------------------------------------

def test_a_token_holding_both_scripts_is_split(kernel):
    # The real case: the model emitted " secret؟هيكون" as one word.
    out = kernel.split_mixed_words(
        [{"start": 13.76, "end": 14.96, "word": " secret؟هيكون", "probability": 0.8}]
    )
    assert [w["word"] for w in out] == [" secret؟", "هيكون"]
    assert out[0]["start"] == pytest.approx(13.76)
    assert out[1]["end"] == pytest.approx(14.96)
    assert out[0]["end"] == out[1]["start"]


def test_a_single_script_token_is_untouched(kernel):
    word = {"start": 0.0, "end": 0.5, "word": " chicken", "probability": 0.9}
    assert kernel.split_mixed_words([word]) == [word]


def test_an_arabic_only_token_is_untouched(kernel):
    word = {"start": 0.0, "end": 0.5, "word": "الحمام", "probability": 0.9}
    assert kernel.split_mixed_words([word]) == [word]


def test_the_split_keeps_every_character(kernel):
    out = kernel.split_mixed_words(
        [{"start": 0.0, "end": 1.0, "word": "abcمرحباdef", "probability": 0.9}]
    )
    assert "".join(w["word"] for w in out) == "abcمرحباdef"


def test_split_pieces_get_their_own_language(kernel):
    out = kernel.split_mixed_words(
        [{"start": 0.0, "end": 1.0, "word": " secret؟هيكون", "probability": 0.8}]
    )
    assert [kernel.word_language(w["word"]) for w in out] == ["en", "ar"]


def test_punctuation_only_tokens_survive_unsplit(kernel):
    word = {"start": 0.0, "end": 0.2, "word": " ...", "probability": 0.5}
    assert kernel.split_mixed_words([word]) == [word]
