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
        # upgrading keeps values and drops unknown keys
        with open(path, "w", encoding="utf-8") as f:
            f.write("volume = 250\nretroarch_port = 1\n")
        settings.upgrade(path)
        text = open(path, encoding="utf-8").read()
        self.assertIn("volume = 250", text)
        self.assertIn("auto_read = on", text)
        self.assertNotIn("retroarch_port", text)


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


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def scrolled_canvas(g):
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.text(14, 1, "とびだしてきた！")
    cv.text(16, 1, "ゆけ！ ゼニガメ！")
    cv.put(16, 18, "<more>")
    return cv


def battle_menu(g, cursor_row, cursor_col):
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.box(12, 8, 17, 19)
    cv.text(14, 10, "たたかう")
    cv.text(14, 15, "ポケモン")
    cv.text(16, 10, "どうぐ")
    cv.text(16, 15, "にげる")
    cv.put(cursor_row, cursor_col, "<cursor>")
    return cv


class Streaming(unittest.TestCase):
    """Drive the server the way RetroArch's auto mode does, with a fake clock."""

    def setUp(self):
        self.g = make_font()
        d = tempfile.mkdtemp()
        fontp = os.path.join(d, "f.json")
        font_from(self.g).save(fontp)
        cfg = os.path.join(d, "settings.txt")
        settings.write_template(cfg, {"captures_keep": 3})
        self.cap = os.path.join(d, "cap")
        self.clock = FakeClock()
        self.app = server.App(fontp, settings.Settings(cfg), capture_dir=self.cap,
                              clock=self.clock, sleep=self.clock.sleep)

    def frame(self, canvas):
        body = json.dumps({"image": base64.b64encode(pngdec.encode(canvas.image())).decode()}).encode()
        resp = self.app.handle(body, {"output": ["sound,wav"]})
        self.assertEqual(resp.get("auto"), "auto")  # the stream must never stop
        if "sound" in resp:  # RetroArch waits for the speech to finish
            self.clock.t = self.app.speaking_until + 0.05
        return resp

    def said(self, resp):
        return "sound" in resp

    def test_auto_reading_session(self):
        app, narrator = self.app, self.app.narrator
        # 1. stream just started (hotkey) on a dialogue box -> read it
        self.assertTrue(self.said(self.frame(dialogue_canvas(self.g))))
        self.assertEqual(narrator.spoken_dialogue, ["やせいの ピカチュウが", "とびだしてきた！"])
        # 2. same box again -> silence
        self.assertFalse(self.said(self.frame(dialogue_canvas(self.g))))
        # 3. box scrolled one line -> only the new line is planned
        plan = narrator.plan(reader_of(self.app, scrolled_canvas(self.g)))
        self.assertEqual(plan, [("talk", "ゆけ！ ゼニガメ！")])
        self.assertTrue(self.said(self.frame(scrolled_canvas(self.g))))
        # 4. battle menu opens: waits until it sits still, then reads all options, chime after ▶
        self.assertFalse(self.said(self.frame(battle_menu(self.g, 14, 9))))
        self.clock.t += 0.3
        r = reader_of(app, battle_menu(self.g, 14, 9))
        # reading order is row by row (this synthetic menu has ポケモン on the top row)
        self.assertEqual(narrator.plan(r), [("menu", "たたかう"), ("beep",), ("menu", "ポケモン"),
                                            ("menu", "どうぐ"), ("menu", "にげる")])
        self.assertTrue(self.said(self.frame(battle_menu(self.g, 14, 9))))
        # 5. cursor moves to にげる -> just the new option
        self.assertFalse(self.said(self.frame(battle_menu(self.g, 16, 14))))
        self.clock.t += 0.3
        self.assertEqual(narrator.plan(reader_of(app, battle_menu(self.g, 16, 14))), [("menu", "にげる")])
        self.assertTrue(self.said(self.frame(battle_menu(self.g, 16, 14))))
        # 6. nothing new -> silence; the button -> whole menu again
        self.assertFalse(self.said(self.frame(battle_menu(self.g, 16, 14))))
        self.assertFalse(app.press())  # stream alive: no need to press the hotkey
        self.assertTrue(self.said(self.frame(battle_menu(self.g, 16, 14))))
        # captures: only spoken screens, newest 3 kept
        self.assertEqual(len([x for x in os.listdir(self.cap) if x.endswith(".png")]), 3)

    def test_fresh_stream_on_empty_screen_is_valid_for_retroarch(self):
        self.assertEqual(self.frame(Canvas(self.g)), {"error": "No text found.", "auto": "auto"})
        self.assertEqual(self.frame(Canvas(self.g)), {"auto": "auto"})

    def test_stopped_stream_needs_the_hotkey(self):
        self.assertTrue(self.app.press())  # nothing streaming yet
        self.frame(Canvas(self.g))
        self.assertFalse(self.app.press())
        self.clock.t += 5
        self.assertTrue(self.app.press())

    def test_auto_read_off_only_speaks_on_press(self):
        self.app.settings.values["auto_read"] = "off"
        self.frame(Canvas(self.g))                       # stream running
        self.clock.t += 1
        self.assertFalse(self.said(self.frame(dialogue_canvas(self.g))))
        self.app.press()
        self.assertTrue(self.said(self.frame(dialogue_canvas(self.g))))


def reader_of(app, canvas):
    from urusai import reader
    return reader.analyze_image(app.font, canvas.image())


class Narration(unittest.TestCase):
    def test_new_lines(self):
        from urusai.speech import new_lines
        self.assertEqual(new_lines(["b", "c"], ["a", "b"]), ["c"])
        self.assertEqual(new_lines(["a", "b"], ["a", "b"]), ["a", "b"])   # same box: all again
        self.assertEqual(new_lines(["x", "y"], ["a", "b"]), ["x", "y"])

    def test_beep_wav(self):
        from urusai.speech import beep, to_wav
        self.assertEqual(to_wav(beep())[:4], b"RIFF")


class VirtualKeys(unittest.TestCase):
    def test_chord_events(self):
        from unittest import mock
        from urusai import vkbd
        writes = []
        with mock.patch.object(vkbd.os, "open", return_value=99), \
                mock.patch.object(vkbd.fcntl, "ioctl") as ioctl, \
                mock.patch.object(vkbd.os, "write", side_effect=lambda fd, b: writes.append(b)), \
                mock.patch.object(vkbd.time, "sleep"):
            k = vkbd.VirtualKeyboard()
            self.assertEqual(len(writes[0]), 1116)  # struct uinput_user_dev
            ioctl.assert_any_call(99, vkbd.UI_DEV_CREATE)
            k.chord()
        keys = [vkbd.EVENT.unpack(w)[2:] for w in writes[1:]]
        presses = [(c, v) for t, c, v in keys if t == vkbd.EV_KEY]
        self.assertEqual(presses, [(vkbd.KEY_F8, 1), (vkbd.KEY_F6, 1), (vkbd.KEY_F6, 0), (vkbd.KEY_F8, 0)])


class Bundle(unittest.TestCase):
    def test_bundled_voices(self):
        self.assertTrue({"mei", "tohoku", "nitech"} <= set(voices()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
