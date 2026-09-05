# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. Produces a self-contained folder that runs without a
Python install — zip it and it is the portable Windows build.

The frontend must be built first; scripts/build.py handles the whole sequence.
"""

import sys
from pathlib import Path

APP_NAME = "KrevonScribe"
ROOT = Path(SPECPATH)
FRONTEND = ROOT / "resolve_subtitle_tool" / "frontend_dist"
ASSETS = ROOT / "assets"

if not (FRONTEND / "index.html").is_file():
    raise SystemExit(
        "resolve_subtitle_tool/frontend_dist/index.html is missing.\n"
        "Build the frontend first:  python scripts/build.py"
    )

datas = [
    (str(FRONTEND), "frontend_dist"),
    # The kernel is read off disk and uploaded to Kaggle at runtime.
    (str(ROOT / "resolve_subtitle_tool" / "kaggle_kernel" / "transcribe_kernel.py"),
     "resolve_subtitle_tool/kaggle_kernel"),
]

hiddenimports = [
    "webview",
    "kaggle",
    "kaggle.api.kaggle_api_extended",
]
if sys.platform == "win32":
    # pywebview reaches WebView2 through pythonnet; PyInstaller cannot see
    # these imports because they are resolved dynamically at runtime.
    hiddenimports += ["clr", "webview.platforms.edgechromium", "webview.platforms.winforms"]
elif sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa"]
else:
    hiddenimports += ["webview.platforms.gtk", "webview.platforms.qt"]

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trimming these keeps the portable build a few hundred MB smaller.
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy", "PIL", "PySide6", "PyQt5"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app: no console window on Windows
    icon=str(ASSETS / "krevon.ico") if sys.platform == "win32" else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[], name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ASSETS / "krevon.icns"),
        bundle_identifier="com.krevon.scribe",
        info_plist={
            "CFBundleName": "Krevon Scribe",
            "CFBundleDisplayName": "Krevon Scribe",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
