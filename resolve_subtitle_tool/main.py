"""Entry point: opens the pywebview window around the built React frontend."""

from __future__ import annotations

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
    for module in ("webview", "kaggle.api.kaggle_api_extended", "requests"):
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

    import webview

    from .api_bridge import Api

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
    api.window = window
    # debug=True opens the inspector; keep it off for released builds.
    try:
        # http_server=True serves the frontend over 127.0.0.1 instead of file://.
        # pywebview documents file:// as not fully supported, and on Windows the
        # page rendered while the js_api bridge never attached, leaving the UI
        # with no window.pywebview.api to call. A real origin fixes that, and
        # costs nothing on macOS, where file:// happened to work.
        webview.start(debug="--debug" in sys.argv, http_server=True)
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
        )


if __name__ == "__main__":
    main()
