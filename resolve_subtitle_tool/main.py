"""Entry point: opens the pywebview window around the built React frontend."""

from __future__ import annotations

import sys
from pathlib import Path

import webview

from .api_bridge import Api

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


def main() -> None:
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
