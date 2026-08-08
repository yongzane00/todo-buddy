"""Rebuild an AI-rendered cat animation into a clean transparent sprite sheet.

Input:  asset/cat_animation/_source/<NAME>.png  (e.g. a 1536x1024 render with a
        grey background, glow, blur, and ~6.5px pseudo-pixel blocks)
Output: asset/cat_animation/<NAME>.png  (N frames x 64x64, hard {0,255} alpha,
        snapped to the shared 8-color cat palette, no anti-aliasing, body
        centered per frame, bottom on the shared baseline row 55)

Current sheets come from one labeled 5-row grid image (rows in GRID_ROWS
order; text labels at the left are stripped automatically):

    python tools/build_cat_sheet.py Animated_kumquat.jpeg --grid

Legacy per-state commands for single-row renders (the ones these consumed
now live only in git history; add --preview to any command for a 6x review
image):

    python tools/build_cat_sheet.py AWAKE_IDLE
    python tools/build_cat_sheet.py SLEEPING --glyph z
    python tools/build_cat_sheet.py WAKE_UP  --align per-frame
    python tools/build_cat_sheet.py HAPPY    --glyph heart --min-blob 25
    python tools/build_cat_sheet.py ANGRY    --glyph anger --min-blob 12

Frame spans are auto-detected from the sprite mask, so renders don't need to
sit on an exact grid. The source-to-output scale is fixed so every state sheet
keeps the same pixel density as AWAKE_IDLE (44 output px per 157 source px);
poses too tall for the canvas (HAPPY's jump) shrink slightly instead of
clipping. Floating glyphs (sleep z's, anger marks, the heart) turn to mush at
this scale, so the --glyph modes erase them and stamp crisp pixel versions at
the source positions. Requires numpy and Pillow: pip install -e ".[tools]"
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO / "asset" / "cat_animation" / "_source"
OUT_DIR = REPO / "asset" / "cat_animation"

FRAME = 64
SCALE = 44 / 157          # matches the AWAKE_IDLE sheet's pixel density
BASELINE = 56             # output y edge below the body (last drawn row = 55)
ANCHOR_X = 31.5           # output x where the body centre lands in every frame
ALPHA_THRESHOLD = 0.45
MIN_FRAME_WIDTH = 40      # source px; ignore stray mask runs narrower than this
FRAME_GAP = 12            # merge mask runs separated by fewer empty columns

PALETTE = np.array([
    [0x24, 0x07, 0x38],   # outline / ink (also the sleep "Z" glyphs)
    [0xD9, 0x3F, 0x06],   # dark orange (stripes, shading)
    [0xFE, 0x7E, 0x0A],   # base orange
    [0xFC, 0xB1, 0x3A],   # light orange
    [0xFC, 0xD0, 0x78],   # pale orange
    [0xFE, 0xEB, 0xA3],   # cream (muzzle, belly, paws)
    [0xDE, 0x30, 0x4A],   # red (heart, tongue, anger marks)
    [0x99, 0x14, 0x35],   # deep red (heart shading, mouth)
], dtype=int)
RED = 6  # PALETTE index used for stamped anger glyphs


def sprite_mask(rgb: np.ndarray, exclude_red: bool = False) -> np.ndarray:
    """Sprite pixels vs. background/glow: saturated orange, dark ink, or cream.

    exclude_red drops red/crimson pixels entirely (used for ANGRY, whose neon
    anger marks bleed a red bloom that is chromatically identical to the marks
    and would otherwise pollute the sprite). Oranges have a large green-blue
    gap; reds do not, which separates the two without touching the cat.
    """
    sat = rgb.max(2) - rgb.min(2)
    lum = rgb.mean(2)
    mask = (sat > 100) | (lum < 50) | ((lum > 180) & (sat > 55))
    if exclude_red:
        red = (
            (rgb[..., 0] > 150)
            & (rgb[..., 1] - rgb[..., 2] < 35)
            & (rgb[..., 2] > 40)
            & (lum > 90)  # keep dark reds: the tongue inside an open mouth
        )
        mask &= ~red
    return mask


ANGER_STAMP = [
    ".......X..",
    "XX.....X..",
    "XX...XXXXX",
    "..XX...X..",
    "..XX...X..",
]

HEART_STAMP = [
    ".XX..XX.",
    "XXXXXXXX",
    "XXXXXXXX",
    "xXXXXXXx",
    ".xXXXXx.",
    "..xXXx..",
    "...xx...",
]  # 'X' = red, 'x' = deep red shading


def stamp_heart(cell: np.ndarray, src: np.ndarray, span: tuple[int, int], body_top: int) -> bool:
    """Stamp a crisp heart near the top on frames whose source shows one.

    The jumping HAPPY cat nearly fills the 64px canvas, so the source heart
    maps above the frame; we re-home it in free space along the top, scanning
    for a spot that doesn't collide with the ears.
    """
    x0, x1 = span
    rgb = src[:, x0:x1 + 1]
    red = (rgb[..., 0] > 170) & (rgb[..., 0] - rgb[..., 1] > 110) & (rgb[..., 1] - rgb[..., 2] < 40)
    red[body_top + 10:, :] = False
    if red.sum() < 400:
        return False

    h, w = len(HEART_STAMP), len(HEART_STAMP[0])
    alpha = cell[..., 3] > 0
    for ox in range(FRAME - w - 1, 0, -1):  # prefer top-right, like the old Qt-painted heart
        window = alpha[0:h + 2, max(ox - 1, 0):ox + w + 1]
        if not window.any():
            for py, row in enumerate(HEART_STAMP):
                for px, ch in enumerate(row):
                    if ch == "X":
                        cell[1 + py, ox + px] = (*PALETTE[RED], 255)
                    elif ch == "x":
                        cell[1 + py, ox + px] = (*PALETTE[RED + 1], 255)
            return True
    return False


def stamp_anger_marks(
    cell: np.ndarray,
    src: np.ndarray,
    span: tuple[int, int],
    body_top: int,
    anchor: float,
    bottom_excl: int,
    scale: float,
) -> bool:
    """Stamp a crisp '.. +' anger mark where the source's red marks sit.

    The source marks are unrecoverable after downscaling (pure red shapes
    wrapped in an equally red bloom), so we take their per-frame centroid from
    the raw render — the bloom is symmetric around the marks, so the centroid
    is faithful, and the frame-to-frame drift keeps the animation alive.
    """
    x0, x1 = span
    rgb = src[:, x0:x1 + 1]
    red = (rgb[..., 0] > 170) & (rgb[..., 0] - rgb[..., 1] > 110) & (rgb[..., 1] - rgb[..., 2] < 40)
    red[body_top + 10:, :] = False
    ys, xs = np.nonzero(red)
    if len(ys) < 50:
        return False

    oy = round(BASELINE + (ys.mean() - bottom_excl) * scale) - len(ANGER_STAMP) // 2
    ox = round(ANCHOR_X + (xs.mean() + x0 - anchor) * scale) - len(ANGER_STAMP[0]) // 2
    oy = max(0, min(oy, FRAME - len(ANGER_STAMP)))
    ox = max(0, min(ox, FRAME - len(ANGER_STAMP[0])))
    for py, row in enumerate(ANGER_STAMP):
        for px, on in enumerate(row):
            if on == "X":
                cell[oy + py, ox + px] = (*PALETTE[RED], 255)
    return True


def detect_frames(mask: np.ndarray, expected: int = 0) -> list[tuple[int, int]]:
    cols = mask.sum(0)
    runs: list[list[int]] = []
    start = None
    for x, filled in enumerate(cols > 0):
        if filled and start is None:
            start = x
        elif not filled and start is not None:
            runs.append([start, x - 1])
            start = None
    if start is not None:
        runs.append([start, mask.shape[1] - 1])

    merged: list[list[int]] = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= FRAME_GAP:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    frames = [(x0, x1) for x0, x1 in merged if x1 - x0 + 1 >= MIN_FRAME_WIDTH]
    if not frames:
        raise SystemExit("no frames detected — check the source image")

    # Glow bridges can fuse neighbouring frames into one run. When the caller
    # knows the frame count, split the widest runs at their weakest column
    # (the bridge is a shallow trickle; the bodies are ~15x denser).
    col_density = mask.sum(0)
    while expected and len(frames) < expected:
        i = max(range(len(frames)), key=lambda k: frames[k][1] - frames[k][0])
        x0, x1 = frames[i]
        width = x1 - x0 + 1
        if width < 2 * MIN_FRAME_WIDTH:
            raise SystemExit(f"cannot split further: {len(frames)} frames found, {expected} expected")
        lo, hi = x0 + width // 4, x1 - width // 4
        cut = min(range(lo, hi + 1), key=lambda x: col_density[x])
        frames[i:i + 1] = [(x0, cut - 1), (cut + 1, x1)]
        frames.sort()
    return frames


def snap(color: np.ndarray) -> np.ndarray:
    """Nearest palette color; red entries only compete for genuinely red pixels.

    Without the hue gate, dark red-brown shadow pixels (tail shading) sit
    closer to the red entries than to dark orange and the cat grows crimson
    patches.
    """
    dist = ((color[None] - PALETTE) ** 2).sum(1).astype(float)
    is_red = (color[1] - color[2] < 35) and (color[0] - color[1] > 120) and (color[2] > 45)
    if not is_red:
        dist[RED:] = np.inf
    return PALETTE[dist.argmin()]


def demote_stray_reds(cell: np.ndarray) -> int:
    """Recolor isolated red pixels to dark orange.

    Genuine red features (tongue, heart, nose) are contiguous clusters;
    lone red pixels are fur-shading blends that slipped through the hue gate.
    """
    rgbv = cell[..., :3]
    redfam = (
        ((rgbv == PALETTE[RED]).all(2) | (rgbv == PALETTE[RED + 1]).all(2))
        & (cell[..., 3] > 0)
    )
    demoted = 0
    for y, x in zip(*np.nonzero(redfam)):
        neighbors = redfam[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2].sum() - 1
        if neighbors < 2:
            cell[y, x] = (*PALETTE[1], 255)
            demoted += 1
    return demoted


def despeckle(alpha: np.ndarray, min_blob: int) -> tuple[np.ndarray, list[int]]:
    """Keep 8-connected blobs of at least min_blob pixels."""
    h, w = alpha.shape
    seen = np.zeros_like(alpha, dtype=bool)
    keep = np.zeros_like(alpha, dtype=bool)
    sizes = []
    for sy in range(h):
        for sx in range(w):
            if not alpha[sy, sx] or seen[sy, sx]:
                continue
            stack, blob = [(sy, sx)], []
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                blob.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            sizes.append(len(blob))
            if len(blob) >= min_blob:
                for y, x in blob:
                    keep[y, x] = True
    return keep, sorted(sizes, reverse=True)


def _z_pattern(size: int) -> np.ndarray:
    """A crisp pixel-art 'z': full top and bottom rows, right-to-left diagonal."""
    z = np.zeros((size, size), dtype=bool)
    z[0, :] = True
    z[-1, :] = True
    for row in range(1, size - 1):
        z[row, size - 1 - row] = True
    return z


def redraw_glyphs(cell: np.ndarray) -> int:
    """Replace detached ink-only blobs (sleep 'z's) with crisp pixel z glyphs.

    The AI render's floating glyphs turn to mush when downscaled; the cat body
    survives fine. Blobs other than the largest whose pixels are all outline
    ink are erased and re-stamped as a clean 'z' sized to the blob.
    """
    alpha = cell[..., 3] > 0
    ink = (cell[..., :3] == PALETTE[0]).all(2) & alpha

    blobs: list[list[tuple[int, int]]] = []
    seen = np.zeros_like(alpha, dtype=bool)
    for sy in range(alpha.shape[0]):
        for sx in range(alpha.shape[1]):
            if not alpha[sy, sx] or seen[sy, sx]:
                continue
            stack, blob = [(sy, sx)], []
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                blob.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if (
                            0 <= ny < alpha.shape[0]
                            and 0 <= nx < alpha.shape[1]
                            and alpha[ny, nx]
                            and not seen[ny, nx]
                        ):
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            blobs.append(blob)

    if len(blobs) < 2:
        return 0
    body = max(blobs, key=len)
    replaced = 0
    for blob in blobs:
        if blob is body:
            continue
        ink_share = np.mean([ink[y, x] for y, x in blob])
        if ink_share < 0.9:
            continue
        ys = [y for y, _ in blob]
        xs = [x for _, x in blob]
        size = 5 if max(ys) - min(ys) + 1 <= 7 else 7 if max(ys) - min(ys) + 1 <= 10 else 9
        for y, x in blob:
            cell[y, x] = 0
        cy = round(sum(ys) / len(ys)) - size // 2
        cx = round(sum(xs) / len(xs)) - size // 2
        cy = max(0, min(cy, alpha.shape[0] - size))
        cx = max(0, min(cx, alpha.shape[1] - size))
        pattern = _z_pattern(size)
        for py, px in zip(*np.nonzero(pattern)):
            cell[cy + py, cx + px] = (*PALETTE[0], 255)
        replaced += 1
    return replaced


def load_masked(path: Path, exclude_red: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Load a render and its sprite mask.

    Renders with a real transparent background carry their own sprite mask;
    color-based background separation is only for opaque (grey/checker-bg)
    renders.
    """
    rgba = np.array(Image.open(path).convert("RGBA")).astype(int)
    src = rgba[..., :3]
    src_alpha = rgba[..., 3]
    if (src_alpha < 128).any():
        print(f"{path.name}: source has transparency; masking on alpha")
        return src, src_alpha >= 128
    return src, sprite_mask(src, exclude_red=exclude_red)


