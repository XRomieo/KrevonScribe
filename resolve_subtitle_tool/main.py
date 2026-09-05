"""Entry point: opens the pywebview window around the built React frontend."""

from __future__ import annotations

import sys
from pathlib import Path

# webview is imported inside main(), not here: it pulls in a GUI toolkit, and
# this module must stay importable without one so --selftest and the test suite
# can reach it on a machine that has neither.

WINDOW_TITLE = "Resolve EN/AR Subtitles"


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
        width=1080,
        height=780,
        min_size=(880, 620),
    )
    api.window = window
    # debug=True opens the inspector; keep it off for released builds.
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
