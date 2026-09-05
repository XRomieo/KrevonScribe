"""The JS-facing bridge. Only the parts that need no window or Resolve."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool import api_bridge  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(api_bridge.config, "CONFIG_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(
        api_bridge.config, "LEGACY_CONFIG_PATH", tmp_path / "legacy" / "settings.json"
    )
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "kaggle"))
    return api_bridge.Api()


@pytest.fixture
def launches(monkeypatch):
    """Capture every way the bridge can hand something to the OS.

    Windows opens links with os.startfile and everything else shells out, so a
    test that watched only subprocess would pass on macOS while letting a real
    browser open on a Windows CI runner.
    """
    calls = []
    monkeypatch.setattr(api_bridge.subprocess, "run", lambda *a, **k: calls.append(a[0]))
    monkeypatch.setattr(api_bridge.os, "startfile", lambda p: calls.append([p]), raising=False)
    return calls


class TestOpenExternal:
    @pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
    def test_opens_an_https_link(self, api, monkeypatch, launches, platform):
        monkeypatch.setattr(api_bridge.sys, "platform", platform)
        assert api.open_external("https://www.kaggle.com/settings")["ok"]
        assert launches, "nothing was launched"
        assert any("https://www.kaggle.com/settings" in str(part)
                   for part in launches[0])

    @pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "http://example.com",
        "javascript:alert(1)",
        "/bin/sh",
        "",
    ])
    def test_refuses_anything_that_is_not_https(self, api, monkeypatch, launches,
                                                url, platform):
        monkeypatch.setattr(api_bridge.sys, "platform", platform)
        result = api.open_external(url)
        assert result["ok"] is False
        assert not launches, f"{url!r} reached the shell"


class TestReveal:
    def test_windows_gets_the_flag_and_path_as_one_argument(
        self, api, monkeypatch, launches, tmp_path,
    ):
        # explorer parses "/select,<path>" as a unit. Passed as two arguments it
        # selects nothing and opens Documents instead of the file.
        target = tmp_path / "EP04.srt"
        target.write_text("1\n")
        monkeypatch.setattr(api_bridge.sys, "platform", "win32")
        assert api.reveal(str(target))["ok"]
        assert launches == [["explorer", f"/select,{target}"]]

    def test_missing_paths_are_reported_rather_than_launched(self, api, launches, tmp_path):
        result = api.reveal(str(tmp_path / "nope.srt"))
        assert result["ok"] is False
        assert not launches


class TestSaveSettings:
    def test_unknown_keys_are_dropped_rather_than_raising(self, api):
        result = api.save_settings({"font_en": "Futura", "not_a_field": 1})
        assert result["ok"]
        assert result["settings"]["font_en"] == "Futura"
        assert "not_a_field" not in result["settings"]

    def test_a_threshold_arriving_as_a_string_is_still_a_number(self, api):
        result = api.save_settings({"arabic_threshold": "0.25"})
        assert result["settings"]["arabic_threshold"] == 0.25

    def test_settings_survive_a_reload(self, api):
        api.save_settings({"kaggle_username": "someone"})
        assert api_bridge.config.load().kaggle_username == "someone"


class TestPywebviewCanBuildItsBridge:
    """pywebview walks this object to build window.pywebview.api.

    Its walker recurses into any public attribute that is a non-callable
    object, and its cycle guard remembers id()s. A .NET property that returns a
    fresh object on every read therefore never repeats an id, and the walk runs
    until the stack is exhausted -- which is what froze the Windows build for
    twenty seconds on every page load.
    """

    @staticmethod
    def walk(obj, base="", seen=None, functions=None):
        """A faithful copy of pywebview.util's get_functions.

        No depth limit on purpose: pywebview has none either, and a cap here
        would hide exactly the runaway this test exists to catch.
        """
        import inspect

        seen = [] if seen is None else seen
        functions = {} if functions is None else functions
        if id(obj) in seen:
            return functions
        seen.append(id(obj))
        for name in dir(obj):
            if name.startswith("_"):
                continue
            full = f"{base}.{name}" if base else name
            attr = getattr(obj, name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                functions[full] = True
            elif inspect.isclass(attr) or (
                isinstance(attr, object) and not callable(attr)
                and hasattr(attr, "__module__")
            ):
                TestPywebviewCanBuildItsBridge.walk(attr, full, seen, functions)
        return functions

    def test_every_public_attribute_is_callable(self, api):
        offenders = [
            n for n in dir(api)
            if not n.startswith("_") and not callable(getattr(api, n))
        ]
        assert not offenders, (
            f"{offenders} are public non-callable attributes. pywebview will "
            "recurse into them when it builds the JS bridge; prefix with _."
        )

    def test_the_bridge_still_exposes_the_methods_the_frontend_calls(self, api):
        found = self.walk(api)
        for name in ("get_bootstrap", "start_run", "save_settings", "reveal"):
            assert name in found, f"{name} would not reach JavaScript"

    def test_a_window_that_recurses_forever_is_not_walked(self, api):
        class Endless:
            """Stands in for the WinForms graph: a new object on every read."""

            @property
            def empty(self):
                return Endless()

        api._window = Endless()
        found = self.walk(api)          # raises RecursionError if it descends
        assert "get_bootstrap" in found
        assert not [k for k in found if k.startswith("window")], found
