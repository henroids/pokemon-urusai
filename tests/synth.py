"""Synthetic Gen 1-style screens for tests (random glyphs, real layout rules).

Random 8x8 glyphs stand in for the real font, laid out the way Gen 1 does it:
text on rows 14/16 with ゛/゜ in the row above, box borders, a ▶ cursor.
"""
import os
import random
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from urusai import pngdec  # noqa: E402
from urusai.font import Font  # noqa: E402

KANA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんっゃゅょ" \
       "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンッャュョー！？"
SHADES = [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)]  # DMG green palette


def make_font(seed=1):
    rnd = random.Random(seed)
    glyphs = {}
    used = set()
    for lab in list(KANA) + ["゛", "゜", "<box>", "<cursor>", "<more>"]:
        while True:
            v = rnd.getrandbits(64) | 1
            if v not in used and all(bin(v ^ u).count("1") > 12 for u in used):
                break
        used.add(v)
        glyphs[lab] = v
    return glyphs


class Canvas:
    def __init__(self, glyphs):
        self.g = glyphs
        self.cells = [[0] * 20 for _ in range(18)]

    def put(self, r, c, lab):
        self.cells[r][c] = self.g[lab]

    def text(self, r, c, s):
        for ch in s:
            if ch != " ":
                d = unicodedata.normalize("NFD", ch)
                self.put(r, c, d[0])
                if len(d) > 1:
                    self.put(r - 1, c, "゛" if d[1] == "゙" else "゜")
            c += 1

    def box(self, r0, c0, r1, c1):
        for c in range(c0, c1 + 1):
            self.put(r0, c, "<box>"); self.put(r1, c, "<box>")
        for r in range(r0, r1 + 1):
            self.put(r, c0, "<box>"); self.put(r, c1, "<box>")

    def image(self, scale=1, pad=(0, 0), noise=0):
        w, h = 160 * scale + 2 * pad[0], 144 * scale + 2 * pad[1]
        rnd = random.Random(7)
        rows = []
        for y in range(h):
            row = bytearray()
            for x in range(w):
                gx, gy = (x - pad[0]) // scale, (y - pad[1]) // scale
                if not (0 <= gx < 160 and 0 <= gy < 144):
                    row += bytes((0, 0, 0)); continue
                v = self.cells[gy // 8][gx // 8]
                bit = (v >> (63 - ((gy % 8) * 8 + gx % 8))) & 1
                shade = SHADES[3] if bit else SHADES[0]
                if not bit and gy < 96 and (gx * 7 + gy * 3) % 11 == 0:
                    shade = SHADES[1]  # overworld clutter above the box
                row += bytes(shade)
            rows.append(bytes(row))
        return pngdec.Image(w, h, rows)


def dialogue_canvas(g):
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.text(14, 1, "やせいの ピカチュウが")
    cv.text(16, 1, "とびだしてきた！")
    cv.put(16, 18, "<more>")
    return cv


def font_from(g):
    return Font({v: k for k, v in g.items()})
