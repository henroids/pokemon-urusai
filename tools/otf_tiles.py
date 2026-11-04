#!/usr/bin/env python3
"""Turn a FontStruct pixel font of the game's lettering into 8x8 tiles.

  otf_tiles.py font/sources/pokemon-silver-jp-gbc/pokemon-silver-jp-gbc.otf \
      > font/sources/pokemon-silver-jp-gbc.json

FontStruct fonts are drawn on a pixel grid (250 units = 1 pixel, 8 pixels
a letter), so each glyph rasterises exactly. A voiced kana is split like the
game draws it: the letter in its own tile, ゛/゜ in the tile above (which
gives the same tiles as the plain letter and the bare mark, so only those
are written). Output: {"label": "tile hex", …} with the reader's labels.
Needs fontTools (pip install fonttools); only run when the font changes.
"""
import json
import sys
import unicodedata

UNIT = 250            # font units per pixel
# Symbols -> the reader's labels. Anything not listed and not kana/digits is skipped.
SYMBOLS = {
    "▶": "<cursor>", "▷": "<cursor_off>", "▼": "<more>",
    "═": "<box>", "║": "<box>", "╔": "<box>", "╗": "<box>", "╚": "<box>", "╝": "<box>",
    "♂": "♂", "♀": "♀", "¥": "円", "円": "円", "…": "…", "・": "・", "ー": "ー",
    "。": "。", "「": "「", "」": "」", "『": "『", "』": "』", "！": "！", "？": "？",
    "!": "！", "?": "？", ".": ".", "/": "／", ":": ":", "-": "ー",
}


def pixels(glyph_set, name):
    from fontTools.pens.recordingPen import RecordingPen
    pen = RecordingPen()
    glyph_set[name].draw(pen)
    polys, cur = [], []
    for op, args in pen.value:
        if op == "moveTo":
            cur = [args[0]]
        elif op == "lineTo":
            cur.append(args[0])
        elif op in ("closePath", "endPath"):
            if cur:
                polys.append(cur)
            cur = []
        else:
            raise ValueError("not a pixel font: %s" % op)

    def inside(x, y):  # non-zero winding at a pixel centre
        w = 0
        for poly in polys:
            for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
                if (y1 <= y < y2 or y2 <= y < y1) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    w += 1 if y1 <= y < y2 else -1
        return w != 0

    return {(px, py) for px in range(-1, 9) for py in range(-2, 12)
            if inside((px + .5) * UNIT, (py + .5) * UNIT)}


def tile(pix, dy=0):
    """Pixels with y in dy..dy+7 -> 64-bit int (bit 63 = top-left), like screen.tiles()."""
    v = 0
    for row in range(8):
        for x in range(8):
            v = (v << 1) | ((x, dy + 7 - row) in pix)
    return v


def label(ch):
    if ch in SYMBOLS:
        return SYMBOLS[ch]
    if ch.isdigit() or ("ぁ" <= ch <= "ヺ" and len(unicodedata.normalize("NFD", ch)) == 1):
        return ch
    return None


def tiles(path):
    from fontTools.ttLib import TTFont
    font = TTFont(path)
    gs = font.getGlyphSet()
    out = {}
    for code, name in sorted(font.getBestCmap().items()):
        ch = chr(code)
        if ch in "゛゜":
            out.setdefault(ch, []).append("%016x" % tile(pixels(gs, name), dy=8))
            continue
        lab = label(ch)
        if lab:
            t = "%016x" % tile(pixels(gs, name))
            if t != "%016x" % 0 and t not in out.setdefault(lab, []):
                out[lab].append(t)
    return out


if __name__ == "__main__":
    json.dump(tiles(sys.argv[1]), sys.stdout, ensure_ascii=False, indent=1, sort_keys=True)
    sys.stdout.write("\n")
