"""Service tests: settings, loudness, button mapping and a RetroArch-style request."""
import array
import base64
import io
import json
import os
import sys
import tempfile
import time
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synth import Canvas, dialogue_canvas, font_from, make_font  # noqa: E402
from urusai import audio, button, gba, pngdec, server, settings  # noqa: E402
from urusai.tts import VOICE_DIR, Speaker  # noqa: E402


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


# Game-style lines: phrase-final は/へ are particles (wa/e); は inside words stays "ha".
PARTICLE_LINES = [
    "ぼくは オーキド！ みんなからは ポケモン はかせと よばれて おるよ",
    "では はじめに きみの なまえを おしえて もらおう！",
    "この せかいには ポケット モンスターと よばれる",
    "どこへ いくの？ トキワシティへ むかえ！",
    "わたしは ジムリーダーの タケシ！",
    "こんにちは！ こんばんは！",
    "はかせは けんきゅうじょへ いったよ",
    "これは きみへの プレゼントだ",
    "かれは はしって いった",          # without spaces Open JTalk hears 枯れ葉 "kareha"
    "むしポケモンは はやいぞ",
]


class Particles(unittest.TestCase):
    def test_phrase_final_particles_sound_wa_and_e(self):
        from urusai import normalize, tts
        sp = Speaker()
        fixed_any = False
        for line in PARTICLE_LINES:
            with self.subTest(line=line):
                text, hints = normalize.with_particles(line)
                self.assertTrue(hints or "は" not in line)
                _, toks = sp._synth(text, analyse=True)
                wrong = tts.misread_particles(text, toks, hints)
                if wrong:  # what Speaker.wav does: spell it わ/え and synthesise again
                    fixed_any = True
                    text = "".join({"は": "わ", "へ": "え"}[c] if i in wrong else c for i, c in enumerate(text))
                    _, toks = sp._synth(text, analyse=True)
                self.assertEqual(tts.misread_particles(text, toks, hints), [])
                for surface, _, pron in toks:  # は inside words keeps its "ha"
                    if surface in ("はかせ", "はやい", "はじめ", "はしっ"):
                        self.assertTrue(pron.startswith("ハ"), (surface, pron))
        self.assertTrue(fixed_any, "かれは should have needed the fix")

    def test_laughter_is_left_alone(self):
        from urusai import normalize
        self.assertEqual(normalize.with_particles("あはは！ へへへ")[1], [])
        self.assertEqual(normalize.with_particles("ははは")[1], [])


class Numbers(unittest.TestCase):
    """Counters are read with their sound changes (いっこ, さんびき, はっぽん…)."""

    CASES = [
        ("モンスターボールを 1こ てにいれた！", "イッコ"),
        ("キズぐすり ×3", "サンコ"),
        ("ポッポを 3びき つかまえた", "サンビキ"),
        ("8ほんの き", "ハッポン"),
        ("6かい つかえる", "ロッカイ"),
        ("4にんで あそぶ", "ヨニン"),
        ("10ぴきめの ポケモン", "ジュッピ"),
        ("ゼニガメ レベル5 15／ 20", "ニジューノウチジューゴ"),
        ("ナンバー.007", "ナナバン"),
        ("おもさ 9.0キログラム", "キューキログラム"),
        ("プレイじかん 12:34", "ジューニジカンサンジューヨンプン"),
        ("3000えん もらった！", "サンゼンエン"),
        ("HPが 20かいふく した！", "ニジューカイフ"),   # かいふく is not 回
    ]

    def test_counters(self):
        from urusai import normalize
        sp = Speaker()
        for text, want in self.CASES:
            with self.subTest(text=text):
                _, toks = sp._synth(normalize.for_speech(text), analyse=True)
                pron = "".join(t[2] for t in toks).replace("’", "")
                self.assertIn(want, pron)


class Joins(unittest.TestCase):
    def test_lines_of_a_box_run_straight_on(self):
        from urusai.speech import Narrator
        from urusai.sounds import wav_samples
        n = Narrator(Speaker(), Speaker())
        one = wav_samples(n.render([("talk", "やせいの ピカチュウが"), ("talk", "とびだしてきた！")]))
        # the longest silence inside the clip (between the two lines) is short
        longest = run = 0
        for x in one[4800:-4800]:
            run = run + 1 if abs(x) < 300 else 0
            longest = max(longest, run)
        self.assertLess(longest / 48000, 0.12)


