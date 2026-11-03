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
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("volume = 250", text)
        self.assertIn("auto_read = on", text)
        self.assertNotIn("retroarch_port", text)


class Loudness(unittest.TestCase):
    def test_voices_are_levelled(self):
        import math
        from urusai.speech import _wav_samples, trim

        def rms(voice):
            a = trim(_wav_samples(Speaker(voice=voice, volume=100).wav("たたかう どうぐ ポケモン にげる")))
            g = [x for x in a if abs(x) > 300]
            return 20 * math.log10(math.sqrt(sum(x * x for x in g) / len(g)))
        self.assertLess(abs(rms("tohoku") - rms("nitech")), 1.5)

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


def half_scrolled_canvas(g):
    """Mid-scroll: the old second line has moved up, the new one isn't typed yet."""
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.text(14, 1, "とびだしてきた！")
    return cv


class Streaming(unittest.TestCase):
    """Drive the server the way RetroArch's auto mode does, with a fake clock.
    Synthesis is made to take 3 s, like on the handheld."""

    SYNTH_SECONDS = 3.0

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
        render = self.app.narrator.render

        def slow_render(pieces):
            self.clock.t += self.SYNTH_SECONDS
            return render(pieces)
        self.app.narrator.render = slow_render
        self.app.narrator.say = lambda text, kind="talk": slow_render([(kind, text)])
        self.played = []

    def frame(self, canvas, settle=0.0):
        """One RetroArch request; returns the pieces spoken (None if silent)."""
        self.clock.t += settle
        planned = []
        plan = self.app.narrator.plan

        def spy(reading, repeat=False):
            pieces = plan(reading, repeat)
            planned.append(pieces)
            return pieces
        self.app.narrator.plan = spy
        body = json.dumps({"image": base64.b64encode(pngdec.encode(canvas.image())).decode()}).encode()
        try:
            resp = self.app.handle(body, {"output": ["sound,wav"]})
        finally:
            self.app.narrator.plan = plan
        self.assertEqual(resp.get("auto"), "auto")  # the stream must never stop
        if "sound" in resp:
            # RetroArch plays it (from when we replied), then asks again shortly after it ends
            self.clock.t += (len(base64.b64decode(resp["sound"])) - 44) / 96000 + 0.3
            spoken = planned[-1] if planned else ["announcement"]
            self.played.append(spoken)
            return spoken
        return None

    def test_dialogue_is_read_once_and_scrolls_read_only_the_new_line(self):
        self.assertEqual(self.frame(dialogue_canvas(self.g)),
                         [("talk", "やせいの ピカチュウが とびだしてきた！")])
        for _ in range(5):  # no loop after the (slow) speech
            self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=0.2))
        self.assertIsNone(self.frame(half_scrolled_canvas(self.g), settle=1.0))  # old line alone: nothing new
        self.assertEqual(self.frame(scrolled_canvas(self.g)), [("talk", "ゆけ！ ゼニガメ！")])
        self.assertIsNone(self.frame(scrolled_canvas(self.g), settle=0.2))

    def test_menu_open_move_close(self):
        self.frame(dialogue_canvas(self.g))
        self.assertIsNone(self.frame(battle_menu(self.g, 14, 9)))  # settling
        self.assertEqual(self.frame(battle_menu(self.g, 14, 9), settle=0.3),
                         [("cue", "open"), ("menu", "たたかう"), ("cue", "select"), ("menu", "ポケモン"),
                          ("menu", "どうぐ"), ("menu", "にげる")])
        self.assertIsNone(self.frame(battle_menu(self.g, 14, 9), settle=0.3))
        # cursor to どうぐ (third of four): just the option
        self.frame(battle_menu(self.g, 16, 9))
        self.assertEqual(self.frame(battle_menu(self.g, 16, 9), settle=0.3), [("menu", "どうぐ")])
        # cursor to にげる (last): option + low "tok"
        self.frame(battle_menu(self.g, 16, 14))
        self.assertEqual(self.frame(battle_menu(self.g, 16, 14), settle=0.3), [("menu", "にげる"), ("cue", "edge")])
        # menu closes onto a plain screen: the falling "closed" sound
        self.frame(Canvas(self.g))
        self.assertEqual(self.frame(Canvas(self.g), settle=0.5), [("cue", "close")])
        self.assertIsNone(self.frame(Canvas(self.g), settle=0.5))

    def test_say_it_again_repeats_once(self):
        self.frame(dialogue_canvas(self.g))
        self.assertFalse(self.app.press())  # stream alive: no hotkey needed
        self.assertEqual(self.frame(dialogue_canvas(self.g), settle=0.2),
                         [("talk", "やせいの ピカチュウが とびだしてきた！")])
        for _ in range(5):
            self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=0.2))

    def test_double_tap_mutes_and_unmutes(self):
        self.frame(Canvas(self.g))
        self.assertFalse(self.app.toggle_mute())
        self.assertEqual(self.frame(Canvas(self.g)), ["announcement"])  # よみあげ オフ
        self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=1.0))  # muted
        self.app.press()  # the button still works while muted
        self.assertIsNotNone(self.frame(dialogue_canvas(self.g)))
        self.app.toggle_mute()
        self.assertEqual(self.frame(dialogue_canvas(self.g)), ["announcement"])  # よみあげ オン

    def test_position_setting(self):
        self.app.settings.values["menu_position"] = "on"
        self.app._apply_settings()
        self.frame(battle_menu(self.g, 14, 9))
        spoken = self.frame(battle_menu(self.g, 14, 9), settle=0.3)
        self.assertIn(("menu", "1ばんめ"), spoken)

    def test_fresh_stream_on_empty_screen_is_valid_for_retroarch(self):
        body = json.dumps({"image": base64.b64encode(pngdec.encode(Canvas(self.g).image())).decode()}).encode()
        self.assertEqual(self.app.handle(body, {}), {"error": "No text found.", "auto": "auto"})
        self.assertEqual(self.app.handle(body, {}), {"auto": "auto"})

    def test_stopped_stream_needs_the_hotkey(self):
        self.assertTrue(self.app.press())  # nothing streaming yet
        self.frame(Canvas(self.g))
        self.assertFalse(self.app.press())
        self.clock.t += 10
        self.assertTrue(self.app.press())

    def test_auto_read_off_only_speaks_on_press(self):
        self.app.settings.values["auto_read"] = "off"
        self.frame(Canvas(self.g))
        self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=1.0))
        self.app.press()
        self.assertIsNotNone(self.frame(dialogue_canvas(self.g)))


def reader_of(app, canvas):
    from urusai import reader
    return reader.analyze_image(app.font, canvas.image())


class Narration(unittest.TestCase):
    def test_new_lines(self):
        from urusai.speech import new_lines
        self.assertEqual(new_lines(["b", "c"], ["a", "b"]), ["c"])
        self.assertEqual(new_lines(["b"], ["a", "b"]), [])          # mid-scroll: nothing new
        self.assertEqual(new_lines(["a", "b"], ["a", "b"]), [])
        self.assertEqual(new_lines(["x", "y"], ["a", "b"]), ["x", "y"])

    def test_cues_render(self):
        from urusai.speech import cue, to_wav
        for name in ("select", "open", "close", "edge"):
            self.assertEqual(to_wav(cue(name))[:4], b"RIFF")

    def test_taps(self):
        import time
        events = []
        taps = button.Taps(lambda: events.append("single"), lambda: events.append("double"), window=0.15)
        taps.press()
        time.sleep(0.3)
        taps.press()
        taps.press()
        time.sleep(0.3)
        self.assertEqual(events, ["single", "double"])


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
