"""On-screen messages such as 「よみあげ オン」, drawn with the game's own font.

RetroArch shows an image from the AI Service reply over the game until the
next reply comes in, so a message is a transparent PNG with a white box in
the middle, the way the game draws its own text boxes. Stdlib only.
"""
import unicodedata

from . import pngdec

GB_W, GB_H = 160, 144
SCALE = 4                       # sharp at full screen even if RetroArch filters it
INK, PAPER = (24, 24, 24, 255), (248, 248, 248, 255)
CLEAR = (0, 0, 0, 0)
MARKS = {"゙": "゛", "゚": "゜"}   # combining (han)dakuten -> the game's own tiles


def glyphs(font):
    """label -> 8x8 tile (the first one the font has for that label)."""
    out = {}
    for tile, label in sorted(font.table.items()):
        out.setdefault(label, tile)
    return out


def layout(text):
    """Text -> [(letter, mark)], e.g. げ -> ('け', '゛')."""
    cells = []
    for ch in text:
        base, *rest = unicodedata.normalize("NFD", ch)
        cells.append((base, MARKS.get(rest[0]) if rest else None))
    return cells


def render(font, text):
    """A GB-sized RGBA canvas (rows of tuples) with the message box centred."""
    g = glyphs(font)
    cells = layout(text)
    # in tiles: border, mark row, letter row, border; one tile of border left/right
    w, h = (len(cells) + 2) * 8, 4 * 8
    x0, y0 = (GB_W - w) // 2, (GB_H - h) // 2
    px = [[CLEAR] * GB_W for _ in range(GB_H)]
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            edge = min(x - x0, y - y0, x0 + w - 1 - x, y0 + h - 1 - y)
            px[y][x] = INK if 1 <= edge <= 2 else PAPER if edge > 2 else CLEAR

    def draw(tile, tx, ty):
        for y in range(8):
            for x in range(8):
                if (tile >> (63 - (y * 8 + x))) & 1:
                    px[ty + y][tx + x] = INK

    for i, (letter, mark) in enumerate(cells):
        tx = x0 + (i + 1) * 8
        if letter in g:
            draw(g[letter], tx, y0 + 16)
        if mark in g:
            draw(g[mark], tx, y0 + 8)
    return px


def png(font, text, scale=SCALE):
    """The message as RGBA PNG bytes."""
    rows = []
    for row in render(font, text):
        line = b"".join(bytes(p) * scale for p in row)
        rows += [line] * scale
    return pngdec.encode_rows(GB_W * scale, GB_H * scale, rows, 6)