def build(name: str, min_blob: int, preview: bool, glyph: str = "none", expected_frames: int = 6, align: str = "median") -> None:
    src, mask = load_masked(SOURCE_DIR / f"{name}.png", exclude_red=glyph in ("anger", "heart"))
    process(name, src, mask, min_blob, preview, glyph, expected_frames, align)


def process(
    name: str,
    src: np.ndarray,
    mask: np.ndarray,
    min_blob: int,
    preview: bool,
    glyph: str = "none",
    expected_frames: int = 6,
    align: str = "median",
    scale_base: float | None = None,
    strip_label: bool = False,
) -> None:
    sat = src.max(2) - src.min(2)
    lum = src.mean(2)
    orange = (sat > 100) & (src[..., 1] - src[..., 2] > 35) & mask
    cream = (lum > 180) & (sat > 50) & (sat < 130) & mask

    # Grid rows carry an ink text label left of the first frame; it holds no
    # orange, so everything left of the first orange column is label.
    if strip_label:
        first_orange = int(np.nonzero(orange.any(0))[0].min())
        mask = mask.copy()
        mask[:, : max(first_orange - 8, 0)] = False

    frames = detect_frames(mask, expected_frames)
    print(f"{name}: {len(frames)} frames detected: {frames}")

    # Baseline: median of the per-frame sprite bottoms (outline included) —
    # outlier-resistant, so ANGRY's below-ground flame can't float the other
    # frames. 'per-frame' pins every frame's own bottom to the ground line
    # instead; right for sequences where each pose rests on the ground.
    frame_bottoms = [int(np.nonzero(mask[:, x0:x1 + 1])[0].max()) for x0, x1 in frames]
    bottom_excl = int(np.median(frame_bottoms)) + 1

    # Anchor on the cream muzzle centroid (stable while the tail moves), then
    # shift by a sheet-wide constant so the orange body is centred on average.
    cream_cx, body_cx, body_top = [], [], []
    for x0, x1 in frames:
        cys, cxs = np.nonzero(cream[:, x0:x1 + 1])
        oys, oxs = np.nonzero(orange[:, x0:x1 + 1])
        cream_cx.append(cxs.mean() + x0 if len(cxs) else oxs.mean() + x0)
        body_cx.append((oxs.min() + oxs.max()) / 2 + x0)
        body_top.append(int(oys.min()))
    offset = float(np.mean([b - c for b, c in zip(body_cx, cream_cx)]))

    # Floating glyph leftovers (the heart's ink outline) sit far above the
    # body and would clip into view as stray arcs; heart mode redraws them.
    if glyph == "heart":
        for (x0, x1), top in zip(frames, body_top):
            mask[: max(top - 15, 0), x0:x1 + 1] = False

    # A pose taller than the canvas (jumping HAPPY cat) shrinks slightly
    # instead of clipping its ears; 3 output px of headroom covers the ink
    # outline that rides above the topmost orange pixel.
    base = scale_base if scale_base is not None else SCALE
    scale = base
    needed = (bottom_excl - min(body_top)) * base + 3
    if needed > BASELINE:
        scale = (BASELINE - 3) / (bottom_excl - min(body_top))
        print(f"  pose exceeds canvas at base scale; using {scale:.4f} (base {base:.4f})")

    sheet = np.zeros((FRAME, FRAME * len(frames), 4), dtype=np.uint8)
    for i, (x0, x1) in enumerate(frames):
        fmask = np.zeros_like(mask)
        fmask[:, x0:x1 + 1] = mask[:, x0:x1 + 1]
        anchor = cream_cx[i] + offset

        frame_bottom = frame_bottoms[i] + 1 if align == "per-frame" else bottom_excl
        for oy in range(FRAME):
            sy0, sy1 = (
                frame_bottom + (oy - BASELINE) / scale,
                frame_bottom + (oy + 1 - BASELINE) / scale,
            )
            iy0, iy1 = max(int(np.floor(sy0)), 0), min(int(np.ceil(sy1)), src.shape[0])
            if iy1 <= iy0:
                continue
            for ox in range(FRAME):
                sx0, sx1 = (
                    anchor + (ox - ANCHOR_X) / scale,
                    anchor + (ox + 1 - ANCHOR_X) / scale,
                )
                ix0, ix1 = max(int(np.floor(sx0)), 0), min(int(np.ceil(sx1)), src.shape[1])
                if ix1 <= ix0:
                    continue
                m = fmask[iy0:iy1, ix0:ix1]
                if m.size == 0 or m.mean() < ALPHA_THRESHOLD:
                    continue
                rgb = snap(src[iy0:iy1, ix0:ix1][m].mean(0).round().astype(int))
                sheet[oy, i * FRAME + ox] = (*rgb, 255)

    for i in range(len(frames)):
        cell = sheet[:, i * FRAME:(i + 1) * FRAME]
        keep, sizes = despeckle(cell[..., 3] > 0, min_blob)
        cell[~keep] = 0
        demoted = demote_stray_reds(cell)
        note = f", {demoted} stray red px demoted" if demoted else ""
        if glyph == "z":
            note += f", {redraw_glyphs(cell)} glyph(s) redrawn"
        elif glyph == "anger":
            stamped = stamp_anger_marks(
                cell, src, frames[i], body_top[i], cream_cx[i] + offset, bottom_excl, scale
            )
            note += ", anger mark stamped" if stamped else ", no anger mark found"
        elif glyph == "heart":
            note += ", heart stamped" if stamp_heart(cell, src, frames[i], body_top[i]) else ""
        print(f"  frame {i} blobs kept>={min_blob}: {sizes[:8]}{' ...' if len(sizes) > 8 else ''}{note}")

    out_path = OUT_DIR / f"{name}.png"
    img = Image.fromarray(sheet, "RGBA")
    img.save(out_path, optimize=True)
    print(f"saved {out_path} {img.size}")

    if preview:
        prev = img.resize((img.width * 6, img.height * 6), Image.NEAREST)
        prev.save(OUT_DIR / f"_preview_{name}.png")
        print(f"saved preview {OUT_DIR / f'_preview_{name}.png'}")


