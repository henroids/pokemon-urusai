"""End-to-end tests with a synthetic Gen 1-style screen (no game assets needed).

Random 8x8 glyphs stand in for the real font, laid out the way Gen 1 does it:
text on rows 14/16 with ゛/゜ in the row above, box borders, a ▶ cursor.
"""
import base64
import json
import os
import random
import sys
import threading
import unittest
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from urusai import normalize, pngdec, reader, screen  # noqa: E402
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


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.g = make_font()
        self.font = font_from(self.g)

    def test_dialogue_with_dakuten(self):
        img = dialogue_canvas(self.g).image()
        self.assertEqual(reader.read_image(self.font, img), "やせいの ピカチュウが とびだしてきた！")

    def test_scaled_phone_screenshot(self):
        img = dialogue_canvas(self.g).image(scale=7, pad=(400, 36))  # 1920x1080-ish Thor capture
        self.assertEqual(reader.read_image(self.font, img), "やせいの ピカチュウが とびだしてきた！")

    def test_start_menu_reads_selected_item(self):
        cv = Canvas(self.g)
        cv.box(0, 10, 15, 19)
        for i, item in enumerate(["ずかん", "ポケモン", "どうぐ", "レッド", "レポート", "せってい", "とじる"]):
            cv.text(2 + i * 2, 12, item)
        cv.put(6, 11, "<cursor>")
        self.assertEqual(reader.read_image(self.font, cv.image()), "どうぐ")

    def test_battle_menu_selected(self):
        cv = Canvas(self.g)
        cv.box(12, 0, 17, 19)
        cv.box(12, 8, 17, 19)
        cv.text(14, 10, "たたかう")
        cv.text(14, 15, "ポケモン")
        cv.text(16, 10, "どうぐ")
        cv.text(16, 15, "にげる")
        cv.put(16, 14, "<cursor>")
        self.assertEqual(reader.read_image(self.font, cv.image()), "にげる")

    def test_learning_round_trip(self):
        """Label a screenshot with tools/learn.py's logic and read it back."""
        import subprocess, tempfile
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
        self.assertIn("やせいの ピカチュウが とびだしてきた！", out)

    def test_normalize(self):
        self.assertEqual(normalize.for_speech("ニドラン♂‥‥ まって！"), "ニドランオス、　まって！")


class ServerTests(unittest.TestCase):
    def test_retroarch_style_request(self):
        from urusai import server
        from urusai.tts import Speaker
        import tempfile
        g = make_font()
        d = tempfile.mkdtemp()
        fontp = os.path.join(d, "f.json")
        font_from(g).save(fontp)
        app = server.App(fontp, capture_dir=os.path.join(d, "cap"), speaker=Speaker())
        srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        png = pngdec.encode(dialogue_canvas(g).image())
        body = json.dumps({"image": base64.b64encode(png).decode(), "label": "Pokemon Red",
                           "state": {"paused": 1, "a": 0}}).encode()
        url = "http://127.0.0.1:%d/?source_lang=ja&target_lang=ja&output=sound,wav" % port
        resp = json.loads(urllib.request.urlopen(urllib.request.Request(url, body)).read())
        wav = base64.b64decode(resp["sound"])
        self.assertEqual(wav[:4], b"RIFF")
        self.assertGreater(len(wav), 48000)  # > 0.5 s of audio
        self.assertTrue(os.listdir(os.path.join(d, "cap")))
        # blank screen -> RetroArch's special "No text found." error
        blank = pngdec.encode(Canvas(g).image())
        resp = json.loads(urllib.request.urlopen(urllib.request.Request(
            url, json.dumps({"image": base64.b64encode(blank).decode()}).encode())).read())
        self.assertEqual(resp, {"error": "No text found."})
        srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
