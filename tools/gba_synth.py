#!/usr/bin/env python3
"""Draw made-up GBA screens with the games' real fonts, to test urusai/gba.py
before real screenshots exist: tests/gba/*.png and the text each should read as.

  gba_synth.py DIR      # DIR holds the pret clones, as for build_gba_font.py

The layouts are guesses at what the games do (a window, shadowed text, a ▶
cursor), over a noisy "map" so the reader has something to ignore.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_gba_font as bf  # noqa: E402

OUT = os.path.join(bf.ROOT, "tests", "gba")
WHITE, DARK, SHADOW = (248, 248, 248), (96, 96, 96), (208, 208, 200)
TEAL, BLUE, RED = (40, 80, 104), (48, 80, 200), (224, 8, 8)


class Canvas:
    def __init__(self, src, seed):
        from PIL import Image
        self.src, self.Image = src, Image
        self.im = Image.new("RGB", (240, 160))
        rnd = random.Random(seed)
        tones = [(88, 160, 72), (112, 184, 88), (64, 128, 56), (200, 176, 120), (96, 96, 96), (248, 248, 248)]
        px = self.im.load()
        for y in range(160):
            for x in range(240):
                px[x, y] = tones[min(len(tones) - 1, int(rnd.random() ** 2 * len(tones)))] if rnd.random() < .3 else tones[(x // 16 + y // 16) % 3]
        self.px = px
        self.sheets = {}

    def window(self, x, y, w, h, fill=WHITE, edge=(72, 112, 160)):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px[xx, yy] = edge if min(xx - x, yy - y, x + w - 1 - xx, y + h - 1 - yy) < 3 else fill

    def text(self, font, x, y, s, fg=DARK, shadow=SHADOW, bg=WHITE, spacing=0):
        name, sheet, cw, ch, per_row, adv = next(f for f in bf.SHEETS if f[0] == font)
        if font not in self.sheets:
            im = self.Image.open(os.path.join(self.src, sheet))
            self.sheets[font] = (im.load(), im.size, bf.widths(os.path.join(self.src, adv[0]), adv[1]) if isinstance(adv, tuple) else None)
        px, size, table = self.sheets[font]
        for chx in s:
            gid = 0 if chx == " " else bf.CHARS.index(chx)
            advance = (table[gid] if table and table[gid] else (adv if not table else cw)) if gid else (table and 5 or 8)
            for yy in range(ch):
                for xx in range(min(cw, advance)):
                    v = px[gid % per_row * cw + xx, gid // per_row * ch + yy] if gid else 3
                    self.px[x + xx, y + yy] = {1: fg, 2: shadow}.get(v, bg)
            x += advance + spacing

    def arrow(self, x, y, bg=WHITE):
        im = self.Image.open(os.path.join(self.src, bf.ARROWS[0][0]))
        px = im.load()
        for yy in range(16):
            for xx in range(8):   # palette 2 is the text colour (the outline), 4 the red filling
                self.px[x + xx, y + yy] = {2: DARK, 4: RED}.get(px[xx, yy], bg)


def scenes(src):
    c = Canvas(src, 1)   # Emerald-style message, two lines, waiting for A
    c.window(0, 112, 240, 48)
    c.text("em_normal", 12, 118, "オダマキ『おーい！ まって くれー！")
    c.text("em_normal", 12, 134, "そこは あぶないぞ！")
    c.arrow(160, 134)
    yield "em_message", c, "オダマキ『おーい！ まって くれー！ そこは あぶないぞ！"

    c = Canvas(src, 2)   # a start menu on the right
    c.window(168, 0, 72, 128)
    for i, s in enumerate(["ずかん", "ポケモン", "バッグ", "ヘンリー", "レポート", "せってい", "とじる"]):
        c.text("em_normal", 184, 8 + 16 * i, s)
    c.text("em_normal", 176, 8 + 16 * 2, "▶")
    yield "em_start_menu", c, "バッグ"

    c = Canvas(src, 3)   # a question with はい/いいえ
    c.window(0, 112, 240, 48)
    c.text("em_normal", 12, 118, "ここまでの かつやくを")
    c.text("em_normal", 12, 134, "レポートに かきこみますか？")
    c.window(176, 64, 64, 48)
    c.text("em_normal", 192, 72, "はい")
    c.text("em_normal", 192, 88, "いいえ")
    c.text("em_normal", 184, 88, "▶")
    yield "em_yes_no", c, "ここまでの かつやくを レポートに かきこみますか？ いいえ"

    c = Canvas(src, 4)   # a battle: white-on-dark message, 2x2 menu
    c.window(0, 112, 240, 48, fill=TEAL)
    c.text("em_normal", 12, 118, "ミズゴロウは", fg=WHITE, shadow=(104, 88, 112), bg=TEAL)
    c.text("em_normal", 12, 134, "どうする？", fg=WHITE, shadow=(104, 88, 112), bg=TEAL)
    c.window(120, 112, 120, 48)
    for (x, y), s in zip(((136, 118), (192, 118), (136, 134), (192, 134)), ["たたかう", "バッグ", "ポケモン", "にげる"]):
        c.text("em_normal", x, y, s)
    c.text("em_normal", 128, 118, "▶")
    c.window(8, 16, 104, 32)
    c.text("em_small", 16, 18, "ポチエナ")
    c.text("em_small", 80, 18, "12／20")
    yield "em_battle", c, "ミズゴロウは どうする？ たたかう"

    c = Canvas(src, 5)   # FireRed/LeafGreen: blue text for a man, in its own font
    c.window(0, 112, 240, 48)
    c.text("fr_male", 10, 116, "オーキド『おお ヘンリー！", fg=BLUE)
    c.text("fr_male", 10, 132, "げんきに しとったか？", fg=BLUE)
    yield "fr_message", c, "オーキド『おお ヘンリー！ げんきに しとったか？"

    c = Canvas(src, 6)   # FireRed/LeafGreen menu font, numbers
    c.window(88, 0, 152, 96)
    for i, s in enumerate(["キズぐすり ×3", "モンスターボール ×10", "やめる"]):
        c.text("fr_normal", 104, 8 + 16 * i, s)
    c.text("fr_normal", 94, 8, "▶")
    yield "fr_bag", c, "キズぐすり ×3"

    c = Canvas(src, 7)   # nothing to read
    yield "map_only", c, ""


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    expect = {}
    for name, canvas, text in scenes(sys.argv[1]):
        canvas.im.save(os.path.join(OUT, name + ".png"), optimize=True)
        expect[name] = text
    with open(os.path.join(OUT, "expect.json"), "w", encoding="utf-8") as f:
        json.dump(expect, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("%d screens in %s" % (len(expect), os.path.relpath(OUT, bf.ROOT)))
