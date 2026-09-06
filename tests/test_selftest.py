"""Tests for the build self-test's argument parsing.

The self-test itself needs a built frontend and the runtime dependencies, so it
runs in CI rather than here; what is unit-testable is how it reads its flags,
which is what CI depends on to get a report out of a windowed Windows build.
"""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool import main  # noqa: E402
from resolve_subtitle_tool.main import _flag_value, _print_safely  # noqa: E402


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


class TestPrintingTheReport:
    """The report has to survive a console that cannot encode it.

    A Windows console is usually cp1252, not UTF-8, and any line of the report
    can carry a non-ASCII path: the frontend location is printed, and a user
    profile name is enough to put a non-Latin character in it. print() raising
    UnicodeEncodeError there would throw away the whole diagnosis.
    """

    @staticmethod
    def cp1252_console():
        return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")

    def test_ascii_is_printed_unchanged(self):
        stream = self.cp1252_console()
        _print_safely("13/13 checks passed", stream)
        stream.flush()
        assert stream.buffer.getvalue().decode("cp1252") == "13/13 checks passed\n"

    def test_an_unencodable_path_does_not_lose_the_report(self):
        stream = self.cp1252_console()
        path = r"C:\Users\أحمد\index.html"
        report = f"FAIL  frontend: {path}\n\n0/1 checks passed"
        _print_safely(report, stream)
        stream.flush()
        written = stream.buffer.getvalue().decode("cp1252")
        assert "0/1 checks passed" in written
        assert "FAIL  frontend" in written

    def test_a_stream_with_no_encoding_attribute_is_tolerated(self):
        # StringIO has no .encoding; the helper must not trip over that.
        stream = io.StringIO()
        _print_safely("frontend: " + r"C:\Users\أحمد\index.html", stream)
        assert "أحمد" in stream.getvalue()


class TestFindingTheFrontend:
    """Which build of the UI a run actually loads.

    scripts/build.py stages a copy of the frontend inside the package for
    PyInstaller to pick up. That copy is only as new as the last release build,
    so a run from source has to look at frontend/dist first -- otherwise
    `bun run build` appears to do nothing at all.
    """

    @staticmethod
    def _tree(tmp_path):
        package = tmp_path / "resolve_subtitle_tool"
        staged = package / "frontend_dist"
        live = tmp_path / "frontend" / "dist"
        for d in (staged, live):
            d.mkdir(parents=True)
        (staged / "index.html").write_text("staged", encoding="utf-8")
        (live / "index.html").write_text("live", encoding="utf-8")
        return package, staged, live

    def _index(self, monkeypatch, package):
        monkeypatch.setattr(main, "__file__", str(package / "main.py"))
        return main.frontend_index()

    def test_a_source_run_prefers_the_live_build(self, tmp_path, monkeypatch):
        package, _, live = self._tree(tmp_path)
        assert self._index(monkeypatch, package) == live / "index.html"

    def test_the_staged_copy_is_still_a_fallback(self, tmp_path, monkeypatch):
        package, staged, live = self._tree(tmp_path)
        (live / "index.html").unlink()
        assert self._index(monkeypatch, package) == staged / "index.html"

    def test_a_frozen_run_uses_what_was_bundled(self, tmp_path, monkeypatch):
        package, _, _ = self._tree(tmp_path)
        bundle = tmp_path / "meipass" / "frontend_dist"
        bundle.mkdir(parents=True)
        (bundle / "index.html").write_text("bundled", encoding="utf-8")
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
        assert self._index(monkeypatch, package) == bundle / "index.html"

    def test_no_frontend_at_all_says_how_to_build_it(self, tmp_path, monkeypatch):
        package = tmp_path / "resolve_subtitle_tool"
        package.mkdir(parents=True)
        with pytest.raises(SystemExit, match="bun run build"):
            self._index(monkeypatch, package)
