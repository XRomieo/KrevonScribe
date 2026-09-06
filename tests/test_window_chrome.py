"""The title bar the app draws for itself on Windows.

The Win32 calls need a real window, so they are not what is tested here. What
is: that the frontend is told which title bar to draw, that every button
reaches the right call, and that a command arriving before the window exists is
answered rather than raising -- the page can render its bar before pywebview
has finished opening.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolve_subtitle_tool import api_bridge, window_chrome  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(api_bridge.config, "CONFIG_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(
        api_bridge.config, "LEGACY_CONFIG_PATH", tmp_path / "legacy" / "settings.json"
    )
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path / "kaggle"))
    return api_bridge.Api()


class FakeChrome:
    """Records what the bridge asked the window to do."""

    def __init__(self, maximized=False):
        self.calls = []
        self.maximized = maximized

    def minimize(self):
        self.calls.append("minimize")

    def toggle_maximize(self):
        self.calls.append("toggle_maximize")
        self.maximized = not self.maximized

    def close(self):
        self.calls.append("close")

    def drag(self):
        self.calls.append("drag")

    def is_maximized(self):
        return self.maximized


class TestWhichTitleBar:
    def test_windows_draws_its_own(self):
        expected = "custom" if sys.platform == "win32" else "native"
        assert window_chrome.KIND == expected

    def test_the_bootstrap_says_which(self, api):
        assert api.get_bootstrap()["chrome"] == window_chrome.KIND


class TestWindowCommands:
    @pytest.mark.parametrize("action", ["minimize", "toggle_maximize", "close", "drag"])
    def test_each_button_reaches_the_window(self, api, action):
        api._chrome = FakeChrome()
        assert api.window_command(action)["ok"]
        assert api._chrome.calls == [action]

    def test_state_asks_without_touching_the_window(self, api):
        api._chrome = FakeChrome(maximized=True)
        result = api.window_command("state")
        assert result == {"ok": True, "maximized": True}
        assert api._chrome.calls == []

    def test_the_answer_carries_the_new_state(self, api):
        api._chrome = FakeChrome(maximized=False)
        assert api.window_command("toggle_maximize")["maximized"] is True
        assert api.window_command("toggle_maximize")["maximized"] is False

    def test_an_unknown_action_is_refused(self, api):
        api._chrome = FakeChrome()
        result = api.window_command("resize_to_the_moon")
        assert result["ok"] is False
        assert api._chrome.calls == []

    def test_a_command_before_the_window_exists_is_not_an_exception(self, api):
        assert api._chrome is None
        result = api.window_command("minimize")
        assert result["ok"] is False
        assert "not ready" in result["error"]

    def test_a_failing_window_is_reported_not_raised(self, api):
        class Broken(FakeChrome):
            def minimize(self):
                raise OSError("the window went away")

        api._chrome = Broken()
        result = api.window_command("minimize")
        assert result["ok"] is False
        assert "went away" in result["error"]


class FakeWindow:
    """pywebview's Window, as far as this module uses it."""

    def __init__(self):
        self.calls = []

    def minimize(self):
        self.calls.append("minimize")

    def maximize(self):
        self.calls.append("maximize")

    def restore(self):
        self.calls.append("restore")

    def destroy(self):
        self.calls.append("destroy")


class TestTheWindowItself:
    """The state changes go through pywebview, which marshals them.

    The window belongs to the UI thread and these calls arrive on a worker
    thread. Reaching for ShowWindow instead changed the window behind WinForms'
    back, and the page came back from the taskbar blank.
    """

    def test_the_buttons_go_through_pywebview(self):
        window = FakeWindow()
        chrome = window_chrome.WindowChrome(window)
        chrome.minimize()
        chrome.close()
        assert window.calls == ["minimize", "destroy"]

    def test_maximize_toggles_on_what_the_os_reports(self, monkeypatch):
        window = FakeWindow()
        chrome = window_chrome.WindowChrome(window)
        monkeypatch.setattr(type(chrome), "is_maximized", lambda self: False)
        chrome.toggle_maximize()
        monkeypatch.setattr(type(chrome), "is_maximized", lambda self: True)
        chrome.toggle_maximize()
        assert window.calls == ["maximize", "restore"]

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows has the real API")
    def test_nothing_reaches_win32_off_windows(self):
        chrome = window_chrome.WindowChrome(FakeWindow())
        chrome.attach()
        chrome.drag()
        assert chrome.is_maximized() is False
