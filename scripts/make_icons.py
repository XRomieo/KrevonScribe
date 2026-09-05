"""Rasterise the Krevon mark into the icon containers each platform wants.

Run on macOS: it uses qlmanage to render the SVG and iconutil to pack the
.icns. The results are committed, because the Windows build runs on a machine
that has neither, and PyInstaller needs the .ico at bundle time.

    python scripts/make_icons.py
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# macOS draws its own drop shadow and expects the squircle to sit inside a
# margin; Windows and the web want the tile edge-to-edge.
FULL_BLEED = ASSETS / "krevon-icon.svg"
MACOS = ASSETS / "krevon-icon-macos.svg"

ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(svg: Path, size: int, out: Path) -> Path:
    """Rasterise ``svg`` to a square PNG of ``size`` pixels."""
    if sys.platform != "darwin":
        raise SystemExit("This script needs macOS (qlmanage + iconutil).")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["qlmanage", "-t", "-s", str(size), "-o", tmp, str(svg)],
            check=True, capture_output=True,
        )
        produced = next(Path(tmp).glob("*.png"), None)
        if produced is None:
            raise SystemExit(f"qlmanage rendered nothing for {svg}")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(produced.read_bytes())
    # qlmanage rounds to its own idea of the thumbnail box; force the exact size.
    subprocess.run(
        ["sips", "-z", str(size), str(size), str(out)], check=True, capture_output=True
    )
    return out


def build_icns(work: Path) -> Path:
    iconset = work / "krevon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for size in ICNS_SIZES:
        # Every size is rendered from the vector rather than downscaled, so the
        # 16px mark stays crisp instead of turning to grey mush.
        if size <= 512:
            render(MACOS, size, iconset / f"icon_{size}x{size}.png")
        if size >= 32:
            render(MACOS, size, iconset / f"icon_{size // 2}x{size // 2}@2x.png")
    out = ASSETS / "krevon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    return out


def build_ico(work: Path) -> Path:
    """Pack PNGs into an .ico by hand — no Pillow in this project's deps."""
    images = []
    for size in ICO_SIZES:
        png = render(FULL_BLEED, size, work / f"ico_{size}.png")
        images.append((size, png.read_bytes()))

    header = struct.pack("<HHH", 0, 1, len(images))  # reserved, type=icon, count
    entries, blobs = b"", b""
    offset = len(header) + 16 * len(images)
    for size, data in images:
        # 256 is stored as 0 in the single-byte width/height fields.
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)

    out = ASSETS / "krevon.ico"
    out.write_bytes(header + entries + blobs)
    return out


def main() -> None:
    for svg in (FULL_BLEED, MACOS):
        if not svg.is_file():
            raise SystemExit(f"Missing {svg.relative_to(ROOT)}")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        icns = build_icns(work)
        ico = build_ico(work)
    for path in (icns, ico):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
