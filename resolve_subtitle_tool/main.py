"""Entry point: opens the pywebview window around the built React frontend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# webview is imported inside main(), not here: it pulls in a GUI toolkit, and
# this module must stay importable without one so --selftest and the test suite
# can reach it on a machine that has neither.

WINDOW_TITLE = "Krevon Scribe"


def frontend_index() -> Path:
    """Locate the built frontend, whether running from source or from a bundle."""
    candidates = []
    bundle = getattr(sys, "_MEIPASS", None)          # PyInstaller onefile/onedir
    if bundle:
        candidates.append(Path(bundle) / "frontend_dist" / "index.html")
    here = Path(__file__).resolve().parent
    candidates.append(here / "frontend_dist" / "index.html")
    candidates.append(here.parent / "frontend" / "dist" / "index.html")
    for c in candidates:
        if c.is_file():
            return c
    raise SystemExit(
        "The frontend has not been built. Run:  cd frontend && bun install && bun run build\n"
        "Looked in:\n  " + "\n  ".join(str(c) for c in candidates)
    )


def _flag_value(flag: str) -> str | None:
    """Read ``--flag value`` or ``--flag=value`` from argv."""
    for i, arg in enumerate(sys.argv):
        if arg == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def _gui_backend_modules() -> tuple[str, ...]:
    """The imports pywebview makes to reach a native window, by platform."""
    if sys.platform == "win32":
        return ("clr", "webview.platforms.winforms")
    if sys.platform == "darwin":
        return ("webview.platforms.cocoa",)
    return ()


def selftest() -> int:
    """Verify a build can actually do its job, and report what it found.

    A PyInstaller bundle fails in a particular way: everything looks present on
    disk, and then an import that only happens at runtime is missing on the
    user's machine. Checking files exist does not catch that, so this imports
    what the app imports and exercises the parts that need no Resolve, no
    network and no credentials. CI runs it against the frozen executable.
    """
    import importlib
    import time

    results: list[tuple[bool, str]] = []

    def check(label, fn):
        try:
            results.append((True, f"{label}: {fn()}"))
        except Exception as exc:
            results.append((False, f"{label}: {type(exc).__name__}: {exc}"))

    check("frozen", lambda: bool(getattr(sys, "_MEIPASS", None)))
    check("frontend", lambda: frontend_index())

    # Imports PyInstaller has to have been told about; a missing hidden import
    # shows up here rather than the first time someone presses Transcribe.
    # bottle and webview.http back the local server the frontend is served from.
    # They are pure Python, so they live in the archive inside the exe where no
    # file listing can confirm them -- importing is the only proof.
    for module in ("webview", "webview.http", "bottle",
                   "kaggle.api.kaggle_api_extended", "requests"):
        check(f"import {module}", lambda m=module: importlib.import_module(m).__name__)

    # Importing `webview` alone proves nothing about the window opening: the GUI
    # backend is resolved later, and on Windows it drags in pythonnet and starts
    # a .NET runtime. A build shipped once where exactly that step failed on the
    # user's machine while every other check here passed, so exercise it.
    for module in _gui_backend_modules():
        check(f"import {module}", lambda m=module: importlib.import_module(m).__name__)

    from . import kaggle_runner, subtitle_utils

    check("kernel source", lambda: kaggle_runner.KERNEL_SOURCE.is_file()
          and kaggle_runner.KERNEL_SOURCE.read_text(encoding="utf-8").count("\n") > 100)

    # The pure logic, end to end: segments in, SRT text out.
    def srt_roundtrip():
        english, arabic = subtitle_utils.split_tagged_segments([
            {"start": 0.0, "end": 1.0, "text": "Okay.", "language": "en"},
            {"start": 1.2, "end": 2.0, "text": "لماذا؟", "language": "ar"},
        ])
        cues = subtitle_utils.merge_for_single_track(english, arabic)
        text = subtitle_utils.render_srt(cues)
        assert "Okay." in text and "لماذا؟" in text, text
        return f"{len(cues)} cues"

    check("srt round trip", srt_roundtrip)

    def serves_frontend():
        # The window is drawn from a local HTTP server now, not file://. That
        # server is the single point everything else depends on, so start the
        # real one against the real frontend and fetch the page back.
        import urllib.error
        import urllib.request

        from webview import http as wv_http

        index = frontend_index()
        address, _, server = wv_http.start_server(urls=[str(index)], http_port=None)
        url = f"{address}/index.html"
        # An empty ProxyHandler stops urllib from sending a loopback request to
        # whatever proxy the environment names, which is how this hangs on a CI
        # runner. The server also starts in a thread, so give it a few tries.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            last: Exception | None = None
            for _ in range(15):
                try:
                    with opener.open(url, timeout=2) as r:
                        body = r.read()
                    assert r.status == 200, r.status
                    assert b"<div id=\"root\">" in body, body[:200]
                    return f"{len(body)} bytes from {address}"
                except (urllib.error.URLError, OSError) as exc:
                    last = exc
                    time.sleep(0.5)
            raise AssertionError(f"no answer from {url}: {last}")
        finally:
            getattr(server, "shutdown", lambda: None)()

    check("serves frontend", serves_frontend)

    def config_roundtrip():
        # Serialise and rebuild without touching the user's saved settings.
        from . import config

        settings = config.Settings()
        rebuilt = config.Settings(**settings.to_dict())
        assert rebuilt.backend == settings.backend
        return f"{len(settings.to_dict())} fields, backend={rebuilt.backend}"

    check("config round trip", config_roundtrip)

    failed = [line for ok, line in results if not ok]
    report = "\n".join(f"{'PASS' if ok else 'FAIL'}  {line}" for ok, line in results)
    report += f"\n\n{len(results) - len(failed)}/{len(results)} checks passed"

    # A windowed build has no console on Windows, so printing the report reaches
    # nobody there. --selftest-out gives CI something to read either way.
    out = _flag_value("--selftest-out")
    if out:
        Path(out).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 1 if failed else 0


WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def _renderer_is_ancient() -> bool:
    """True when pywebview is about to draw the UI with Internet Explorer.

    Windows needs .NET 4.6.2+ and the WebView2 runtime. Without both, pywebview
    falls back to MSHTML and only writes a log warning — which nothing here
    reads, so the app would open on a blank window with nothing to explain it.
    A Vite bundle cannot run in that engine at all.
    """
    if sys.platform != "win32":
        return False
    try:
        from webview.platforms import winforms

        return getattr(winforms, "renderer", "") == "mshtml"
    except Exception:  # noqa: BLE001  # Never block startup on the check itself.
        return False


def _webview_storage_path() -> str | None:
    """Where WebView2 may keep its working files.

    Left alone, pywebview points WebView2 at ``TemporaryDirectory().name`` --
    a path whose object is garbage collected immediately, so it can be deleted
    out from under the browser -- or, if it falls back to the folder beside the
    exe, at somewhere unwritable when the portable build sits in Program Files.
    A per-user directory is stable and always writable.
    """
    if sys.platform != "win32":
        return None
    from . import config

    path = config.config_dir() / "webview"
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK):
            return None
    except OSError:
        return None  # pywebview's own fallback is better than refusing to start.
    return str(path)


def start_logging() -> Path | None:
    """Record this run to a file, overwriting the last one.

    A windowed Windows build has no console, so when the app misbehaves there
    is nothing to read. pywebview logs which renderer it chose and how the page
    loaded at debug level, which is exactly what is needed to tell "the bridge
    never arrived" apart from "the bridge was slow".
    """
    import logging

    from . import config

    path = config.config_dir() / "last-run.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    except OSError:
        return None
    # pywebview takes its level from the environment and defaults to INFO, so
    # the interesting lines -- which renderer it picked, what URL it loaded --
    # are missing without this. Set before webview is imported.
    os.environ.setdefault("PYWEBVIEW_LOG", "DEBUG")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    # INFO at the root keeps the network libraries quiet; webview is the part
    # worth reading in full.
    root.setLevel(logging.INFO)
    logging.getLogger("pywebview").setLevel(logging.DEBUG)
    logging.getLogger("webview").setLevel(logging.DEBUG)
    return path


BRIDGE_PROBE = """(function () {
  try {
    var pw = window.pywebview;
    return JSON.stringify({
      url: String(location.href),
      pywebview: typeof pw,
      token: pw ? typeof pw.token : "n/a",
      createApi: pw ? typeof pw._createApi : "n/a",
      methods: pw && pw.api ? Object.keys(pw.api) : null,
      errors: window.__diagErrors || []
    });
  } catch (e) { return JSON.stringify({ probeError: String(e) }); }
})()"""


def watch_bridge(window) -> None:
    """Log what the page can actually see, a few times, then stop.

    The JavaScript side cannot report a broken bridge over that same bridge, and
    a windowed build has no console. Reading the page from Python sidesteps both:
    evaluate_js is the Window API and does not depend on window.pywebview.api
    being populated.
    """
    import logging
    import threading
    import time

    log = logging.getLogger(__name__)

    def run() -> None:
        for delay in (5, 10, 25):
            time.sleep(delay if delay == 5 else delay - 5)
            try:
                log.info("bridge after ~%ss: %s", delay, window.evaluate_js(BRIDGE_PROBE))
            except Exception as exc:  # noqa: BLE001
                log.warning("bridge probe failed after ~%ss: %s", delay, exc)

    threading.Thread(target=run, daemon=True).start()


def _fatal(message: str) -> None:
    """Report a startup failure. A windowed build has no console to print to."""
    print(message, file=sys.stderr)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, WINDOW_TITLE, 0x10)
        except Exception:
            pass  # Nothing left to fall back to; the exit code still reports it.
    raise SystemExit(1)


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())

    log_path = start_logging()

    import webview

    from .api_bridge import Api

    import logging

    logging.getLogger(__name__).info(
        "Krevon Scribe starting on %s, frontend %s", sys.platform, frontend_index(),
    )

    if _renderer_is_ancient():
        _fatal(
            "Krevon Scribe needs the Microsoft Edge WebView2 runtime, which "
            "this PC does not have.\n\n"
            "Install it (the free Evergreen Runtime) from:\n"
            f"{WEBVIEW2_URL}\n\n"
            "Windows 11 and up-to-date Windows 10 include it already. "
            "If the PC is older, .NET Framework 4.6.2 or newer is needed too."
        )

    api = Api()
    window = webview.create_window(
        WINDOW_TITLE,
        str(frontend_index()),
        js_api=api,
        width=940,
        height=820,
        min_size=(720, 640),
        background_color="#0f0e13",
    )
    api._window = window  # underscored on purpose; see Api.__init__
    watch_bridge(window)
    # debug=True opens the inspector; keep it off for released builds.
    try:
        # http_server=True serves the frontend over 127.0.0.1 instead of file://.
        # pywebview documents file:// as not fully supported, and on Windows the
        # page rendered while the js_api bridge never attached, leaving the UI
        # with no window.pywebview.api to call. A real origin fixes that, and
        # costs nothing on macOS, where file:// happened to work.
        webview.start(
            debug="--debug" in sys.argv,
            http_server=True,
            storage_path=_webview_storage_path(),
        )
    except RuntimeError as exc:
        if "Python.Runtime" not in str(exc):
            raise
        # Windows blocked the .NET assembly the window is drawn through. The
        # traceback for this names only internals, so say what to do instead.
        _fatal(
            "Windows blocked a file this app needs.\n\n"
            "Files extracted from a downloaded zip are marked as untrusted, and "
            ".NET refuses to load them. To clear the mark, open PowerShell in "
            "the folder you unzipped and run:\n\n"
            "    Get-ChildItem -Recurse | Unblock-File\n\n"
            "Then start Krevon Scribe again. Unzipping to a local drive rather "
            "than a network drive avoids this too."
            + (f"\n\nDetails were written to:\n{log_path}" if log_path else "")
        )


if __name__ == "__main__":
    main()