GRID_ROWS = ["AWAKE_IDLE", "SLEEPING", "HAPPY", "ANGRY", "WAKE_UP"]
CAT_HEIGHT = 44  # output px the reference (idle) cat stands tall


def _bands(orange: np.ndarray, merge_gap: int = 8, min_height: int = 20) -> list[tuple[int, int]]:
    """Row bands from the orange body profile, expanded to claim glyph space.

    Floating glyphs (sleep z's, hearts) rise arbitrarily close to the row
    above, so gap thresholds on the full mask can't separate rows. Bodies
    can: glyphs and text labels contain no orange. Each band then extends
    upward to just below the previous body (claiming its own glyphs) and
    slightly downward for the ink outline.
    """
    prof = orange.sum(1) > 2
    runs: list[list[int]] = []
    start = None
    for y, filled in enumerate(prof):
        if filled and start is None:
            start = y
        elif not filled and start is not None:
            runs.append([start, y - 1])
            start = None
    if start is not None:
        runs.append([start, orange.shape[0] - 1])
    merged: list[list[int]] = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    bodies = [(y0, y1) for y0, y1 in merged if y1 - y0 + 1 >= min_height]

    # The previous row's ink outline hangs ~6-9px below its orange body; start
    # each band just past it (but before this row's own floating glyphs).
    outline_pad = 10
    bands = []
    for i, (y0, y1) in enumerate(bodies):
        top = max(0, y0 - 60) if i == 0 else bodies[i - 1][1] + outline_pad
        bands.append((top, min(y1 + outline_pad - 1, orange.shape[0] - 1)))
    return bands


