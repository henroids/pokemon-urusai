"""Turn a screenshot into a 20x18 grid of 8x8 one-bit tiles."""
from . import pngdec

GB_W, GB_H = 160, 144
COLS, ROWS = GB_W // 8, GB_H // 8


def to_gb_frame(img):
    """Return a 160x144 Image from whatever RetroArch / a phone sent."""
    if (img.width, img.height) == (GB_W, GB_H):
        return img
    if (img.width, img.height) == (256, 224):  # Super Game Boy border
        return pngdec.downscale(img, 1, 48, 40)
    # Integer-scaled capture (e.g. an AYN Thor screenshot with Integer Scale on):
    # assume the game is centred at the largest integer scale that fits.
    k = min(img.width // GB_W, img.height // GB_H)
    if k >= 1:
        x0 = (img.width - GB_W * k) // 2
        y0 = (img.height - GB_H * k) // 2
        return pngdec.downscale(img, k, x0, y0)
    raise ValueError("frame too small: %dx%d" % (img.width, img.height))


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
