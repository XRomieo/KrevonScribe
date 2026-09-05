"""Tests for the build self-test's argument parsing.

The self-test itself needs a built frontend and the runtime dependencies, so it
runs in CI rather than here; what is unit-testable is how it reads its flags,
which is what CI depends on to get a report out of a windowed Windows build.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool.main import _flag_value  # noqa: E402


@pytest.fixture
def argv(monkeypatch):
    def set_argv(*args):
        monkeypatch.setattr(sys, "argv", ["app.py", *args])
    return set_argv


def test_separate_value_is_read(argv):
    argv("--selftest", "--selftest-out", "report.txt")
    assert _flag_value("--selftest-out") == "report.txt"


def test_equals_form_is_read(argv):
    argv("--selftest-out=report.txt")
    assert _flag_value("--selftest-out") == "report.txt"


def test_a_missing_flag_is_none(argv):
    argv("--selftest")
    assert _flag_value("--selftest-out") is None


def test_a_flag_with_no_value_is_none(argv):
    # Trailing flag with nothing after it must not raise.
    argv("--selftest", "--selftest-out")
    assert _flag_value("--selftest-out") is None


def test_a_windows_path_with_spaces_survives(argv):
    argv("--selftest-out", r"C:\Users\a b\report.txt")
    assert _flag_value("--selftest-out") == r"C:\Users\a b\report.txt"


def test_an_unrelated_flag_is_not_matched(argv):
    argv("--selftest-outdir", "x")
    assert _flag_value("--selftest-out") is None
