"""Rasterise the Krevon mark into the icon containers each platform wants.

    python scripts/make_icons.py --ico     # assets/krevon.ico, runs anywhere
    python scripts/make_icons.py --icns    # assets/krevon.icns, needs iconutil
    python scripts/make_icons.py           # both

The rasteriser is here rather than shelled out to a platform tool. The previous
version rendered through macOS's ``qlmanage``, which composites onto **white**:
every icon in the committed .ico had opaque white corners, so Windows drew a
white frame around a dark tile in the taskbar and the title bar. Nothing about
that is visible in a file listing, and there is no Windows equivalent of
qlmanage to swap in, so the drawing happens here instead.

The mark is a handful of rounded rectangles and round-capped strokes, which are
exactly the shapes that have short signed-distance functions, so the whole
renderer is the SDF of each shape plus analytic coverage for the antialiasing.
The SVGs stay the source of truth: this parses them, and refuses to guess at any
construct it was not taught.
"""

from __future__ import annotations

import argparse
import math
import re
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# macOS draws its own drop shadow and expects the squircle to sit inside a
# margin; Windows and the web want the tile edge-to-edge.
FULL_BLEED = ASSETS / "krevon-icon.svg"
MACOS = ASSETS / "krevon-icon-macos.svg"

ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

SVG_NS = "{http://www.w3.org/2000/svg}"


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

def _color(text: str) -> tuple[float, float, float, float] | None:
    """``#rgb`` / ``#rrggbb`` / ``#rrggbbaa`` to floats, or None for "none"."""
    text = (text or "").strip()
    if not text or text == "none":
        return None
    if not text.startswith("#"):
        raise SystemExit(f"Only hex colours are supported, got {text!r}")
    digits = text[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    if len(digits) == 6:
        digits += "ff"
    if len(digits) != 8:
        raise SystemExit(f"Cannot read colour {text!r}")
    r, g, b, a = (int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4, 6))
    return r, g, b, a


class Solid:
    def __init__(self, rgba):
        self.rgba = rgba

    def at(self, _x, _y):
        return self.rgba


class VerticalGradient:
    """A two-stop gradient down the bounding box, which is all the mark uses."""

    def __init__(self, top, bottom, y0, height):
        self.top, self.bottom = top, bottom
        self.y0 = y0
        self.height = height or 1.0

    def at(self, _x, y):
        t = min(1.0, max(0.0, (y - self.y0) / self.height))
        a, b = self.top, self.bottom
        return (a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
                a[3] + (b[3] - a[3]) * t)


# --------------------------------------------------------------------------
# Shapes, in root user space
# --------------------------------------------------------------------------

class RoundRect:
    """Filled when ``half_stroke`` is None, otherwise its outline."""

    def __init__(self, x, y, w, h, r, paint, half_stroke=None):
        self.cx, self.cy = x + w / 2, y + h / 2
        self.hx, self.hy = w / 2, h / 2
        self.r = min(r, self.hx, self.hy)
        self.paint = paint
        self.half_stroke = half_stroke
        pad = (half_stroke or 0.0)
        self.bounds = (x - pad, y - pad, x + w + pad, y + h + pad)

    def distance(self, px, py):
        qx = abs(px - self.cx) - (self.hx - self.r)
        qy = abs(py - self.cy) - (self.hy - self.r)
        d = min(max(qx, qy), 0.0) + math.hypot(max(qx, 0.0), max(qy, 0.0)) - self.r
        return abs(d) - self.half_stroke if self.half_stroke is not None else d


class Capsule:
    """A line segment with round caps — every stroke in the mark is one."""

    def __init__(self, ax, ay, bx, by, half_stroke, paint):
        self.ax, self.ay, self.bx, self.by = ax, ay, bx, by
        self.half_stroke = half_stroke
        self.paint = paint
        self.bounds = (min(ax, bx) - half_stroke, min(ay, by) - half_stroke,
                       max(ax, bx) + half_stroke, max(ay, by) + half_stroke)

    def distance(self, px, py):
        pax, pay = px - self.ax, py - self.ay
        bax, bay = self.bx - self.ax, self.by - self.ay
        span = bax * bax + bay * bay
        h = 0.0 if span == 0 else min(1.0, max(0.0, (pax * bax + pay * bay) / span))
        return math.hypot(pax - bax * h, pay - bay * h) - self.half_stroke


# --------------------------------------------------------------------------
# SVG reading
# --------------------------------------------------------------------------

