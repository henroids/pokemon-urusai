"""Service tests: settings, loudness, button mapping and a RetroArch-style request."""
import array
import base64
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import Canvas, dialogue_canvas, font_from, make_font  # noqa: E402
from urusai import audio, button, pngdec, server, settings  # noqa: E402
from urusai.tts import Speaker, voices  # noqa: E402


def tone(amplitude, n=4800, rate=48000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(array.array("h", [amplitude if i % 2 else -amplitude for i in range(n)]).tobytes())
    return buf.getvalue()


def peak(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return max(abs(s) for s in array.array("h", w.readframes(w.getnframes())))


class SettingsFile(unittest.TestCase):
    def test_defaults_template_and_reload(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "urusai_settings.txt")
        s = settings.Settings(path)
        self.assertEqual(s["button"], "L2")  # no file yet -> defaults
        settings.write_template(path)
        s.reload()
        self.assertEqual(s.values, settings.DEFAULTS)
        with open(path, "a", encoding="utf-8") as f:
            f.write("volume = 300  # louder\nvoice = tohoku\nbogus = 1\nspeed = fast\n")
        os.utime(path, (1, 1))  # force a new mtime
        self.assertTrue(s.reload())
        self.assertEqual((s["volume"], s["voice"], s["speed"]), (300, "tohoku", settings.DEFAULTS["speed"]))


class Loudness(unittest.TestCase):
    def test_quiet_parts_get_louder(self):
        self.assertEqual(peak(audio.louder(tone(4000), 200)), 8000)

    def test_never_clips(self):
        self.assertLessEqual(peak(audio.louder(tone(32000), 400)), audio.CEILING)

    def test_100_is_untouched_and_lower_is_quieter(self):
        raw = tone(10000)
        self.assertEqual(audio.louder(raw, 100), raw)
        self.assertEqual(peak(audio.louder(raw, 50)), 5000)


class Buttons(unittest.TestCase):
    def test_names_and_codes(self):
        self.assertEqual(button.button_code("L2"), 0x138)
        self.assertEqual(button.button_code("r3"), 0x13E)
        self.assertEqual(button.button_code("0x13a"), 0x13A)
        self.assertIsNone(button.button_code("off"))
        with self.assertRaises(ValueError):
            button.button_code("banana")

    def test_capability_bitmap(self):
        # one 64-bit word holding bit 0x138 % 64 = 56 ... in word index 0x138 // 64 = 4
        words = ["0"] * 5
        words[0] = "%x" % (1 << (0x138 % 64))
        caps = " ".join(words)
        self.assertTrue(button.has_key(caps, 0x138))
        self.assertFalse(button.has_key(caps, 0x139))

    def test_find_devices_in_fake_sysfs(self):
        root = tempfile.mkdtemp()
        for name, has_l2 in (("event0", False), ("event3", True)):
            d = os.path.join(root, name, "device", "capabilities")
            os.makedirs(d)
            bit = (1 << (0x138 % 64)) if has_l2 else 1
            with open(os.path.join(d, "key"), "w") as f:
                f.write("%x 0 0 0 0\n" % bit)
        self.assertEqual(button.devices_with(0x138, root), ["/dev/input/event3"])


    def test_watcher_fires_once_per_press(self):
        """Feed fake input_event records through a pipe standing in for /dev/input/eventN."""
        import time
        fifo = os.path.join(tempfile.mkdtemp(), "event9")
        os.mkfifo(fifo)
        pressed = []
        names = iter(["L2"] * 1000)
        orig = button.devices_with
        button.devices_with = lambda code: [fifo]
        try:
            watcher = button.ButtonWatcher(lambda: next(names, "off"), lambda: pressed.append(1),
                                           log=io.StringIO())
            watcher.start()
            with open(fifo, "wb") as f:
                ev = lambda code, value: button.EVENT.pack(0, 0, button.EV_KEY, code, value)
                f.write(ev(0x130, 1) + ev(0x138, 1) + ev(0x138, 0) + ev(0x138, 1))  # A, L2 down/up, bounce
                f.flush()
                time.sleep(0.5)
            self.assertEqual(pressed, [1])  # other buttons ignored, bounce within 0.4 s ignored
            self.assertIn("watching L2", watcher.status)
        finally:
            button.devices_with = orig


class RetroArchRequest(unittest.TestCase):
    def test_speech_round_trip(self):
        g = make_font()
        d = tempfile.mkdtemp()
        fontp = os.path.join(d, "f.json")
        font_from(g).save(fontp)
        cfg = os.path.join(d, "settings.txt")
        settings.write_template(cfg, {"captures_keep": 2})
        app = server.App(fontp, settings.Settings(cfg), capture_dir=os.path.join(d, "cap"), speaker=Speaker())
        srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/?source_lang=ja&target_lang=ja&output=sound,wav" % srv.server_address[1]

        def post(png):
            body = json.dumps({"image": base64.b64encode(png).decode(), "state": {"paused": 0}}).encode()
            with urllib.request.urlopen(urllib.request.Request(url, body)) as r:
                return json.loads(r.read())

        frame = pngdec.encode(dialogue_canvas(g).image())
        for _ in range(3):
            resp = post(frame)
        wav = base64.b64decode(resp["sound"])
        self.assertEqual(wav[:4], b"RIFF")
        self.assertGreater(len(wav), 48000)
        self.assertLessEqual(peak(wav), audio.CEILING)
        pngs = [x for x in os.listdir(os.path.join(d, "cap")) if x.endswith(".png")]
        self.assertEqual(len(pngs), 2)  # captures_keep honoured, oldest deleted
        self.assertEqual(post(pngdec.encode(Canvas(g).image())), {"error": "No text found."})
        srv.shutdown()
        srv.server_close()

    def test_bundled_voices(self):
        self.assertTrue({"mei", "tohoku", "nitech"} <= set(voices()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
