"""Tests for the kernel's code-switch language segmentation.

The kernel normally runs on Kaggle, but the span logic is pure arithmetic over
detection probabilities, so it can be driven here with a stub model. The stub
reports the *fraction* of each window that is Arabic, which is how real
detection behaves on a window straddling a switch.
"""

import importlib.util
from pathlib import Path

import pytest

KERNEL = Path(__file__).resolve().parents[1] / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"
SR = 16000
SETTINGS = {"languages": ["en", "ar"], "detect_window": 4.0, "detect_hop": 1.0, "min_span": 1.5}


@pytest.fixture(scope="module")
def kernel():
    spec = importlib.util.spec_from_file_location("transcribe_kernel", KERNEL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.log = lambda _msg: None
    return module


class StubModel:
    def __init__(self, arabic_intervals, total, settings):
        self.truth = arabic_intervals
        self.total = total
        self.settings = settings
        self.t = 0.0

    def detect_language(self, audio=None):
        w0 = self.t
        w1 = min(self.total, self.t + self.settings["detect_window"])
        self.t += self.settings["detect_hop"]
        overlap = sum(max(0.0, min(w1, b) - max(w0, a)) for a, b in self.truth)
        frac = overlap / max(w1 - w0, 1e-6)
        return ("ar" if frac > 0.5 else "en", 0.9, {"ar": frac, "en": 1.0 - frac})


def spans_for(kernel, arabic_intervals, total=27.4, settings=None):
    settings = settings or SETTINGS
    pcm = [0.0] * int(total * SR)
    model = StubModel(arabic_intervals, total, settings)
    return kernel.detect_language_spans(model, pcm, SR, settings)


def test_monolingual_english_is_one_span(kernel):
    assert spans_for(kernel, []) == [(0.0, 27.4, "en")]


def test_monolingual_arabic_is_one_span(kernel):
    assert spans_for(kernel, [(0, 30)]) == [(0.0, 27.4, "ar")]


def test_single_switch_boundaries_are_exact(kernel):
    assert spans_for(kernel, [(4, 8)]) == [
        (0.0, 4.0, "en"),
        (4.0, 8.0, "ar"),
        (8.0, 27.4, "en"),
    ]


def test_two_switches_both_survive(kernel):
    """A median filter over labels would erase the second, one-slot-wide switch."""
    assert spans_for(kernel, [(4, 8), (14, 18)]) == [
        (0.0, 4.0, "en"),
        (4.0, 8.0, "ar"),
        (8.0, 14.0, "en"),
        (14.0, 18.0, "ar"),
        (18.0, 27.4, "en"),
    ]


def test_subsecond_blip_is_absorbed(kernel):
    assert spans_for(kernel, [(10, 10.5)]) == [(0.0, 27.4, "en")]


def test_spans_tile_the_audio_without_gaps(kernel):
    spans = spans_for(kernel, [(4, 8), (14, 18)])
    assert spans[0][0] == 0.0
    assert spans[-1][1] == pytest.approx(27.4)
    for earlier, later in zip(spans, spans[1:]):
        assert earlier[1] == later[0]


def test_adjacent_spans_never_share_a_language(kernel):
    for truth in ([], [(4, 8)], [(4, 8), (14, 18)], [(10, 10.5)], [(0, 30)]):
        spans = spans_for(kernel, truth)
        langs = [lang for _, _, lang in spans]
        assert all(a != b for a, b in zip(langs, langs[1:])), truth


def test_short_audio_returns_a_single_span(kernel):
    spans = spans_for(kernel, [], total=0.8)
    assert len(spans) == 1
    assert spans[0][2] == "en"


def test_empty_audio_does_not_crash(kernel):
    assert spans_for(kernel, [], total=0.0) == [(0.0, 0.0, "en")]
