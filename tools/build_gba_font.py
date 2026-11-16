#!/usr/bin/env python3
"""Build font/gba_jp.json: how to recognise the Japanese letters of the GBA
Pokémon games (ルビー・サファイア・エメラルド・ファイアレッド・リーフグリーン).

  build_gba_font.py DIR      # DIR holds clones of pret/pokeemerald, pokefirered, pokeruby

The letter shapes are read from the font sheets of the decompilation
projects (graphics/fonts/*.png), which are only needed to run this tool:
nothing from them is stored. For each letter the output keeps
  * a fingerprint (hash) of its ink, which is all urusai/gba.py needs to
    recognise it on screen, and
  * where the ink sits in its cell and how far the next letter is (to tell
    lines and spaces apart).
Needs Pillow; only run when a sheet is added.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from urusai import gba  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "font", "gba_jp.json")

# Glyph ids in the games' Japanese character table, 16 to a row.
CHARS = ("　あいうえおかきくけこさしすせそ" "たちつてとなにぬねのはひふへほま" "みむめもやゆよらりるれろわをんぁ"
         "ぃぅぇぉゃゅょがぎぐげござじずぜ" "ぞだぢづでどばびぶべぼぱぴぷぺぽ" "っアイウエオカキクケコサシスセソ"
         "タチツテトナニヌネノハヒフヘホマ" "ミムメモヤユヨラリルレロワヲンァ" "ィゥェォャュョガギグゲゴザジズゼ"
         "ゾダヂヅデドバビブベボパピプペポ" "ッ0123456789！？。ー・" "…『』「」♂♀円．×／ABCDE"
         "FGHIJKLMNOPQRSTU" "VWXYZabcdefghijk" "lmnopqrstuvwxyz▶" "：")
SKIP = set("　")

# (name, sheet, cell width, cell height, cells per row, (C file, width table) or advance)
E, F, R = "pokeemerald/", "pokefirered/", "pokeruby/"
SHEETS = [
    ("em_normal", E + "graphics/fonts/japanese_normal.png", 8, 16, 16, 8),
    ("em_small", E + "graphics/fonts/japanese_small.png", 8, 16, 16, 8),
    ("em_bold", E + "graphics/fonts/japanese_bold.png", 8, 16, 16, 8),
    ("em_short", E + "graphics/fonts/japanese_short.png", 16, 16, 16, (E + "src/fonts.c", "gFontShortJapaneseGlyphWidths")),
    ("fr_normal", F + "graphics/fonts/japanese_normal.png", 16, 16, 16, (F + "src/text.c", "sFontNormalJapaneseGlyphWidths")),
    ("fr_male", F + "graphics/fonts/japanese_male.png", 16, 16, 16, (F + "src/text.c", "sFontMaleJapaneseGlyphWidths")),
    ("fr_female", F + "graphics/fonts/japanese_female.png", 16, 16, 16, (F + "src/text.c", "sFontFemaleJapaneseGlyphWidths")),
    ("fr_small", F + "graphics/fonts/japanese_small.png", 8, 16, 32, 8),
    ("fr_tall", F + "graphics/fonts/japanese_tall.png", 8, 16, 32, 8),
    ("fr_bold", F + "graphics/fonts/japanese_bold.png", 8, 16, 32, 8),
    ("rs_normal", R + "graphics/fonts/font3_jpn.png", 8, 16, 16, 8),
]   # not included: Ruby's font0/font1/font4 (other layouts; font3 is its text font)
# The "press A" arrow is its own little picture, not a letter: (sheet, cell w, cell h, frames across, down)
ARROWS = [(E + "graphics/fonts/down_arrow.png", 8, 16, 1, 3), (F + "graphics/fonts/down_arrows.png", 16, 16, 8, 1),
          (R + "graphics/fonts/down_arrow.png", 8, 16, 1, 4)]
INK = 1   # palette index of the letter itself in the font sheets (2 is its shadow)


def widths(path, name):
    with open(path, encoding="utf-8") as f:
        m = re.search(re.escape(name) + r"\[\]\s*=\s*\{([^}]*)\}", f.read())
    return [int(x) for x in re.findall(r"\d+", m.group(1))]


def cell_ink(px, size, x0, y0, cw, ch, ink):
    """Rows of a cell as ints (leftmost pixel = highest bit); [] if outside the sheet."""
    if x0 + cw > size[0] or y0 + ch > size[1]:
        return []
    return [sum((px[x0 + x, y0 + y] in ink) << (cw - 1 - x) for x in range(cw)) for y in range(ch)]


def entry(rows, cw):
    """(fingerprint key, top-row index key, bearing, top) of a cell's ink, or None if blank."""
    used = [y for y, r in enumerate(rows) if r]
    if not used:
        return None
    top, bottom = used[0], used[-1]
    every = 0
    for r in rows:
        every |= r
    left = cw - every.bit_length()
    right = cw - 1 - ((every & -every).bit_length() - 1)
    w = right - left + 1
    ink = [(r >> (cw - 1 - right)) & ((1 << w) - 1) for r in rows[top:bottom + 1]]
    return gba.fingerprint(w, ink), gba.anchor_key(w, ink), left, top


