"""Frozen-app entry point.

PyInstaller needs a plain module-level script to start from; keeping it at the
repository root also makes `python app.py` the same command from source.
"""

from resolve_subtitle_tool.main import main

if __name__ == "__main__":
    main()
