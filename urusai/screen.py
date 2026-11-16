"""Turn a screenshot into a 20x18 grid of 8x8 one-bit tiles."""
from . import pngdec

GB_W, GB_H = 160, 144
COLS, ROWS = GB_W // 8, GB_H // 8


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


# Luminance = 0.299 R + 0.587 G + 0.114 B, one lookup table per channel, so a
# whole row is weighed with three C-speed translate() calls and two additions.
_LUM = [bytes(v * w // 1000 for v in range(256)) for w in (299, 587, 114)]


def ink_rows(img):
    """Each row as an int with one bit per pixel (leftmost pixel = highest bit):
    1 where the pixel is text ink, the darkest of the screen's four shades."""
    lum = []
    for row in img.rows:
        r, g, b = (int.from_bytes(row[c::3].translate(_LUM[c]), "big") for c in range(3))
        lum.append((r + g + b).to_bytes(img.width, "big"))
    lo = min(map(min, lum))
    hi = max(map(max, lum))
    if hi - lo < 32:
        return [0] * img.height
    thr = lo + (hi - lo) // 6
    as_digits = bytes(49 if v <= thr else 48 for v in range(256))   # "1" / "0"
    return [int(line.translate(as_digits), 2) for line in lum]


def tiles(img):
    """Grid[row][col] -> 64-bit int (bit 63 = top-left pixel)."""
    rows = ink_rows(img)
    grid = []
    for ty in range(ROWS):
        band = rows[ty * 8:ty * 8 + 8]
        line = []
        for shift in range(img.width - 8, -8, -8):
            v = 0
            for bits in band:
                v = (v << 8) | ((bits >> shift) & 0xFF)
            line.append(v)
        grid.append(line)
    return grid


def tile_hex(v):
    return "%016x" % v


def tile_art(v):
    return "\n".join("".join("#" if (v >> (63 - (y * 8 + x))) & 1 else "." for x in range(8))
                     for y in range(8))
