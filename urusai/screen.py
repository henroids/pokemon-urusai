"""Turn a screenshot into a 20x18 grid of 8x8 one-bit tiles."""
from . import pngdec

GB_W, GB_H = 160, 144
COLS, ROWS = GB_W // 8, GB_H // 8


def is_gba(img):
    """A Game Boy Advance frame (240x160 or a whole multiple): not ours to read yet."""
    k = img.width // 240
    return k >= 1 and (img.width, img.height) == (240 * k, 160 * k)


def to_gb_frame(img):
    """Return a 160x144 Image from whatever RetroArch / a phone sent."""
    if (img.width, img.height) == (GB_W, GB_H):
        return img
    # A bigger image: a Super Game Boy frame (game centred at 1x) or a phone/
    # handheld screenshot (centred at an integer scale, or stretched to fit,
    # e.g. 7.5x on a 1080p AYN Thor).
    # Try both and keep the one whose source pixels look like solid blocks.
    if img.width < GB_W or img.height < GB_H:
        raise ValueError("frame too small: %dx%d" % (img.width, img.height))
    cands = {min(img.width / GB_W, img.height / GB_H),
             float(min(img.width // GB_W, img.height // GB_H))}
    best = min(cands, key=lambda s: _block_error(img, s))
    return _sample(img, best)


def _origin(img, s):
    return (img.width - GB_W * s) / 2.0, (img.height - GB_H * s) / 2.0


def _sample(img, s, dx=0.5, dy=0.5):
    x0, y0 = _origin(img, s)
    rows = []
    for ty in range(GB_H):
        src = img.rows[min(img.height - 1, int(y0 + (ty + dy) * s))]
        out = bytearray(GB_W * 3)
        for tx in range(GB_W):
            i = min(img.width - 1, int(x0 + (tx + dx) * s)) * 3
            out[tx * 3:tx * 3 + 3] = src[i:i + 3]
        rows.append(bytes(out))
    return pngdec.Image(GB_W, GB_H, rows)


def _block_error(img, s):
    """How often samples near a source pixel's edges disagree with its centre."""
    if s < 2:
        return 0
    m = 1.3 / s  # just inside the left/top and right/bottom edges
    c = _sample(img, s)
    err = 0
    for dx, dy in ((m, m), (1 - m, 1 - m)):
        e = _sample(img, s, dx, dy)
        err += sum(a != b for ra, rb in zip(c.rows, e.rows) for a, b in zip(ra, rb))
    return err


def ink_mask(img):
    """Per-pixel 'is text ink' (the darkest shade) as a list of rows of 0/1."""
    lum = [[(r * 299 + g * 587 + b * 114) // 1000 for r, g, b in
            (row[i:i + 3] for i in range(0, len(row), 3))] for row in img.rows]
    lo = min(min(r) for r in lum)
    hi = max(max(r) for r in lum)
    if hi - lo < 32:
        return [[0] * img.width for _ in range(img.height)]
    thr = lo + (hi - lo) // 6  # only the darkest of the 4 shades counts as ink
    return [[1 if v <= thr else 0 for v in r] for r in lum]


def tiles(img, dx=0, dy=0):
    """Grid[row][col] -> 64-bit int (bit 63 = top-left pixel)."""
    m = ink_mask(img)
    grid = []
    for ty in range(ROWS):
        row = []
        for tx in range(COLS):
            v = 0
            for y in range(8):
                py = ty * 8 + y + dy
                line = m[py] if 0 <= py < img.height else None
                for x in range(8):
                    px = tx * 8 + x + dx
                    bit = line[px] if line is not None and 0 <= px < img.width else 0
                    v = (v << 1) | bit
            row.append(v)
        grid.append(row)
    return grid


def tile_hex(v):
    return "%016x" % v


def tile_art(v):
    return "\n".join("".join("#" if (v >> (63 - (y * 8 + x))) & 1 else "." for x in range(8))
                     for y in range(8))