_TRANSFORM = re.compile(r"(translate|scale)\(([^)]*)\)")
_NUMBERS = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _transform(text: str, offset, scale):
    """Fold ``translate``/``scale`` into the running (offset, uniform scale)."""
    ox, oy = offset
    for kind, args in _TRANSFORM.findall(text or ""):
        nums = [float(n) for n in _NUMBERS.findall(args)]
        if kind == "translate":
            dx = nums[0]
            dy = nums[1] if len(nums) > 1 else 0.0
            ox, oy = ox + dx * scale, oy + dy * scale
        else:
            if len(nums) > 1 and nums[0] != nums[1]:
                raise SystemExit("Only uniform scale() is supported")
            scale *= nums[0]
    return (ox, oy), scale


def _gradients(root) -> dict:
    out = {}
    for node in root.iter(f"{SVG_NS}linearGradient"):
        if node.get("x1", "0") != node.get("x2", "0"):
            raise SystemExit("Only vertical gradients are supported")
        stops = [(float(s.get("offset", 0)), _color(s.get("stop-color", "")))
                 for s in node.findall(f"{SVG_NS}stop")]
        if len(stops) != 2:
            raise SystemExit("Gradients need exactly two stops")
        stops.sort(key=lambda s: s[0])
        out[node.get("id", "")] = (stops[0][1], stops[1][1])
    return out


def _paint(value, gradients, y0, height):
    if value and value.startswith("url(#"):
        name = value[5:].rstrip(")")
        if name not in gradients:
            raise SystemExit(f"Unknown gradient {name!r}")
        top, bottom = gradients[name]
        return VerticalGradient(top, bottom, y0, height)
    rgba = _color(value)
    return Solid(rgba) if rgba else None


def _path_points(d: str) -> list[tuple[float, float]]:
    """Read the M/L/V/H subset the mark is drawn with."""
    tokens = re.findall(r"[MLVHmlvh]|-?\d*\.?\d+", d)
    points: list[tuple[float, float]] = []
    x = y = 0.0
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd not in "MLVHmlvh":
            raise SystemExit(f"Unsupported path data: {d!r}")
        i += 1
        if cmd in "MLml":
            dx, dy = float(tokens[i]), float(tokens[i + 1])
            i += 2
            x, y = (x + dx, y + dy) if cmd.islower() else (dx, dy)
        elif cmd in "Vv":
            dy = float(tokens[i]); i += 1
            y = y + dy if cmd == "v" else dy
        else:
            dx = float(tokens[i]); i += 1
            x = x + dx if cmd == "h" else dx
        points.append((x, y))
    if len(points) != 2:
        raise SystemExit(f"Expected a two-point path, got {len(points)}: {d!r}")
    return points


def _walk(node, inherited, offset, scale, gradients, shapes):
    style = dict(inherited)
    for key in ("fill", "stroke", "stroke-width", "stroke-linecap"):
        if node.get(key) is not None:
            style[key] = node.get(key)
    offset, scale = _transform(node.get("transform", ""), offset, scale)

    tag = node.tag
    if tag == f"{SVG_NS}rect":
        x = float(node.get("x", 0)) * scale + offset[0]
        y = float(node.get("y", 0)) * scale + offset[1]
        w = float(node.get("width", 0)) * scale
        h = float(node.get("height", 0)) * scale
        r = float(node.get("rx", 0)) * scale
        fill = _paint(style.get("fill", "#000000"), gradients, y, h)
        if fill is not None:
            shapes.append(RoundRect(x, y, w, h, r, fill))
        stroke = _paint(style.get("stroke", "none"), gradients, y, h)
        if stroke is not None:
            width = float(style.get("stroke-width", 1)) * scale
            shapes.append(RoundRect(x, y, w, h, r, stroke, half_stroke=width / 2))
    elif tag == f"{SVG_NS}path":
        stroke = _paint(style.get("stroke", "none"), gradients, 0, 1)
        if stroke is None:
            raise SystemExit("Paths in the mark are strokes; this one has none")
        if style.get("stroke-linecap") != "round":
            raise SystemExit("Only round line caps are supported")
        (ax, ay), (bx, by) = _path_points(node.get("d", ""))
        width = float(style.get("stroke-width", 1)) * scale
        shapes.append(Capsule(
            ax * scale + offset[0], ay * scale + offset[1],
            bx * scale + offset[0], by * scale + offset[1],
            width / 2, stroke,
        ))
    elif tag not in (f"{SVG_NS}svg", f"{SVG_NS}g", f"{SVG_NS}defs",
                     f"{SVG_NS}title", f"{SVG_NS}linearGradient", f"{SVG_NS}stop"):
        raise SystemExit(f"Unsupported SVG element: {tag}")

    if tag in (f"{SVG_NS}svg", f"{SVG_NS}g"):
        for child in node:
            _walk(child, style, offset, scale, gradients, shapes)