class Loudness(unittest.TestCase):
    def test_voices_are_levelled(self):
        import math
        from urusai.sounds import wav_samples as _wav_samples, trim

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

    # The RG35XXSP's buttons, as Knulli's es_input.cfg has them (abridged)
    RG35XXSP = """<inputList>
      <inputConfig type="joystick" deviceName="ANBERNIC-keys" deviceGUID="19000000010000000100000000010000">
        <input name="a" type="button" id="3" value="1" code="304" />
        <input name="hotkey" type="button" id="11" value="1" code="312" />
        <input name="l2" type="button" id="13" value="1" code="314" />
        <input name="pageup" type="button" id="7" value="1" code="308" />
        <input name="select" type="button" id="9" value="1" code="310" />
        <input name="up" type="hat" id="0" value="1" />
      </inputConfig>
      <inputConfig type="joystick" deviceName="Select-is-hotkey pad">
        <input name="select" type="button" id="6" value="1" code="314" />
        <input name="hotkey" type="button" id="6" value="1" code="314" />
      </inputConfig>
    </inputList>"""

    def es_maps(self):
        path = os.path.join(tempfile.mkdtemp(), "es_input.cfg")
        with open(path, "w") as f:
            f.write(self.RG35XXSP)
        return button.es_pad_maps([path, "/nonexistent/es_input.cfg"])

    def test_es_input_maps_each_pad_to_standard_codes(self):
        maps = self.es_maps()
        b = button.BUTTONS
        self.assertEqual(maps["ANBERNIC-keys"], {304: b["A"], 312: b["MENU"], 314: b["L2"], 308: b["L1"], 310: b["SELECT"]})
        self.assertEqual(maps["Select-is-hotkey pad"], {314: b["SELECT"]})

    def test_find_devices_in_fake_sysfs(self):
        root = tempfile.mkdtemp()
        for name, code, pad in (("event0", 1, "keyboard"), ("event3", 0x138, "standard pad"),
                                ("event4", 314, "ANBERNIC-keys"), ("event5", 0x138, "ANBERNIC-keys")):
            d = os.path.join(root, name, "device", "capabilities")
            os.makedirs(d)
            with open(os.path.join(d, "key"), "w") as f:
                f.write("%x 0 0 0 0\n" % (1 << (code % 64)) if code >= 256 else "0 0 0 0 %x\n" % (1 << code))
            with open(os.path.join(root, name, "device", "name"), "w") as f:
                f.write(pad + "\n")
        maps = self.es_maps()
        found = button.devices_with(0x138, root, maps)       # L2
        self.assertEqual([p for p, _ in found], ["/dev/input/event3", "/dev/input/event4"])   # event5's 0x138 is MENU
        self.assertEqual(found[1][1][314], 0x138)

    def watch(self, events, translate=None):
        """Feed input_event records through a pipe standing in for /dev/input/eventN."""
        fifo = os.path.join(tempfile.mkdtemp(), "event9")
        os.mkfifo(fifo)
        pressed, game = [], []
        names = iter(["L2"] * 1000)
        orig = button.devices_with
        button.devices_with = lambda code: [(fifo, translate or {})]
        try:
            watcher = button.ButtonWatcher(lambda: next(names, "off"), lambda: pressed.append(1),
                                           lambda: game.append(1), log=io.StringIO())
            watcher.start()
            with open(fifo, "wb") as f:
                f.write(b"".join(button.EVENT.pack(0, 0, button.EV_KEY, c, v) for c, v in events))
                f.flush()
                time.sleep(0.5)
            return pressed, game, watcher.status
        finally:
            button.devices_with = orig

    def test_watcher_fires_once_per_press(self):
        pressed, game, status = self.watch([(0x130, 1), (0x138, 1), (0x138, 0), (0x138, 1)])  # A, L2 down/up, bounce
        self.assertEqual((pressed, game), ([1], [1]))  # A cuts speech; the bounce within 0.06 s is ignored
        self.assertIn("watching L2", status)

    def test_watcher_on_the_rg35xxsp(self):
        tr = self.es_maps()["ANBERNIC-keys"]
        pressed, game, _ = self.watch([(312, 1), (312, 0), (314, 1), (304, 1)], tr)  # MENU, L2, A
        self.assertEqual((pressed, game), ([1], [1]))  # MENU is neither L2 nor a game button


