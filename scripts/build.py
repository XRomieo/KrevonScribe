"""Build the whole app: frontend -> staged assets -> PyInstaller bundle.

Runs the same way on macOS and Windows. PyInstaller cannot cross-compile, so
the Windows executable must be produced on Windows (CI does this).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
STAGED = ROOT / "resolve_subtitle_tool" / "frontend_dist"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(cmd)
    print(f"\n$ {printable}", flush=True)
    # shell=True on Windows so `bun`/`bunx` .cmd shims resolve.
    result = subprocess.run(cmd, cwd=cwd, shell=(sys.platform == "win32"))
    if result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {printable}")


def build_frontend(skip_install: bool) -> None:
    if shutil.which("bun") is None and sys.platform != "win32":
        raise SystemExit("bun is not on PATH. Install it from https://bun.sh")
    if not skip_install:
        run(["bun", "install"], cwd=FRONTEND)
    run(["bun", "run", "build"], cwd=FRONTEND)

    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit(f"Frontend build produced no index.html in {dist}")
    if STAGED.exists():
        shutil.rmtree(STAGED)
    shutil.copytree(dist, STAGED)
    print(f"Staged frontend -> {STAGED.relative_to(ROOT)}")


# .NET Framework refuses to load an assembly whose file is marked as coming
# from another zone, and Windows marks every file extracted from a downloaded
# zip that way. pywebview reaches WebView2 through pythonnet, so that refusal
# stops the app before its window opens, with a traceback ending in
# "Failed to resolve Python.Runtime.Loader.Initialize". Telling the runtime to
# trust remote sources lifts it. The CLR reads this file by the host process's
# name, so it has to sit beside the exe, not under _internal/.
EXE_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true" />
  </runtime>
  <startup>
    <supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0" />
  </startup>
</configuration>
"""


def build_bundle() -> None:
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "app.spec"], cwd=ROOT)
    if sys.platform == "win32":
        target = ROOT / "dist" / "KrevonScribe" / "KrevonScribe.exe.config"
        target.write_text(EXE_CONFIG, encoding="utf-8")
        print(f"Wrote {target.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Krevon Scribe.")
    ap.add_argument("--frontend-only", action="store_true")
    ap.add_argument("--skip-install", action="store_true",
                    help="Reuse the existing node_modules instead of running bun install.")
    args = ap.parse_args()

    build_frontend(args.skip_install)
    if args.frontend_only:
        print("\nFrontend built. Run from source with:  python app.py")
        return
    build_bundle()

    out = ROOT / "dist"
    print(f"\nDone. Bundle in {out}")
    for child in sorted(out.glob("*")):
        print(f"  {child.name}")


if __name__ == "__main__":
    main()
