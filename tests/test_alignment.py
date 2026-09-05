"""Tests for the kernel's forced-alignment helpers.

The alignment itself needs a GPU-sized model and real audio, so what is tested
here is everything around it: how cues are grouped into windows, and how mixed
Arabic/Latin text is reduced to the aligner's romanised alphabet.
"""

import importlib.util
from pathlib import Path

import pytest

KERNEL = (
    Path(__file__).resolve().parents[1]
    / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"
)


@pytest.fixture(scope="module")
def kernel():
    spec = importlib.util.spec_from_file_location("transcribe_kernel", KERNEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.log = lambda _msg: None
    return module


def cue(start, end, text="x"):
    return {"start": start, "end": end, "text": text, "language": "en"}


# --- _chunk_cues ----------------------------------------------------------

def test_short_timelines_are_one_chunk(kernel):
    cues = [cue(0, 2), cue(2, 4), cue(4, 6)]
    assert kernel._chunk_cues(cues, [0, 1, 2], 120.0) == [[0, 1, 2]]


def test_chunks_break_once_the_window_is_full(kernel):
    cues = [cue(0, 5), cue(5, 10), cue(10, 15), cue(15, 20)]
    chunks = kernel._chunk_cues(cues, [0, 1, 2, 3], 10.0)
    # The third cue would take the window past 10s, so it starts the next one.
    assert chunks == [[0, 1], [2, 3]]


def test_every_cue_lands_in_exactly_one_chunk(kernel):
    cues = [cue(i * 3, i * 3 + 2) for i in range(20)]
    chunks = kernel._chunk_cues(cues, list(range(20)), 7.0)
    assert sorted(i for chunk in chunks for i in chunk) == list(range(20))


def test_a_cue_longer_than_the_window_still_gets_its_own_chunk(kernel):
    cues = [cue(0, 1), cue(1, 90)]
    chunks = kernel._chunk_cues(cues, [0, 1], 10.0)
    assert [i for chunk in chunks for i in chunk] == [0, 1]


def test_no_cues_makes_no_chunks(kernel):
    assert kernel._chunk_cues([], [], 120.0) == []


# --- _romanised -----------------------------------------------------------

def test_latin_words_survive_lowercased(kernel):
    assert kernel._romanised("Chicken", lambda s: s) == "chicken"


def test_punctuation_is_stripped_but_apostrophes_are_kept(kernel):
    # The aligner's dictionary holds the apostrophe, so "it's" stays two tokens
    # of one word rather than becoming "it s".
    assert kernel._romanised("it's,", lambda s: s) == "it's"


def test_non_latin_output_is_reduced_to_the_aligner_alphabet(kernel):
    # Stand-in romaniser: what matters is that anything outside [a-z'] goes.
    assert kernel._romanised("الحمام", lambda s: "al-Hamām") == "alhamm"


def test_a_word_with_no_alignable_letters_becomes_empty(kernel):
    # The caller drops these rather than feeding the tokenizer an empty string.
    assert kernel._romanised("...", lambda s: s) == ""


def test_a_failing_romaniser_falls_back_to_the_raw_word(kernel):
    def boom(_s):
        raise RuntimeError("uroman exploded")

    assert kernel._romanised("Bath", boom) == "bath"