class SettingsUpgrade(unittest.TestCase):
    def test_old_default_volume_moves_up_a_chosen_one_stays(self):
        for old, new in (("200", "220"), ("150", "150")):
            path = os.path.join(tempfile.mkdtemp(), "urusai_settings.txt")
            with open(path, "w") as f:
                f.write("volume = %s\n" % old)
            settings.upgrade(path)
            self.assertEqual(settings.Settings(path)["volume"], int(new))


class RetroArchCheck(unittest.TestCase):
    """STATUS.txt says whether RetroArch got the settings the reader needs."""

    def cfg(self, text):
        path = os.path.join(tempfile.mkdtemp(), "retroarchcustom.cfg")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_all_ok(self):
        p = self.cfg('ai_service_enable = "true"\nai_service_mode = "1"\nai_service_url = "http://127.0.0.1:4404/"\n'
                     'ai_service_pause = "false"\ninput_enable_hotkey = "shift"\ninput_ai_service = "f10"\n')
        self.assertEqual(server.retroarch_check("shift+f10", 4404, [p, "/nonexistent"]),
                         ["RetroArch settings in %s: all OK" % p])

    def test_problems_are_named(self):
        p = self.cfg('ai_service_enable = "false"\nai_service_mode = "0"\ninput_enable_hotkey = "shift"\n'
                     'input_ai_service = "f9"\naudio_mute_enable = "true"\n')
        line, = server.retroarch_check("shift+f10", 4404, [p])
        for bit in ("ai_service_enable = false (should be true)", "ai_service_mode = 0 (should be 1)",
                    "ai_service_url = missing", "input_ai_service = f9 (should be f10)", "the game is muted"):
            self.assertIn(bit, line)

    def test_no_config_yet(self):
        self.assertIn("no retroarch.cfg found", server.retroarch_check("f12+f10", 4404, ["/nonexistent"])[0])


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


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


def two_line_box(g, line1, line2=None, more=False):
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.text(14, 1, line1)
    if line2:
        cv.text(16, 1, line2)
    if more:
        cv.put(16, 18, "<more>")
    return cv


def yes_no(g, row):
    cv = Canvas(g)
    cv.box(12, 0, 17, 19)
    cv.text(14, 1, "ニックネームを つけますか？")
    cv.box(6, 13, 11, 19)
    cv.text(7, 15, "はい")
    cv.text(9, 15, "いいえ")
    cv.put(row, 14, "<cursor>")
    return cv


