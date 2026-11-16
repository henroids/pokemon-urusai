"""Reading tests: synthetic screens for the rules, real frames for regression."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import ROOT, Canvas, dialogue_canvas, font_from, make_font  # noqa: E402
from urusai import normalize, pngdec, reader  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_font  # noqa: E402

FRAMES = os.path.join(ROOT, "tests", "frames")
DIALOGUE = "やせいの ピカチュウが とびだしてきた！"


class SyntheticScreens(unittest.TestCase):
    def setUp(self):
        self.g = make_font()
        self.font = font_from(self.g)

    def test_dialogue_with_dakuten_above(self):
        self.assertEqual(reader.read_image(self.font, dialogue_canvas(self.g).image()), DIALOGUE)

    def test_integer_scaled_screenshot(self):
        img = dialogue_canvas(self.g).image(scale=7, pad=(400, 36))
        self.assertEqual(reader.read_image(self.font, img), DIALOGUE)

    def test_start_menu_reads_selected_item(self):
        cv = Canvas(self.g)
        cv.box(0, 10, 15, 19)
        for i, item in enumerate(["ずかん", "ポケモン", "どうぐ", "レッド", "レポート", "せってい", "とじる"]):
            cv.text(2 + i * 2, 12, item)
        cv.put(6, 11, "<cursor>")
        self.assertEqual(reader.read_image(self.font, cv.image()), "どうぐ")

    def test_battle_menu_cuts_at_aligned_column(self):
        cv = Canvas(self.g)
        cv.box(12, 0, 17, 19)
        cv.box(12, 8, 17, 19)
        cv.text(14, 10, "たたかう")
        cv.text(14, 15, "ポケモン")
        cv.text(16, 10, "どうぐ")
        cv.text(16, 15, "にげる")
        cv.put(16, 14, "<cursor>")
        self.assertEqual(reader.read_image(self.font, cv.image()), "にげる")

    def test_learn_tool_round_trip(self):
        img = dialogue_canvas(self.g).image(scale=7, pad=(400, 36))
        d = tempfile.mkdtemp()
        shot, fontp = os.path.join(d, "s.png"), os.path.join(d, "f.json")
        with open(shot, "wb") as f:
            f.write(pngdec.encode(img))
        tool = os.path.join(ROOT, "tools", "learn.py")
        subprocess.run([sys.executable, tool, "--font", fontp, "label", shot,
                        "14:1", "やせいの ピカチュウが", "16:1", "とびだしてきた！"], check=True, capture_output=True)
        out = subprocess.run([sys.executable, tool, "--font", fontp, "read", shot],
                             check=True, capture_output=True, text=True).stdout
        self.assertIn(DIALOGUE, out)


class RealFrames(unittest.TestCase):
    """The 36 reference frames from 青 must keep reading exactly as recorded."""

    @classmethod
    def setUpClass(cls):
        cls.font = build_font.build(FRAMES, log=lambda *a: None)

    def test_committed_font_matches_labels(self):
        from urusai.font import Font
        committed = Font.load(os.path.join(ROOT, "font", "gb_jp.json"))
        self.assertEqual(committed.table, self.font.table, "run tools/build_font.py")

    def test_every_frame_reads_as_expected(self):
        got = build_font.readings(self.font, FRAMES)
        for name, want in build_font.EXPECT.items():
            with self.subTest(frame=name):
                self.assertEqual(got[name], want)

    def test_letters_from_the_pixel_fonts(self):
        """Letters no screenshot had yet (♂/♀, small ァ, 円, Gen 2's ユ) read back."""
        import json
        from synth import Canvas
        from urusai.font import Font
        font = Font.load(os.path.join(ROOT, "font", "gb_jp.json"))
        g = {}
        for t, lab in sorted(font.table.items()):
            g.setdefault(lab, t)
        with open(os.path.join(ROOT, "font", "sources", "pokemon-silver-jp-gbc.json")) as f:
            g["ユ"] = int(json.load(f)["ユ"][-1], 16)       # the Gen 2 shape
        cv = Canvas(g)
        cv.box(12, 0, 17, 19)
        cv.text(14, 1, "ニドラン♀と ファイヤー")
        cv.text(16, 1, "ユウキに 300円！")
        self.assertEqual(reader.analyze_image(font, cv.image()).flat(),
                         "ニドラン♀と ファイヤー ユウキに 300円！")

    def test_png_decoder_handles_every_filter_and_format(self):
        """RetroArch picks any of PNG's five row filters; phones send RGBA or palettes."""
        import struct
        import zlib
        from urusai import pngdec
        import random
        rnd = random.Random(7)
        w, h = 37, 9
        rows = [bytes(rnd.randrange(256) for _ in range(w * 3)) for _ in range(h)]

        def filtered(rows, bpp, kinds):
            out, prev = bytearray(), bytes(len(rows[0]))
            for r, kind in zip(rows, kinds):
                line = bytearray()
                for i, v in enumerate(r):
                    a = r[i - bpp] if i >= bpp else 0
                    b, c = prev[i], prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    paeth = a if pa <= pb and pa <= pc else b if pb <= pc else c
                    line.append((v - (0, a, b, (a + b) >> 1, paeth)[kind]) & 255)
                out += bytes([kind]) + line
                prev = r
            return bytes(out)

        def png(raw, ctype, extra=b""):
            def chunk(kind, body):
                return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
                    + extra + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

        for kinds in ([k] * h for k in range(5)):
            self.assertEqual(pngdec.decode(png(filtered(rows, 3, kinds), 2)).rows, rows, kinds[0])
        mixed = [rnd.randrange(5) for _ in range(h)]
        self.assertEqual(pngdec.decode(png(filtered(rows, 3, mixed), 2)).rows, rows)
        rgba = [b"".join(r[i:i + 3] + b"\x80" for i in range(0, w * 3, 3)) for r in rows]
        self.assertEqual(pngdec.decode(png(filtered(rgba, 4, mixed), 6)).rows, rows)
        idx = [bytes(rnd.randrange(4) for _ in range(w)) for _ in range(h)]
        pal = bytes(range(10, 22))
        plte = struct.pack(">I", 12) + b"PLTE" + pal + struct.pack(">I", zlib.crc32(b"PLTE" + pal))
        self.assertEqual(pngdec.decode(png(filtered(idx, 1, mixed), 3, plte)).rows,
                         [b"".join(pal[v * 3:v * 3 + 3] for v in r) for r in idx])
        self.assertEqual(pngdec.decode(pngdec.encode(pngdec.Image(w, h, rows), level=1)).rows, rows)

    def test_gba_screens(self):
        """Made-up GBA screens in the games' real fonts (tools/gba_synth.py)."""
        import json
        from urusai import gba, pngdec
        font = gba.GbaFont.load(os.path.join(ROOT, "font", "gba_jp.json"))
        with open(os.path.join(ROOT, "tests", "gba", "expect.json"), encoding="utf-8") as f:
            expect = json.load(f)
        self.assertGreaterEqual(len(expect), 7)
        for name, text in expect.items():
            with open(os.path.join(ROOT, "tests", "gba", name + ".png"), "rb") as f:
                img = pngdec.decode(f.read())
            self.assertTrue(gba.is_gba(img))
            self.assertEqual(gba.analyze(font, img).flat(), text, name)
        r = gba.analyze(font, img.__class__(480, 320, [bytes(480 * 3)] * 320))   # 2x, blank
        self.assertEqual(r.kind, "none")

    def test_gba_menu_is_split_from_the_message(self):
        from urusai import gba, pngdec
        font = gba.GbaFont.load(os.path.join(ROOT, "font", "gba_jp.json"))
        with open(os.path.join(ROOT, "tests", "gba", "em_battle.png"), "rb") as f:
            r = gba.analyze(font, pngdec.decode(f.read()))
        self.assertEqual((r.options, r.selected), (["たたかう", "バッグ", "ポケモン", "にげる"], 0))
        self.assertEqual(r.dialogue, ["ミズゴロウは", "どうする？"])     # white on dark, another window
        with open(os.path.join(ROOT, "tests", "gba", "fr_bag.png"), "rb") as f:
            r = gba.analyze(font, pngdec.decode(f.read()))
        self.assertEqual(r.options, ["キズぐすり ×3", "モンスターボール ×10", "やめる"])

    def test_phone_screenshot_scale_is_detected(self):
        # 7.5x stretched captures were reduced to these 160x144 frames
        with open(os.path.join(FRAMES, "36.png"), "rb") as f:
            img = pngdec.decode(f.read())
        self.assertEqual((img.width, img.height), (160, 144))


class Speech(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize.for_speech("ニドラン♂‥‥ まって！"), "ニドランオス、まって！")
        self.assertEqual(normalize.for_speech("オーキド『まー！"), "オーキド、まー！")
        self.assertEqual(normalize.for_speech("ナンバー.007 0.5メートル"), "7番0.5メートル")
        self.assertEqual(normalize.for_speech("では はじめに きみの なまえを"), "でははじめにきみのなまえを")

    def test_shared_tiles_follow_neighbours(self):
        self.assertEqual(reader.fix_shared("へンりー"), "ヘンリー")
        self.assertEqual(reader.fix_shared("ぺッと"), "ぺっと")
        self.assertEqual(reader.fix_shared("あッ"), "あっ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
