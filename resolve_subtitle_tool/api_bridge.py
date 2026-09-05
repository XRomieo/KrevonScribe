"""The ``js_api`` object pywebview exposes to the React frontend.

Every method returns a JSON-serialisable dict shaped as either
``{"ok": True, ...}`` or ``{"ok": False, "error": "..."}`` so the UI never has
to interpret a Python traceback. Long work runs on a worker thread and streams
log lines back into the page.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import traceback
from dataclasses import fields
from pathlib import Path
from typing import Any

from . import config, pipeline, resolve_bridge


def _ok(**payload: Any) -> dict:
    return {"ok": True, **payload}


def _err(exc: BaseException | str) -> dict:
    if isinstance(exc, str):
        return {"ok": False, "error": exc}
    return {"ok": False, "error": str(exc) or exc.__class__.__name__,
            "kind": exc.__class__.__name__}


# Keeps a console window from flashing up when this windowed build shells out.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Api:
    """Backend surface callable from JavaScript as ``window.pywebview.api.*``."""

    def __init__(self) -> None:
        # Both of these must stay underscored. pywebview builds its JS bridge by
        # walking every public attribute of this object and recursing into any
        # that is a non-callable object. A public `window` sent it into the
        # native window's .NET graph, where Rectangle.Empty returns a new object
        # each time, so its id()-based cycle guard never fired -- it recursed
        # until the stack blew, on the UI thread, on every page load. That is a
        # twenty-second freeze on Windows. macOS never hit it: the Cocoa window
        # does not expose an equivalent graph.
        self._window = None
        self._settings = config.load()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # -- plumbing --------------------------------------------------------
    def _emit(self, event: str, payload: Any) -> None:
        """Push an event into the page. Safe to call from a worker thread."""
        if self._window is None:
            return
        try:
            message = json.dumps({"event": event, "payload": payload})
            self._window.evaluate_js(f"window.__appEvent && window.__appEvent({message})")
        except Exception:
            pass  # the UI going away must never kill a running job

    def _log(self, message: str) -> None:
        self._emit("log", {"message": str(message)})

    # -- state -----------------------------------------------------------
    def get_bootstrap(self) -> dict:
        return _ok(
            settings=self._settings.to_dict(),
            kaggle=config.kaggle_status(),
            resolve=self.get_resolve_state(),
            platform=sys.platform,
            config_path=str(config.CONFIG_PATH),
        )

    def get_resolve_state(self) -> dict:
        try:
            return _ok(info=resolve_bridge.get_info().to_dict())
        except resolve_bridge.ResolveError as exc:
            return _err(exc)
        except Exception as exc:  # noqa: BLE001 - surface anything to the UI
            return _err(exc)

    # -- settings --------------------------------------------------------
    def save_settings(self, values: dict) -> dict:
        try:
            known = {f.name for f in fields(config.Settings)}
            current = self._settings.to_dict()
            current.update({k: v for k, v in (values or {}).items() if k in known})
            # Keep numeric fields numeric even if the input arrives as a string.
            current["arabic_threshold"] = float(current["arabic_threshold"])
            self._settings = config.Settings(**current)
            config.save(self._settings)
            return _ok(settings=self._settings.to_dict())
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    def save_kaggle_credentials(self, values: dict) -> dict:
        try:
            values = values or {}
            token = (values.get("token") or "").strip()
            username = (values.get("username") or "").strip()
            key = (values.get("key") or "").strip()
            if token:
                config.write_access_token(token)
            elif username and key:
                config.write_kaggle_json(username, key)
            else:
                return _err("Provide either an API token, or a username and key.")
            if not username:
                # A token carries the account identity; ask Kaggle rather than
                # making the user retype a name it already knows.
                from . import kaggle_runner
                username = kaggle_runner.detect_username()
            if username:
                self._settings.kaggle_username = username
                config.save(self._settings)
            return _ok(kaggle=config.kaggle_status(), settings=self._settings.to_dict())
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    # -- dialogs ---------------------------------------------------------
    def choose_folder(self, current: str = "") -> dict:
        import webview
        if self._window is None:
            return _err("Window is not ready yet.")
        try:
            picked = self._window.create_file_dialog(
                webview.FOLDER_DIALOG, directory=current or str(Path.home())
            )
            return _ok(path=picked[0] if picked else None)
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    def choose_audio_file(self, current: str = "") -> dict:
        import webview
        if self._window is None:
            return _err("Window is not ready yet.")
        try:
            picked = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=current or str(Path.home()),
                allow_multiple=False,
                file_types=("Audio (*.wav;*.flac;*.mp3;*.m4a;*.aac;*.ogg;*.opus)",
                            "All files (*.*)"),
            )
            return _ok(path=picked[0] if picked else None)
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    def open_external(self, url: str) -> dict:
        """Open an https link in the user's real browser.

        Getting a Kaggle token means visiting a page, and a webview window with
        no address bar is a bad place to do that. Only https is honoured, so a
        stray call cannot be turned into a local command.
        """
        try:
            if not str(url).startswith("https://"):
                return _err("Only https links can be opened.")
            if sys.platform == "darwin":
                subprocess.run(["open", url], check=False)
            elif sys.platform == "win32":
                # Not `cmd /c start`: this build has no console, so cmd flashes
                # one up, and start treats & in a URL as a command separator.
                os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606
            else:
                subprocess.run(["xdg-open", url], check=False)
            return _ok()
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    def reveal(self, path: str) -> dict:
        """Show a file or folder in Finder / Explorer."""
        try:
            p = Path(path)
            if not p.exists():
                return _err(f"Not found: {path}")
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", str(p)], check=False)
            elif sys.platform == "win32":
                # The flag and the path are one argument. Split in two, Explorer
                # sees an empty selection and opens Documents instead.
                subprocess.run(["explorer", f"/select,{p}"], check=False,
                               creationflags=_NO_WINDOW)
            else:
                subprocess.run(["xdg-open", str(p.parent)], check=False)
            return _ok()
        except Exception as exc:  # noqa: BLE001
            return _err(exc)

    # -- the run ---------------------------------------------------------
    def is_running(self) -> dict:
        return _ok(running=bool(self._thread and self._thread.is_alive()))

    def start_run(self, options: dict) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return _err("A run is already in progress.")
            options = options or {}
            self._thread = threading.Thread(
                target=self._run, args=(options,), daemon=True, name="transcribe-run"
            )
            self._thread.start()
        return _ok(started=True)

    def _run(self, options: dict) -> None:
        self._emit("run_started", {})
        try:
            outcome = pipeline.run(
                self._settings,
                audio_source=options.get("audio_source", "timeline"),
                track_indices=[int(i) for i in options.get("track_indices", [])],
                audio_file=options.get("audio_file"),
                import_to_resolve=bool(options.get("import_to_resolve", True)),
                progress=self._log,
            )
            self._emit("run_finished", outcome.to_dict())
        except Exception as exc:  # noqa: BLE001
            self._log(f"Failed: {exc}")
            self._emit("run_failed", {
                "error": str(exc) or exc.__class__.__name__,
                "kind": exc.__class__.__name__,
                "traceback": traceback.format_exc(),
            })
