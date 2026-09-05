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
