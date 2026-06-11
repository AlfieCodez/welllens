"""Generate WellLens PWA icons: a white leaf on the brand green tile.

Reproduces the leaf stroke from the auth portal's SVG (24x24 viewBox) by
sampling its cubic Beziers, then rasterising at each target size.

Run from the project root:
    py scripts/generate_icons.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "welllens" / "static" / "icons"

GREEN = (65, 97, 58)      # --green #41613A
LEAF = (246, 243, 236)    # #F6F3EC (off-white, matches the portal stroke)

# The leaf path from welllens_auth.html, as cubic Bezier segments in a 24x24 box.
# Each segment: (P0, C1, C2, P3).
SEGMENTS = [
    ((20, 4),    (20, 4),    (8, 4),     (5.5, 11.5)),
    ((5.5, 11.5),(3.6, 17.2),(7, 20),    (7, 20)),
    ((7, 20),    (7, 20),    (8, 13),    (13, 9.5)),
    ((13, 9.5),  (9.8, 13),  (8.5, 16.5),(8.5, 19.5)),
]


def _bezier(p0, c1, c2, p3, steps=60):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt**3 * p0[0] + 3 * mt**2 * t * c1[0]
             + 3 * mt * t**2 * c2[0] + t**3 * p3[0])
        y = (mt**3 * p0[1] + 3 * mt**2 * t * c1[1]
             + 3 * mt * t**2 * c2[1] + t**3 * p3[1])
        pts.append((x, y))
    return pts


def _leaf_points():
    pts = []
    for seg in SEGMENTS:
        pts.extend(_bezier(*seg))
    return pts


def make_icon(size, maskable=False):
    # Supersample for smooth edges.
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded tile background. Maskable icons fill the whole square (no radius)
    # so platform masks can crop cleanly; normal icons get rounded corners.
    if maskable:
        d.rectangle([0, 0, big, big], fill=GREEN)
        leaf_frac = 0.52   # keep leaf inside the safe zone
    else:
        radius = int(big * 0.22)
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=GREEN)
        leaf_frac = 0.62

    # Scale + centre the 24x24 leaf.
    target = big * leaf_frac
    scale = target / 24.0
    offset = (big - target) / 2.0
    stroke_w = max(2, int(1.7 * scale))

    pts = [(offset + x * scale, offset + y * scale) for x, y in _leaf_points()]
    d.line(pts, fill=LEAF, width=stroke_w, joint="curve")
    # Round the stroke ends.
    for end in (pts[0], pts[-1]):
        r = stroke_w / 2
        d.ellipse([end[0] - r, end[1] - r, end[0] + r, end[1] + r], fill=LEAF)

    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    specs = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-192-maskable.png", 192, True),
        ("icon-512-maskable.png", 512, True),
        ("apple-touch-icon.png", 180, False),
        ("favicon-32.png", 32, False),
    ]
    for name, size, maskable in specs:
        make_icon(size, maskable).save(OUT / name)
        print(f"  wrote {name} ({size}x{size}{', maskable' if maskable else ''})")
    print(f"\nIcons written to {OUT}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