def build_grid(filename: str, min_blob: int, preview: bool) -> None:
    """Process a single image holding all five state rows (labels at left).

    Row order must match GRID_ROWS. One shared scale is derived from the
    first (idle) row so every state keeps consistent pixel density.
    """
    src, mask = load_masked(SOURCE_DIR / filename)
    sat = src.max(2) - src.min(2)
    orange = (sat > 100) & (src[..., 1] - src[..., 2] > 35) & mask
    bands = _bands(orange)
    if len(bands) != len(GRID_ROWS):
        raise SystemExit(f"expected {len(GRID_ROWS)} rows, found {len(bands)}: {bands}")

    ref = bands[0]
    ref_rows = np.nonzero(mask[ref[0]:ref[1] + 1].sum(1) > 2)[0]
    ref_h = int(ref_rows.max() - ref_rows.min() + 1)
    scale_base = CAT_HEIGHT / ref_h
    print(f"grid: {len(bands)} rows, idle row {ref_h}px tall -> scale {scale_base:.4f}")

    for (top, bottom), name in zip(bands, GRID_ROWS):
        align = "per-frame" if name == "WAKE_UP" else "median"
        process(
            name,
            src[top:bottom + 1],
            mask[top:bottom + 1],
            min_blob,
            preview,
            expected_frames=6,
            align=align,
            scale_base=scale_base,
            strip_label=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="sheet name, e.g. SLEEPING (reads _source/<NAME>.png)")
    parser.add_argument("--min-blob", type=int, default=3, help="drop detached specks below this size")
    parser.add_argument("--preview", action="store_true", help="also write a 6x nearest-neighbor preview")
    parser.add_argument(
        "--glyph",
        choices=["none", "z", "anger", "heart"],
        default="none",
        help="glyph handling: 'z' redraws sleep z's; 'anger'/'heart' exclude the red bloom and stamp crisp marks",
    )
    parser.add_argument(
        "--frames", type=int, default=6, help="expected frame count (0 = trust auto-detection)"
    )
    parser.add_argument(
        "--align",
        choices=["median", "per-frame"],
        default="median",
        help="baseline: 'median' keeps airborne poses airborne; 'per-frame' grounds every frame",
    )
    parser.add_argument(
        "--grid",
        action="store_true",
        help="name is a full filename of one image holding all five labeled state rows",
    )
    args = parser.parse_args()
    if args.grid:
        build_grid(args.name, args.min_blob, args.preview)
    else:
        build(args.name, args.min_blob, args.preview, args.glyph, args.frames, args.align)
