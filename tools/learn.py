#!/usr/bin/env python3
"""Build the Gen 1 tile font from screenshots, and test reading.

  learn.py grid  SHOT.png                    show the 20x18 tile grid (known labels / ?ids)
  learn.py label SHOT.png ROW:COL TEXT ...   label tiles left-to-right starting at ROW:COL
                                             (voiced kana like が also label ゛ in the row above;
                                              a space skips one tile)
  learn.py tile  SHOT.png ROW:COL LABEL      label one tile, e.g. "<box>" "<cursor>" "<more>"
  learn.py read  SHOT.png [--wav out.wav]    print what the server would say

SHOT.png may be a native 160x144 frame (e.g. from the server's capture folder)
or an integer-scaled phone screenshot; it is downscaled automatically.
"""
import argparse
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from urusai import normalize, pngdec, reader, screen  # noqa: E402
from urusai.font import Font  # noqa: E402

DEFAULT_FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "font", "gen1_jp.json")
SPLIT = {"゙": "゛", "゚": "゜"}


def load_grid(path):
    with open(path, "rb") as f:
        img = screen.to_gb_frame(pngdec.decode(f.read()))
    return screen.tiles(img)


def rc(s):
    r, c = s.split(":")
    return int(r), int(c)


def cmd_grid(a, font):
    grid = load_grid(a.shot)
    unknown = {}
    print("    " + "".join("%-3d" % c for c in range(screen.COLS)))
    for r, row in enumerate(grid):
        cells = []
        for t in row:
            lab = font.match(t)
            if lab is None:
                uid = unknown.setdefault(t, len(unknown))
                cells.append("?%-2d" % uid)
            elif lab == " ":
                cells.append(" . ")
            elif lab.startswith("<"):
                cells.append(lab[1:3].upper() + " ")
            else:
                cells.append(lab + " ")
        print("%2d  %s" % (r, "".join(cells)))
    if a.show:
        for t, uid in unknown.items():
            print("\n?%d  %s\n%s" % (uid, screen.tile_hex(t), screen.tile_art(t)))
    print("\n%d known tiles in font, %d unknown distinct tiles on this screen" % (len(font.table), len(unknown)))


def cmd_label(a, font):
    grid = load_grid(a.shot)
    pairs = a.items
    if len(pairs) % 2:
        sys.exit("give ROW:COL TEXT pairs")
    n = 0
    for i in range(0, len(pairs), 2):
        r, c = rc(pairs[i])
        for ch in pairs[i + 1]:
            if ch == " ":
                c += 1
                continue
            d = unicodedata.normalize("NFD", ch)
            base, mark = d[0], SPLIT.get(d[1]) if len(d) > 1 else None
            t = grid[r][c]
            if t == 0:
                sys.exit("tile %d:%d is blank but text says %r — check the position" % (r, c, ch))
            font.add(t, base)
            n += 1
            if mark:
                if r == 0 or grid[r - 1][c] == 0:
                    sys.exit("no %s mark above %d:%d" % (mark, r, c))
                font.add(grid[r - 1][c], mark)
                n += 1
            c += 1
    print("labelled %d tiles" % n)
    if not a.dry:
        font.save(a.font)


def cmd_tile(a, font):
    grid = load_grid(a.shot)
    r, c = rc(a.pos)
    font.add(grid[r][c], a.label)
    print(screen.tile_art(grid[r][c]))
    if not a.dry:
        font.save(a.font)


def cmd_read(a, font):
    with open(a.shot, "rb") as f:
        img = pngdec.decode(f.read())
    text = reader.read_image(font, img)
    spoken = normalize.for_speech(text)
    print("read:  ", text)
    print("speak: ", spoken)
    if a.wav and spoken:
        from urusai.tts import Speaker
        with open(a.wav, "wb") as f:
            f.write(Speaker().wav(spoken))
        print("wrote", a.wav)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--font", default=DEFAULT_FONT)
    p.add_argument("--dry", action="store_true", help="don't save the font")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grid"); g.add_argument("shot"); g.add_argument("--show", action="store_true")
    l = sub.add_parser("label"); l.add_argument("shot"); l.add_argument("items", nargs="+")
    t = sub.add_parser("tile"); t.add_argument("shot"); t.add_argument("pos"); t.add_argument("label")
    r = sub.add_parser("read"); r.add_argument("shot"); r.add_argument("--wav")
    a = p.parse_args()
    font = Font.load(a.font)
    {"grid": cmd_grid, "label": cmd_label, "tile": cmd_tile, "read": cmd_read}[a.cmd](a, font)


if __name__ == "__main__":
    main()
