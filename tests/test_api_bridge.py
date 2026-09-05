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


class TestOpenExternal:
    def test_opens_an_https_link(self, api, monkeypatch):
        calls = []
        monkeypatch.setattr(api_bridge.subprocess, "run", lambda *a, **k: calls.append(a))
        assert api.open_external("https://www.kaggle.com/settings")["ok"]
        assert calls, "nothing was launched"
        assert "https://www.kaggle.com/settings" in calls[0][0]

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "http://example.com",
        "javascript:alert(1)",
        "/bin/sh",
        "",
    ])
    def test_refuses_anything_that_is_not_https(self, api, monkeypatch, url):
        calls = []
        monkeypatch.setattr(api_bridge.subprocess, "run", lambda *a, **k: calls.append(a))
        result = api.open_external(url)
        assert result["ok"] is False
        assert not calls, f"{url!r} reached the shell"


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