def read_svg(path: Path) -> tuple[float, list]:
    """Return ``(viewBox side, shapes)`` flattened into root user space."""
    root = ET.parse(path).getroot()
    box = [float(n) for n in _NUMBERS.findall(root.get("viewBox", ""))]
    if len(box) != 4 or box[0] or box[1] or box[2] != box[3]:
        raise SystemExit(f"{path.name} needs a square viewBox starting at 0 0")
    shapes: list = []
    _walk(root, {}, (0.0, 0.0), 1.0, _gradients(root), shapes)
    if not shapes:
        raise SystemExit(f"{path.name} produced nothing to draw")
    return box[2], shapes


# --------------------------------------------------------------------------
# Rasterising
# --------------------------------------------------------------------------

def rasterise(side: float, shapes: list, size: int) -> bytearray:
    """Draw at ``size`` pixels square, returning straight-alpha RGBA rows.

    Coverage comes from the distance field rather than from supersampling: one
    pixel is one unit wide in device space, so a distance of half a pixel either
    side of the edge is the whole antialiased ramp. The background stays
    transparent, which is the entire point of this rewrite.
    """
    unit = side / size          # user units per device pixel
    half = unit / 2
    # Premultiplied RGBA accumulator, so compositing is a single lerp.
    buf = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]

    for shape in shapes:
        x0, y0, x1, y1 = shape.bounds
        # Only touch the rows and columns the shape can reach, plus a pixel of
        # slack for the antialiased edge.
        cmin = max(0, int((x0 - unit) / unit))
        cmax = min(size - 1, int((x1 + unit) / unit))
        rmin = max(0, int((y0 - unit) / unit))
        rmax = min(size - 1, int((y1 + unit) / unit))
        paint = shape.paint
        distance = shape.distance
        for row in range(rmin, rmax + 1):
            py = row * unit + half
            base = row * size
            for col in range(cmin, cmax + 1):
                d = distance(col * unit + half, py)
                if d >= half:
                    continue
                coverage = 1.0 if d <= -half else (half - d) / unit
                r, g, b, a = paint.at(col * unit + half, py)
                sa = a * coverage
                if sa <= 0.0:
                    continue
                dst = buf[base + col]
                inv = 1.0 - sa
                dst[0] = r * sa + dst[0] * inv
                dst[1] = g * sa + dst[1] * inv
                dst[2] = b * sa + dst[2] * inv
                dst[3] = sa + dst[3] * inv

    out = bytearray(size * size * 4)
    for i, (r, g, b, a) in enumerate(buf):
        j = i * 4
        if a > 0.0:
            out[j] = min(255, int(r / a * 255 + 0.5))
            out[j + 1] = min(255, int(g / a * 255 + 0.5))
            out[j + 2] = min(255, int(b / a * 255 + 0.5))
            out[j + 3] = min(255, int(a * 255 + 0.5))
    return out


def encode_png(rgba: bytearray, size: int) -> bytes:
    """Minimal RGBA PNG. Filter 0 on every row keeps this to a few lines."""
    stride = size * 4
    raw = bytearray()
    for row in range(size):
        raw.append(0)
        raw += rgba[row * stride:(row + 1) * stride]

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def render(svg: Path, size: int) -> bytes:
    side, shapes = read_svg(svg)
    return encode_png(rasterise(side, shapes, size), size)


# --------------------------------------------------------------------------
# Containers
# --------------------------------------------------------------------------

def build_ico() -> Path:
    """Pack PNGs into an .ico by hand — no Pillow in this project's deps."""
    images = [(size, render(FULL_BLEED, size)) for size in ICO_SIZES]

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


def build_icns() -> Path:
    """Pack the .icns. Only the packing step needs macOS, via iconutil."""
    if sys.platform != "darwin":
        raise SystemExit("Building the .icns needs macOS (iconutil).")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "krevon.iconset"
        iconset.mkdir(parents=True)
        for size in ICNS_SIZES:
            # Every size is drawn from the vector rather than downscaled, so the
            # 16px mark stays crisp instead of turning to grey mush.
            data = render(MACOS, size)
            if size <= 512:
                (iconset / f"icon_{size}x{size}.png").write_bytes(data)
            if size >= 32:
                (iconset / f"icon_{size // 2}x{size // 2}@2x.png").write_bytes(data)
        out = ASSETS / "krevon.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                       check=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Krevon icon files.")
    ap.add_argument("--ico", action="store_true", help="Build assets/krevon.ico")
    ap.add_argument("--icns", action="store_true", help="Build assets/krevon.icns")
    args = ap.parse_args()
    both = not args.ico and not args.icns

    for svg in (FULL_BLEED, MACOS):
        if not svg.is_file():
            raise SystemExit(f"Missing {svg.relative_to(ROOT)}")

    written = []
    if args.ico or both:
        written.append(build_ico())
    if args.icns or both:
        written.append(build_icns())
    for path in written:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