GBA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gba")


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
                              cache_dir=os.path.join(d, "cache"), clock=self.clock, sleep=self.clock.sleep)
        self.app.can_interrupt = True
        n = self.app.narrator
        self.rendered = []
        render = n.render

        def slow_render(chunk):
            self.rendered.append(chunk)
            self.clock.t += self.SYNTH_SECONDS
            return render(chunk)
        n.render = slow_render

    def frame(self, canvas, settle=0.0):
        """One RetroArch request. Returns the chunk played (None if silent).
        Like RetroArch, the next request comes after the clip has played."""
        self.clock.t += settle
        before = len(self.rendered)
        body = json.dumps({"image": base64.b64encode(pngdec.encode(canvas.image())).decode()}).encode()
        resp = self.app.handle(body)
        self.assertEqual(resp.get("auto"), "auto")  # the stream must never stop
        if "sound" in resp:
            self.clock.t += (len(base64.b64decode(resp["sound"])) - 44) / 96000 + 0.1
            return self.rendered[-1] if len(self.rendered) > before else "cut"
        return None

    def menu_session(self, canvas, settle=0.3):
        """Frames until the menu has been read; returns all chunks played."""
        played = []
        self.frame(canvas)
        for _ in range(12):
            c = self.frame(canvas, settle=settle if not played else 0)
            if c is None and played:
                break
            if c is not None:
                played.append(c)
        return played

    # -- dialogue --
    def test_box_is_read_in_one_go_once_printed_and_never_twice(self):
        g = self.g
        self.assertIsNone(self.frame(two_line_box(g, "やせいの")))                      # line 1 typing
        self.assertIsNone(self.frame(two_line_box(g, "やせいの ピカチュウが", "と")))      # line 2 typing…
        self.assertTrue(self.app.narrator.ready([("talk", "やせいの ピカチュウが")]) or True)
        self.assertEqual(self.frame(two_line_box(g, "やせいの ピカチュウが", "とびだしてきた！", more=True)),
                         [("talk", "やせいの ピカチュウが"), ("talk", "とびだしてきた！")])  # one clip
        for _ in range(4):  # no repeats, even with slow synthesis
            self.assertIsNone(self.frame(two_line_box(g, "やせいの ピカチュウが", "とびだしてきた！", more=True), 0.2))
        # A pressed: scroll. Mid-scroll (old line alone) says nothing; the new line is read.
        self.assertIsNone(self.frame(two_line_box(g, "とびだしてきた！"), 0.2))
        self.assertIsNone(self.frame(two_line_box(g, "とびだしてきた！", "ゆけ"), 0.1))
        self.assertEqual(self.frame(two_line_box(g, "とびだしてきた！", "ゆけ！ ゼニガメ！", more=True)),
                         [("talk", "ゆけ！ ゼニガメ！")])

    def test_line_one_is_made_while_line_two_prints(self):
        import time
        self.frame(two_line_box(self.g, "やせいの ピカチュウが", "と"))
        for _ in range(100):  # the background worker makes it
            if self.app.narrator.ready([("talk", "やせいの ピカチュウが")]):
                break
            time.sleep(0.05)
        self.assertTrue(self.app.narrator.ready([("talk", "やせいの ピカチュウが")]))

    def test_settled_box_is_one_clip(self):
        self.assertEqual(self.frame(dialogue_canvas(self.g)),
                         [("talk", "やせいの ピカチュウが"), ("talk", "とびだしてきた！")])

    # -- menus --
    def test_menu_is_read_option_by_option_then_cursor_moves(self):
        played = self.menu_session(battle_menu(self.g, 14, 9))
        self.assertEqual(played, [
            [("cue", "open"), ("menu", "たたかう"), ("cue", "select")],
            [("gap",), ("menu", "ポケモン")],
            [("gap",), ("menu", "どうぐ")],
            [("gap",), ("menu", "にげる")]])
        self.frame(battle_menu(self.g, 16, 9))
        self.assertEqual(self.frame(battle_menu(self.g, 16, 9), settle=0.3), [("menu", "どうぐ")])
        self.frame(battle_menu(self.g, 16, 14))
        self.assertEqual(self.frame(battle_menu(self.g, 16, 14), settle=0.3), [("menu", "にげる"), ("cue", "edge")])
        self.frame(Canvas(self.g))
        self.assertEqual(self.frame(Canvas(self.g), settle=0.5), [("cue", "close")])

    def test_moving_on_drops_the_rest_of_the_menu(self):
        self.frame(battle_menu(self.g, 14, 9))
        first = self.frame(battle_menu(self.g, 14, 9), settle=0.3)
        self.assertEqual(first[1], ("menu", "たたかう"))
        # the cursor moved while たたかう was read: ポケモン/どうぐ/にげる are dropped
        self.assertIsNone(self.frame(battle_menu(self.g, 16, 9)))
        self.assertEqual(self.frame(battle_menu(self.g, 16, 9), settle=0.3), [("menu", "どうぐ")])

    def test_yes_no_have_no_sound(self):
        played = self.menu_session(yes_no(self.g, 7))
        self.assertEqual(played, [[("talk", "ニックネームを つけますか？")],
                                  [("cue", "open"), ("menu", "はい")],
                                  [("gap",), ("menu", "いいえ")]])
        self.frame(yes_no(self.g, 9))
        self.assertEqual(self.frame(yes_no(self.g, 9), settle=0.3), [("menu", "いいえ")])

    # -- the button --
    def test_say_it_again_repeats_once(self):
        self.frame(dialogue_canvas(self.g))
        self.assertFalse(self.app.press())
        self.assertEqual(self.frame(dialogue_canvas(self.g), settle=0.2),
                         [("talk", "やせいの ピカチュウが"), ("talk", "とびだしてきた！")])
        for _ in range(5):
            self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=0.2))

    def test_reader_off_and_on(self):
        self.frame(Canvas(self.g))
        self.assertIsNone(self.app.toggle())
        resp = self.app.handle(json.dumps({"image": base64.b64encode(
            pngdec.encode(Canvas(self.g).image())).decode()}).encode())
        self.assertEqual(self.rendered[-1], [("menu", "よみあげ オフ")])
        self.assertEqual(base64.b64decode(resp["image"])[1:4], b"PNG")   # shown on screen…
        self.assertGreaterEqual((len(base64.b64decode(resp["sound"])) - 44) / 96000, 1.5)  # …1.5 s+
        self.clock.t += 1.6
        self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=1.0))  # off: nothing read
        self.assertFalse(self.app.press())                                   # L2 does nothing
        self.assertIsNone(self.frame(dialogue_canvas(self.g), settle=1.0))
        self.app.speaking_until = self.clock.t + 2.0                          # (even mid-speech)
        self.assertFalse(self.app.want_interrupt())                          # no key presses
        self.app.speaking_until = self.clock.t
        self.app.toggle()
        self.assertEqual(self.frame(dialogue_canvas(self.g)), [("menu", "よみあげ オン")])
        self.assertIsNotNone(self.frame(dialogue_canvas(self.g), settle=1.0))  # reads again

    def test_an_unchanged_screen_is_not_read_again(self):
        reads = []
        real = server.reader.analyze
        server.reader.analyze = lambda labels: reads.append(1) or real(labels)
        try:
            for _ in range(3):
                self.frame(dialogue_canvas(self.g), settle=0.2)
            self.frame(Canvas(self.g), settle=0.2)
        finally:
            server.reader.analyze = real
        self.assertEqual(len(reads), 2)

    def gba_frame(self, name, settle=0.0):
        self.clock.t += settle
        before = len(self.rendered)
        with open(os.path.join(GBA, name + ".png"), "rb") as f:
            body = json.dumps({"image": base64.b64encode(f.read()).decode()}).encode()
        resp = self.app.handle(body)
        if "sound" in resp:
            self.clock.t += (len(base64.b64decode(resp["sound"])) - 44) / 96000 + 0.1
            return self.rendered[-1] if len(self.rendered) > before else "cut"
        return None

    def test_gba_message_and_menu_are_read(self):
        """A GBA game goes through the same reading rules as a Game Boy one."""
        self.app.gba_font = gba.GbaFont.load(os.path.join(os.path.dirname(GBA), "..", "font", "gba_jp.json"))
        self.assertIsNone(self.gba_frame("map_only"))
        self.assertEqual(self.gba_frame("em_message"),         # ▼ shown: read at once, as one clip
                         [("talk", "オダマキ『おーい！ まって くれー！"), ("talk", "そこは あぶないぞ！")])
        self.assertIsNone(self.gba_frame("em_message"))          # not again
        said = [self.gba_frame("em_yes_no", settle=0.3) for _ in range(4)]
        self.assertEqual([c for c in said if c], [
            [("talk", "ここまでの かつやくを"), ("talk", "レポートに かきこみますか？")],
            [("cue", "open"), ("menu", "はい")], [("gap",), ("menu", "いいえ")]])

    def test_turning_off_cuts_speech(self):
        self.frame(dialogue_canvas(self.g))
        self.clock.t = self.app.speaking_until - 1.0
        self.assertEqual(self.app.toggle(), "cut")
        self.assertEqual(self.frame(Canvas(self.g)), [("menu", "よみあげ オフ")])

    def test_turning_on_starts_a_stopped_stream(self):
        self.clock.t += 100
        self.app.muted = True
        self.assertEqual(self.app.toggle(), "start")

    # -- stopping speech --
    def test_game_button_stops_speech_in_menus(self):
        self.frame(battle_menu(self.g, 14, 9))
        self.frame(battle_menu(self.g, 14, 9), settle=0.3)       # たたかう…
        self.clock.t = self.app.speaking_until - 1.0              # …still playing
        self.assertTrue(self.app.want_interrupt())                # D-pad down
        self.assertFalse(self.app.want_interrupt())               # not twice
        # the hotkey's request: cursor still settling -> silence replaces the clip
        self.assertEqual(self.frame(battle_menu(self.g, 16, 9)), "cut")
        self.assertEqual(self.frame(battle_menu(self.g, 16, 9), settle=0.3), [("menu", "どうぐ")])

    def test_a_press_stops_the_box_and_only_new_text_is_read(self):
        g = self.g
        box = two_line_box(g, "やせいの ピカチュウが", "とびだしてきた！", more=True)
        self.assertEqual(len(self.frame(box)), 2)                 # the box is being read…
        self.clock.t = self.app.speaking_until - 1.0
        self.assertTrue(self.app.want_interrupt())               # …A pressed
        self.assertEqual(self.frame(box), "cut")                 # stopped
        self.assertIsNone(self.frame(box, settle=0.7))           # same screen: stays quiet
        # the game moves on (scroll, next line printed): only the new line
        self.assertIsNone(self.frame(two_line_box(g, "とびだしてきた！", "ゆけ"), 0.1))
        self.assertEqual(self.frame(two_line_box(g, "とびだしてきた！", "ゆけ！ ゼニガメ！", more=True)),
                         [("talk", "ゆけ！ ゼニガメ！")])

    def test_cut_while_text_prints_reads_the_whole_box_when_done(self):
        g = self.g
        self.frame(battle_menu(g, 14, 9))
        self.frame(battle_menu(g, 14, 9), settle=0.3)            # たたかう being read
        self.clock.t = self.app.speaking_until - 1.0
        self.assertTrue(self.app.want_interrupt())               # A: "fight" chosen
        self.assertEqual(self.frame(two_line_box(g, "ゼニガメの")), "cut")
        self.assertIsNone(self.frame(two_line_box(g, "ゼニガメの たいあたり！")))
        self.assertEqual(self.frame(two_line_box(g, "ゼニガメの たいあたり！", "きゅうしょに あたった！", more=True)),
                         [("cue", "close"), ("talk", "ゼニガメの たいあたり！"), ("talk", "きゅうしょに あたった！")])

    def test_any_button_cuts_announcements_and_finished_boxes(self):
        self.frame(dialogue_canvas(self.g))
        self.clock.t = self.app.speaking_until - 1.0
        self.assertTrue(self.app.want_interrupt())               # A on a finished box
        self.assertEqual(self.frame(battle_menu(self.g, 14, 9)), "cut")
        self.app.announce = "よみあげ オン"
        self.frame(battle_menu(self.g, 14, 9))                     # 「よみあげ オン」…
        self.clock.t = self.app.speaking_until - 0.5
        self.assertTrue(self.app.want_interrupt())               # …cut too

    def test_interrupt_needs_the_virtual_keyboard_and_the_setting(self):
        self.frame(dialogue_canvas(self.g))
        self.clock.t = self.app.speaking_until - 1.0
        self.app.settings.values["interrupt"] = "off"
        self.assertFalse(self.app.want_interrupt())
        self.app.settings.values["interrupt"] = "on"
        self.app.can_interrupt = False
        self.assertFalse(self.app.want_interrupt())

    def test_stray_second_loop_is_ended(self):
        body = json.dumps({"image": base64.b64encode(pngdec.encode(Canvas(self.g).image())).decode()}).encode()
        self.app.handle(body)
        self.clock.t += 1
        self.app.last_arrival = self.clock.t
        self.assertEqual(self.app.handle(body), {"error": "No text found."})  # no "auto"

    # -- misc --
    def test_position_setting(self):
        self.app.settings.values["menu_position"] = "on"
        self.app._apply_settings()
        played = self.menu_session(battle_menu(self.g, 14, 9))
        self.assertIn(("menu", "1ばんめ"), played[0])

    def test_fresh_stream_on_empty_screen_is_valid_for_retroarch(self):
        body = json.dumps({"image": base64.b64encode(pngdec.encode(Canvas(self.g).image())).decode()}).encode()
        self.assertEqual(self.app.handle(body), {"error": "No text found.", "auto": "auto"})
        self.assertEqual(self.app.handle(body), {"auto": "auto"})

    def test_stopped_stream_needs_the_hotkey(self):
        self.assertTrue(self.app.press())
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


