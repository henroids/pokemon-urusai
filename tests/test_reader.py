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
        committed = Font.load(os.path.join(ROOT, "font", "gen1_jp.json"))
        self.assertEqual(committed.table, self.font.table, "run tools/build_font.py")

    def test_every_frame_reads_as_expected(self):
        got = build_font.readings(self.font, FRAMES)
        for name, want in build_font.EXPECT.items():
            with self.subTest(frame=name):
                self.assertEqual(got[name], want)

    def test_phone_screenshot_scale_is_detected(self):
        # 7.5x stretched captures were reduced to these 160x144 frames
        with open(os.path.join(FRAMES, "36.png"), "rb") as f:
            img = pngdec.decode(f.read())
        self.assertEqual((img.width, img.height), (160, 144))


class Speech(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize.for_speech("ニドラン♂‥‥ まって！"), "ニドランオス、　まって！")
        self.assertEqual(normalize.for_speech("オーキド『まー！"), "オーキド、まー！")
        self.assertEqual(normalize.for_speech("ナンバー.007 0.5メートル"), "ナンバー007　0.5メートル")

    def test_shared_tiles_follow_neighbours(self):
        self.assertEqual(reader.fix_shared("へンりー"), "ヘンリー")
        self.assertEqual(reader.fix_shared("ぺッと"), "ぺっと")
        self.assertEqual(reader.fix_shared("あッ"), "あっ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