def build(src, log=print):
    from PIL import Image
    glyphs, anchors, fonts, clashes = {}, {}, [], {}

    def add(key, akey, label, font, left, top, advance):
        hits = glyphs.setdefault(key, [])
        for h in hits:
            if h[0] != label:
                clashes.setdefault(frozenset((h[0], label)), set()).add(fonts[font])
        if [label, font, left, top, advance] not in hits:
            hits.append([label, font, left, top, advance])
        a = anchors.setdefault(akey[0], [])
        if list(akey[1]) not in a:
            a.append(list(akey[1]))

    for name, sheet, cw, ch, per_row, adv in SHEETS:
        path = os.path.join(src, sheet)
        if not os.path.exists(path):
            log("  (no %s: skipped)" % sheet)
            continue
        im = Image.open(path)
        px = im.load()
        table = widths(os.path.join(src, adv[0]), adv[1]) if isinstance(adv, tuple) else None
        fonts.append(name)
        n = 0
        for gid, label in enumerate(CHARS):
            if label in SKIP:
                continue
            rows = cell_ink(px, im.size, gid % per_row * cw, gid // per_row * ch, cw, ch, {INK})
            e = entry(rows, cw) if rows else None
            if e:
                advance = table[gid] if table and gid < len(table) and table[gid] else (adv if not table else cw)
                add(e[0], e[1], label, len(fonts) - 1, e[2], e[3], advance)
                n += 1
        log("  %-10s %3d letters" % (name, n))
    fonts.append("arrow")
    for sheet, cw, ch, across, down in ARROWS:
        path = os.path.join(src, sheet)
        if not os.path.exists(path):
            continue
        im = Image.open(path)
        px = im.load()
        for fx in range(across):
            for fy in range(down):
                # outline and fill are drawn in different colours: either may be the text colour
                for tone in {px[fx * cw + x, fy * ch + y] for x in range(cw) for y in range(ch)} - {0}:
                    rows = cell_ink(px, im.size, fx * cw, fy * ch, cw, ch, {tone})
                    if sum(bin(r).count("1") for r in rows) > 6:
                        e = entry(rows, cw)
                        add(e[0], e[1], gba.MORE, len(fonts) - 1, e[2], e[3], cw)
    for pair, where in sorted(clashes.items(), key=lambda kv: sorted(kv[0])):
        log("  same shape: %s (%s)" % (" ".join(sorted(pair)), ", ".join(sorted(where))))
    return {"fonts": fonts, "glyphs": glyphs, "anchors": anchors}


if __name__ == "__main__":
    data = build(sys.argv[1])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")
    print("%s: %d shapes, %d kB" % (os.path.relpath(OUT, ROOT), len(data["glyphs"]), os.path.getsize(OUT) // 1024))