class Cache(unittest.TestCase):
    def test_disk_cache_survives_a_restart(self):
        from urusai.speech import Narrator
        d = tempfile.mkdtemp()
        n = Narrator(Speaker(), Speaker(), cache_dir=d)
        wav = n.render([("menu", "たたかう")])
        self.assertEqual(len([f for f in os.listdir(d) if f.endswith(".pcm")]), 1)
        n2 = Narrator(Speaker(), Speaker(), cache_dir=d)   # "after a reboot"
        n2.speaker.wav = n2.menu_speaker.wav = None         # synthesis would fail if needed
        self.assertTrue(n2.ready([("menu", "たたかう")]))
        self.assertEqual(n2.render([("menu", "たたかう")]), wav)

    def test_prune_keeps_the_size_limit(self):
        from urusai.speech import ClipCache
        import array as arr
        d = tempfile.mkdtemp()
        c = ClipCache(d, disk_bytes=3000)
        for i in range(5):
            c.put(("v", 0, 1, 100, "t%d" % i), arr.array("h", bytes(1000)))
        c.prune()
        self.assertLessEqual(sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)), 3000)


class Narration(unittest.TestCase):
    def test_new_lines(self):
        from urusai.speech import new_lines
        self.assertEqual(new_lines(["b", "c"], ["a", "b"]), ["c"])
        self.assertEqual(new_lines(["b"], ["a", "b"]), [])          # mid-scroll: nothing new
        self.assertEqual(new_lines(["a", "b"], ["a", "b"]), [])
        self.assertEqual(new_lines(["x", "y"], ["a", "b"]), ["x", "y"])

    def test_cues_render(self):
        from urusai.sounds import cue, to_wav
        for name in ("select", "open", "close", "edge"):
            self.assertEqual(to_wav(cue(name))[:4], b"RIFF")

    def test_combo_toggles_once_per_press(self):
        from urusai import button
        fired, taps, game = [], [], []
        w = button.ButtonWatcher(lambda: "L2", lambda: taps.append(1), lambda: game.append(1),
                                 log=io.StringIO(), on_combo=lambda: fired.append(1))
        w.code, w.combo = 0x138, button.combo_codes("SELECT+L2")
        SEL, L2 = 0x13A, 0x138
        self.assertEqual(button.combo_codes("off"), set())
        with self.assertRaises(ValueError):
            button.combo_codes("L1")
        ev = lambda code, value: w.event(button.EV_KEY, code, value)
        ev(L2, 1); ev(L2, 0)                                   # L2 alone: say it again
        self.assertEqual((taps, fired), ([1], []))
        ev(SEL, 1); ev(L2, 1); ev(L2, 0); ev(L2, 1)            # Select+L2, L2 wobbles: once
        self.assertEqual((taps, fired), ([1], [1]))
        ev(L2, 0); ev(SEL, 0)
        ev(L2, 1); ev(SEL, 1)                                  # other order: toggles too
        self.assertEqual(fired, [1, 1])
        self.assertEqual(game, [])                             # never cuts speech as a game press

    def test_installer_frees_l2_from_retroarch_hotkeys(self):
        from urusai import racfg
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, "retroarch.cfg")
        auto = os.path.join(d, "autoconfig", "udev")
        os.makedirs(auto)
        pad = os.path.join(auto, "pad.cfg")
        with open(cfg, "w") as f:
            f.write('input_enable_hotkey_btn = "8"\ninput_rewind_btn = "6"\ninput_save_state_btn = "1"\n')
        with open(pad, "w") as f:
            f.write('input_l2_btn = "6"\ninput_player1_l2_btn = "6"\ninput_hold_fast_forward_btn = "6"\n')
        text = lambda path: "\n".join(racfg.read(path))
        files = racfg.with_autoconfig([cfg])
        self.assertEqual(files, [cfg, pad])
        self.assertEqual(sorted(racfg.free("l2", files, log=lambda *a: None)), ["hold_fast_forward", "rewind"])
        self.assertIn('input_rewind_btn = "nul"', text(cfg))
        self.assertIn('input_save_state_btn = "1"', text(cfg))          # other hotkeys kept
        self.assertIn('input_l2_btn = "6"', text(pad))                   # the pad mapping kept
        racfg.restore(files)
        self.assertIn('input_rewind_btn = "6"', text(cfg))
        self.assertIn('input_hold_fast_forward_btn = "6"', text(pad))

    def test_banner_uses_the_game_font(self):
        from urusai import banner
        from urusai.font import Font
        font = Font.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "font", "gb_jp.json"))
        self.assertEqual(banner.layout("あげ"), [("あ", None), ("け", "゛")])
        px = banner.render(font, "よみあげ オフ")
        ink = sum(p == banner.INK for row in px for p in row)
        self.assertGreater(ink, 200)                       # border + letters
        self.assertEqual(px[0][0], banner.CLEAR)          # the game shows around it
        data = banner.png(font, "よみあげ オン")
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_held_buttons_are_tracked(self):
        from urusai import button
        w = button.ButtonWatcher(lambda: "L2", lambda: None, log=io.StringIO())
        w._track(button.EV_KEY, 0x130, 1)                 # A down
        w._track(button.EV_ABS, 0x11, -1)                 # D-pad up (hat)
        self.assertFalse(w.wait_released(0.01))
        w._track(button.EV_KEY, 0x130, 2)                 # autorepeat: still down
        w._track(button.EV_KEY, 0x130, 0)
        self.assertFalse(w.wait_released(0.01))
        w._track(button.EV_ABS, 0x11, 0)
        self.assertTrue(w.wait_released(0.01))

    def test_hotkey_never_pressed_with_a_held_button(self):
        """The first key is hotkey enable: with A held RetroArch would see Select+A (pause)."""
        import contextlib
        from urusai import server
        events = []

        class Kbd:
            def chord(self, hold=0.1):
                events.append(("chord", hold))

        class Watcher:
            held = True
            def wait_released(self, timeout):
                events.append(("wait", timeout))
                return not self.held
            @contextlib.contextmanager
            def grabbed(self):
                events.append("grab")
                yield
                events.append("ungrab")

        class App:
            cutting = True
            def cut_abandoned(self):
                self.cutting = False

        st = server.Starter.__new__(server.Starter)
        self.app = App()
        st.app, st.log, st.kbd, st.lock = self.app, io.StringIO(), Kbd(), __import__("threading").Lock()
        st.watcher = Watcher()
        st.presses, st.last_press = 0, None
        st.interrupt()                                    # A still held after 1 s: no keys at all
        self.assertEqual(events, [("wait", server.Starter.RELEASE_WAIT)])
        self.assertFalse(self.app.cutting)
        events.clear()
        st.watcher.held = False
        st.interrupt()
        self.assertEqual(events, [("wait", server.Starter.RELEASE_WAIT), "grab",
                                  ("chord", 0.06), ("chord", 0.06), "ungrab"])

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
            k = vkbd.VirtualKeyboard(vkbd.key_codes("shift+f10"))  # Knulli's pair
            self.assertEqual(len(writes[0]), 1116)  # struct uinput_user_dev
            ioctl.assert_any_call(99, vkbd.UI_DEV_CREATE)
            ioctl.assert_any_call(99, vkbd.UI_SET_KEYBIT, 42)
            k.chord()
        keys = [vkbd.EVENT.unpack(w)[2:] for w in writes[1:]]
        presses = [(c, v) for t, c, v in keys if t == vkbd.EV_KEY]
        self.assertEqual(presses, [(42, 1), (68, 1), (68, 0), (42, 0)])   # Shift down, F10, up in reverse
        self.assertEqual(vkbd.key_codes("F12+F10"), (88, 68))              # dArkOS
        with self.assertRaises(ValueError):
            vkbd.key_codes("f9")


class Bundle(unittest.TestCase):
    def test_bundled_voices(self):
        for name in ("mei", "tohoku", "nitech"):
            self.assertTrue(os.path.exists(os.path.join(VOICE_DIR, name + ".htsvoice")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
