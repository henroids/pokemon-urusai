"""RetroArch AI Service endpoint (VGTranslate-compatible), speech only, offline.

RetroArch POSTs {"image": <base64 PNG of the core frame>, ...} to
<url>?output=sound,wav and plays the base64 WAV we return under "sound".

We keep RetroArch in its "auto" mode: every reply carries "auto": "auto",
so RetroArch sends the next frame as soon as any speech has finished.
That stream lets us
  * read new dialogue and menu choices automatically, a short clip at a
    time (a later clip is dropped if the screen has moved on),
  * prepare speech before it's needed, so it plays almost at once,
  * serve the button on the next frame: tap = say it again, double tap =
    auto reading off/on.
The stream starts with RetroArch's AI Service hotkey, which we press
through a virtual keyboard when a game starts or the button is pressed.

Stopping speech: RetroArch only asks again once a clip has finished. When
any game button is pressed mid-speech we press the hotkey twice: the first
press ends auto mode, the second sends a request at once, and our reply
(the new speech, or a moment of silence) replaces the clip that's playing.
The extra loop this leaves behind is ended by replying to its duplicate
request without "auto".

Run:  python3 -m urusai.server [--settings FILE] [--capture DIR] [--cache DIR]
"""
import argparse
import base64
import collections
import contextlib
import datetime
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, banner, gba, pngdec, reader, screen
from .button import ButtonWatcher, Taps
from .font import Font
from .settings import Settings
from .sounds import duration, pad_to, silence, to_wav
from .speech import Narrator
from . import tts
from .tts import HERE, Speaker

NO_TEXT = "No text found."
POLL = 0.1             # seconds between frames while nothing is said
STABLE_MENU = 0.15     # a menu must sit still this long before it's read
STABLE_TEXT = 0.4      # dialogue without ▼ that stopped changing this long is complete
LATENCIES = 50         # recent readings timed for STATUS.txt
PRESS_TIMEOUT = 1.5    # a press is served after this even if text still moves
STREAM_GAP = 4.0       # no frame for this long (and not speaking) = stream stopped
SPEECH_MARGIN = 1.5    # RetroArch asks again a little after our speech has played
BOX_GONE = 0.3         # message box absent this long = the next box is a new one
DUPLICATE = 0.06       # two requests closer than this: the second is a stray loop
INTERRUPT_MIN_LEFT = 0.3  # don't bother stopping speech that's about to end
CUT_SPACING = 0.3      # …or twice in a row
CUT = to_wav(silence(120))  # replaces (stops) the clip that's playing
CUT_TIMEOUT = 1.5      # a stop request whose hotkey never arrived is given up
UNREAD_EVERY = 10.0    # gba_learn: keep a GBA screen with nothing read this often, at most
MESSAGE_SECONDS = 1.5   # 「よみあげ オン／オフ」 stays on screen at least this long


class App:
    def __init__(self, font_path, settings, capture_dir=None, speaker=None, menu_speaker=None,
                 cache_dir=None, clock=time.monotonic, sleep=time.sleep):
        self.font_path = font_path
        self.font = Font.load(font_path)
        self.font_mtime = self._mtime()
        self.started = datetime.datetime.now().isoformat(timespec="seconds")
        self.gba_font = gba.GbaFont.load(os.path.join(os.path.dirname(font_path), "gba_jp.json"))
        self.seen = (None, None, None)   # the last frame as sent, what it read as, its picture
        self.last_unread = -1e9
        self.settings = settings
        self.narrator = Narrator(speaker or Speaker(), menu_speaker or Speaker(), cache_dir=cache_dir)
        self._apply_settings()
        self.capture_dir = capture_dir
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.last_arrival = -1e9    # when the last request came in
        self.last_frame = -1e9      # when the last real frame was handled
        self.frames = 0             # frames RetroArch has sent (for STATUS.txt)
        self.last_said = ""         # what was last said (for STATUS.txt)
        self.speaking_until = -1e9  # when the clip we last sent ends
        self.pending = None         # time of an unserved "say it again"
        self.announce = None        # a message of our own to say (and show) next, e.g. 「よみあげ オフ」
        self.muted = False          # Select+L2 or double tap: the reader is off
        self.cutting = False        # a hotkey-made request is coming to stop the speech
        self.last_cut = -1e9
        self.can_interrupt = False  # set when the virtual keyboard works
        self.hold = None            # after a cut: the screen it was cut on (stay quiet until it changes)
        self.queue = collections.deque()  # clips still to say for the current screen…
        self.queue_sig = None             # …and which screen that was
        self.sig = None             # what's on screen now…
        self.stable_since = 0.0     # …and since when
        self.spoken_sig = None      # the screen we last read aloud
        self.wait_chunk = None      # the speech that's waiting for the natural voice…
        self.wait_since = 0.0       # …since when
        self.latency = collections.deque(maxlen=LATENCIES)  # (text still → speech sent, of which waiting, making)

    # ---- state ----------------------------------------------------------
    def _mtime(self):
        try:
            return os.path.getmtime(self.font_path)
        except OSError:
            return 0

    def _apply_settings(self):
        s, n = self.settings, self.narrator
        n.speaker.configure(s["voice"], s["speed"], s["volume"], s["natural_speed"])
        n.menu_speaker.configure(s["menu_voice"], s["speed"], s["volume"], s["natural_speed"])
        n.cues = s["sound_cues"] == "on"
        n.position = s["menu_position"] == "on"
        n.pause_ms = max(0, min(2000, s["option_pause"]))

    def refresh(self):
        """Pick up edits to the font or the settings file."""
        m = self._mtime()
        if m != self.font_mtime:
            self.font, self.font_mtime = Font.load(self.font_path), m
            self.seen = (None, None, None)
        if self.settings.reload():
            self._apply_settings()

    def stream_alive(self, now=None):
        now = self.clock() if now is None else now
        return now - self.last_frame < STREAM_GAP or now < self.speaking_until + SPEECH_MARGIN

    # ---- the button and the game buttons ----------------------------------
    def press(self):
        """Single tap: say it again. Returns True if the stream must be (re)started."""
        with self.lock:
            if self.muted:
                return False        # the reader is off: the button does nothing
            self.pending = self.clock()
            return not self.stream_alive()

    def toggle(self):
        """Select+L2 or double tap: the reader off/on, said and shown on screen.
        Returns "start" if the stream must be started, "cut" if speech is
        playing and must stop for the message, else None."""
        with self.lock:
            self.muted = not self.muted
            self.announce = "よみあげ オフ" if self.muted else "よみあげ オン"
            self.queue.clear()
            self.pending = None
            now = self.clock()
            if not self.stream_alive(now):
                return "start"
            if self.can_interrupt and now < self.speaking_until - INTERRUPT_MIN_LEFT and not self.cutting:
                self.cutting, self.last_cut = True, now
                return "cut"
            return None

    def want_interrupt(self):
        """A game button was pressed. True = stop the speech now (press the hotkey twice).
        Like a screen reader: any key stops speech, whatever is being said; then
        only what's new is read."""
        with self.lock:
            now = self.clock()
            if self.cutting and now - self.last_cut > CUT_TIMEOUT:
                self.cutting = False  # the hotkey never arrived
            if (self.muted or not self.can_interrupt or self.settings["interrupt"] != "on" or self.cutting
                    or now > self.speaking_until - INTERRUPT_MIN_LEFT or now - self.last_cut < CUT_SPACING):
                return False
            self.cutting, self.last_cut = True, now
            self.queue.clear()
            self.hold = self.sig                # a press means "stop": quiet until the screen changes
            return True

    def cut_abandoned(self):
        with self.lock:
            self.cutting = False

    # ---- one frame from RetroArch ------------------------------------------
    def read(self, picture):
        """(Reading, image to keep) of a frame as RetroArch sent it (base64 PNG).
        A screen that hasn't changed since the last frame isn't read again."""
        if picture != self.seen[0]:
            img = pngdec.decode(base64.b64decode(picture))
            if gba.is_gba(img):
                reading = gba.analyze(self.gba_font, img)
            else:
                img = screen.to_gb_frame(img)
                reading = reader.analyze(reader.label_grid(self.font, screen.tiles(img)))
            self.seen = (picture, reading, img)
        return self.seen[1:]

    def handle(self, body):
        arrival = self.clock()
        with self.lock:
            if self.cutting and arrival - self.last_cut > CUT_TIMEOUT:
                self.cutting = False
            if arrival - self.last_arrival < DUPLICATE and not self.cutting:
                self.last_arrival = arrival
                return {"error": NO_TEXT}  # a stray second loop: no "auto" ends it
            self.last_arrival = arrival
        picture = json.loads(body)["image"]
        with self.lock:
            self.refresh()
            reading, img = self.read(picture)
            now = self.clock()
            fresh = not self.stream_alive(now)  # the stream (re)started: reply with something real
            cut, self.cutting = self.cutting, False
            self.last_frame = now
            self.frames += 1
            reply = self._decide(reading, img, now, cut)
            if reply:
                return reply
            if cut:
                self.speaking_until = now
                return {"sound": base64.b64encode(CUT).decode("ascii"), "auto": "auto"}
        self.sleep(POLL)  # pace the stream while nothing is said (also keeps real requests apart)
        return {"error": NO_TEXT, "auto": "auto"} if fresh else {"auto": "auto"}

    def _decide(self, reading, img, now, cut):
        n = self.narrator
        sig = (reading.flat(), tuple(reading.options), reading.selected, tuple(reading.other))
        if sig != self.sig:
            self.sig, self.stable_since = sig, now
        stable = now - self.stable_since
        if reading.kind in ("other", "none") and stable >= BOX_GONE:
            n.box_closed()
        settled = reading.more or stable >= STABLE_TEXT

        # 1. the rest of what we were saying, if the screen hasn't moved on
        if self.queue:
            if sig == self.queue_sig and not cut:
                if not self._voice_ready(self.queue[0], now):
                    return None
                return self._send(self.queue.popleft(), img, reading)
            self.queue.clear()
        # 2. our own announcements, shown on screen until the next reply
        if self.announce:
            text, self.announce = self.announce, None
            return self._send_wav(pad_to(n.say(text, "menu"), MESSAGE_SECONDS), img, text,
                                  overlay=banner.png(self.font, text, img.width, img.height))
        if self.muted:
            return None           # the reader is off
        if reading.kind == "none" and img.width != screen.GB_W:
            self.keep_unread(img, now)

        ready = {"menu": stable >= STABLE_MENU, "dialogue": True,
                 "other": stable >= STABLE_MENU, "none": stable >= BOX_GONE}[reading.kind]
        # 3. "say it again"
        if self.pending is not None and ((ready and (settled or reading.kind != "dialogue"))
                                         or now - self.pending >= PRESS_TIMEOUT):
            chunks = n.plan(reading, repeat=True)
            if chunks and not self._voice_ready(chunks[0], now):
                return None
            asked, self.pending = self.pending, None
            self.spoken_sig = sig
            return self._start(chunks, reading, img, sig, now, asked)
        # 4. automatic reading
        auto = self.settings["auto_read"] == "on"
        if self.hold is not None:
            if sig == self.hold:
                return None       # the press stopped this screen: stay quiet
            self.hold = None      # something new (e.g. the box went on printing): read it
        if reading.kind == "dialogue":
            if not settled:
                n.prepare_printed_lines(reading)  # get line 1 ready while line 2 prints
                return None
            chunks = n.plan(reading, settled=True)
            if chunks and auto:
                if not self._voice_ready(chunks[0], now):
                    return None
                self.spoken_sig = sig
                return self._start(chunks, reading, img, sig, now)
            if chunks:
                n.prepare(chunks)
        elif ready and sig != self.spoken_sig:
            chunks = n.plan(reading)
            if reading.kind in ("other", "none"):
                chunks = [c for c in chunks if all(p[0] == "cue" for p in c)]  # just "menu closed"
            if auto:
                if chunks and not self._voice_ready(chunks[0], now):
                    return None
                self.spoken_sig = sig
                return self._start(chunks, reading, img, sig, now)
            if reading.kind in ("other", "none"):
                n.remember(reading)  # the menu closed: forget it
            n.prepare(n.plan(reading, repeat=True))  # ready for the button
        elif reading.kind == "menu":
            n.prepare(n.plan(reading))  # still settling: get its speech ready
        return None

    def _voice_ready(self, chunk, now):
        """False while the natural voice is still making this speech, for up to
        natural_wait seconds; then (or if it isn't working) the standard voice says it."""
        n = self.narrator
        if not n.waiting(chunk):
            return True
        if chunk != self.wait_chunk:
            self.wait_chunk, self.wait_since = chunk, now
            n.prepare([chunk])           # first in line
        return now - self.wait_since >= self.settings["natural_wait"]

    def _start(self, chunks, reading, img, sig, now, since=None):
        """Say the first chunk now, queue the rest. None = nothing to say.
        since: when the text was there to read (default: when the screen settled)."""
        self.narrator.remember(reading)
        if not chunks:
            return None
        self.queue = collections.deque(chunks[1:])
        self.queue_sig = sig
        self.narrator.prepare(chunks[1:])
        waited = now - self.wait_since if chunks[0] == self.wait_chunk else 0.0
        made = self.clock()
        reply = self._send(chunks[0], img, reading)
        done = self.clock()
        self.latency.append((done - (self.stable_since if since is None else since), waited, done - made))
        return reply

    def _send(self, chunk, img, reading):
        return self._send_wav(self.narrator.render(chunk), img, reading.flat())

    def _send_wav(self, wav, img, text, overlay=None):
        self.last_said = text
        # Measured *after* rendering: synthesis on the handheld can take a second or two.
        self.speaking_until = self.clock() + duration(wav)
        try:
            self.capture(img, text)
        except OSError as e:  # a full or read-only SD card must never stop the speech
            sys.stderr.write("urusai: capture failed: %r\n" % e)
        reply = {"sound": base64.b64encode(wav).decode("ascii"), "auto": "auto"}
        if overlay:
            reply["image"] = base64.b64encode(overlay).decode("ascii")
        return reply

    def keep_unread(self, img, now):
        """gba_learn: now and then keep a GBA screen nothing was read on, so
        letters or layouts the reader doesn't know yet can be added from it."""
        if self.settings["gba_learn"] == "on" and now - self.last_unread >= UNREAD_EVERY:
            self.last_unread = now
            try:
                self.capture(img, "(nothing read)")
            except OSError:
                pass

    def capture(self, img, text):
        """Keep the newest N spoken frames (+ what was read); oldest are deleted."""
        keep = self.settings["captures_keep"]
        if not self.capture_dir or keep <= 0:
            return
        os.makedirs(self.capture_dir, exist_ok=True)
        base = os.path.join(self.capture_dir, datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        with open(base + ".png", "wb") as f:
            f.write(pngdec.encode(img, level=1))
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text + "\n")
        shots = sorted(x[:-4] for x in os.listdir(self.capture_dir) if x.endswith(".png"))
        for old in shots[:-keep]:
            for ext in (".png", ".txt"):
                try:
                    os.unlink(os.path.join(self.capture_dir, old + ext))
                except OSError:
                    pass


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"status": "ok", "service": "pokemon-urusai", "version": __version__,
                        "tiles": len(app.font.table), "streaming": app.stream_alive()})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                resp = app.handle(body)
            except Exception as e:  # never break the stream on one bad frame
                sys.stderr.write("urusai: %r\n" % e)
                resp = {"error": "Urusai: %s" % e, "auto": "auto"}
            self._send(resp)

        def log_message(self, fmt, *args):
            if os.environ.get("URUSAI_VERBOSE"):
                sys.stderr.write("urusai: " + fmt % args + "\n")

    return Handler


# ---- pressing RetroArch's hotkey ----------------------------------------------
def retroarch_pids():
    pids = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open("/proc/%s/comm" % pid) as f:
                    if f.read().strip() in ("retroarch", "retroarch32"):
                        pids.append(int(pid))
            except OSError:
                pass
    return pids


class Starter:
    """Presses RetroArch's AI Service hotkey (F12+F10 on dArkOS, Shift+F10 on Knulli)
    through a virtual keyboard:
    to start the stream when a game starts or the button finds it stopped, and
    twice in a row to stop speech when a game button is pressed.

    The first key is RetroArch's hotkey enable (like holding Select), so it is only
    pressed once the player has let go of every button, with the pad
    grabbed meanwhile: otherwise a held A would become Select+A (pause)."""

    RELEASE_WAIT = 1.0   # give up on a cut if a button is still held this long

    def __init__(self, app, keys="f12+f10", log=sys.stderr):
        self.app, self.log = app, log
        self.kbd, self.status = None, "off"
        self.lock = threading.Lock()
        try:
            from .vkbd import VirtualKeyboard, key_codes
            self.kbd = VirtualKeyboard(key_codes(keys))
            self.status = "virtual keyboard ready (%s)" % keys
        except Exception as e:  # no /dev/uinput, no permission…
            self.status = "no virtual keyboard (%s) - start the reader by hand once" % e
        self.started_for = set()
        self.watcher = None          # set by main: knows which buttons are held
        self.keys = keys
        self.presses, self.last_press = 0, None   # for STATUS.txt

    def _press(self, *holds, wait=RELEASE_WAIT):
        """The key pair once per hold, never together with a held game button."""
        with self.lock:
            w = self.watcher
            if w and not w.wait_released(wait):
                return False
            with (w.grabbed() if w else contextlib.nullcontext()):
                for i, hold in enumerate(holds):
                    if i:
                        time.sleep(0.06)
                    self.kbd.chord(hold=hold)
            self.presses += 1
            self.last_press = datetime.datetime.now()
            return True

    def kick(self, why):
        if self.kbd and not self.app.stream_alive():
            self.log.write("urusai: starting the reader (%s)\n" % why)
            self._press(0.1, wait=30)

    def interrupt(self):
        """Hotkey twice: auto mode off, then a request right now."""
        if self.kbd and not self._press(0.06, 0.06):
            self.app.cut_abandoned()   # the button stayed down: let the clip finish

    def watch_games(self):
        seen = {}
        while True:
            time.sleep(2)
            if not self.kbd or self.app.settings["autostart"] != "on":
                continue
            now = time.monotonic()
            for pid in retroarch_pids():
                seen.setdefault(pid, now)
                if pid not in self.started_for and now - seen[pid] > 8:  # let the game load
                    self.started_for.add(pid)
                    self.kick("game started")


# Where RetroArch keeps the settings it actually runs with
RETROARCH_CFGS = ("/userdata/system/configs/retroarch/retroarchcustom.cfg",   # Knulli (rewritten each launch)
                  "/home/ark/.config/retroarch/retroarch.cfg", "/home/ark/.config/retroarch32/retroarch.cfg")
STATUS_EVERY = 5      # seconds


def retroarch_settings(path, keys):
    """{key: value} for these keys in a retroarch.cfg ({} if unreadable)."""
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                k, sep, v = line.partition("=")
                if sep and k.strip() in keys:
                    out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def retroarch_check(starter_keys, port, paths=RETROARCH_CFGS):
    """Lines saying whether RetroArch has the settings the reader needs."""
    enable_key, ai_key = (k.strip().lower() for k in starter_keys.split("+"))
    want = {"ai_service_enable": "true", "ai_service_mode": "1",
            "ai_service_url": "http://127.0.0.1:%d/" % port, "ai_service_pause": "false",
            "input_enable_hotkey": enable_key, "input_ai_service": ai_key}
    lines = []
    for path in paths:
        got = retroarch_settings(path, set(want) | {"audio_mute_enable"})
        if not got:
            continue
        wrong = ["%s = %s (should be %s)" % (k, got.get(k, "missing"), v) for k, v in want.items()
                 if got.get(k, "").lower() != v]
        if got.get("audio_mute_enable", "false").lower() == "true":
            wrong.append("audio_mute_enable = true (the game is muted)")
        lines.append("RetroArch settings in %s: %s" % (path, "all OK" if not wrong else "PROBLEM: " + "; ".join(wrong)))
    return lines or ["RetroArch settings: no retroarch.cfg found yet (start a game once)"]


def write_status(app, watcher, starter, port):
    """STATUS.txt in the captures folder: is the reader running, and is RetroArch talking to it?
    Rewritten every few seconds, so it always shows the current state."""
    if not app.capture_dir:
        return
    try:
        os.makedirs(app.capture_dir, exist_ok=True)
        n, s = app.narrator, app.settings
        now = app.clock()
        tmp = os.path.join(app.capture_dir, ".STATUS.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("Pokemon Urusai %s, started %s, updated %s\n" % (
                __version__, app.started, datetime.datetime.now().isoformat(timespec="seconds")))
            pids = retroarch_pids()
            f.write("RetroArch: %s\n" % ("running" if pids else "not running (start a game)"))
            if app.frames:
                f.write("screens received from RetroArch: %d, the last %d s ago%s\n" % (
                    app.frames, now - app.last_frame,
                    " (reading)" if app.stream_alive(now) else " (stopped: L2 or MENU+R1 starts it again)"))
            else:
                f.write("screens received from RetroArch: none yet%s\n" % (
                    " - the AI Service hasn't started (see 'starter' and 'RetroArch settings')" if pids else ""))
            f.write("last said: %s\n" % (app.last_said or "-"))
            f.write("reader: %s\n" % ("OFF (Select+L2 turns it on)" if app.muted else "on"))
            f.write("starter: %s; key presses so far: %d%s\n" % (
                starter.status if starter else "off", starter.presses if starter else 0,
                ", last at %s" % starter.last_press.isoformat(timespec="seconds") if starter and starter.last_press else ""))
            for line in retroarch_check(starter.keys if starter else "f12+f10", port):
                f.write(line + "\n")
            f.write("port %d, %d Game Boy tiles, %d GBA letter shapes, speech cache: %s\n"
                    % (port, len(app.font.table), len(app.gba_font), n.cache.dir or "memory only"))
            f.write("voices: %s (dialogue), %s %+g (menus), volume %d%%\n" % (
                os.path.basename(n.speaker.voice), os.path.basename(n.menu_speaker.voice),
                n.menu_speaker.pitch, n.speaker.volume))
            f.write("natural voice: %s\n" % (
                "in use (waits up to %g s for it, else %s)" % (s["natural_wait"], os.path.basename(n.speaker.hts))
                if n.speaker.neural
                else "not installed (standard voice used)" if tts.parse_voice(s["voice"])[0] == "tsukuyomi"
                else "not selected"))
            for line in natural_report(n):
                f.write(line + "\n")
            for line in latency_report(app.latency):
                f.write(line + "\n")
            f.write("auto read: %s, autostart: %s, interrupt: %s\n" % (s["auto_read"], s["autostart"], s["interrupt"]))
            f.write("button: %s, reader on/off: %s\n" % (watcher.status if watcher else "off", s["toggle_combo"]))
            f.write("settings: %s\n" % s.path)
        os.replace(tmp, os.path.join(app.capture_dir, "STATUS.txt"))
    except OSError as e:
        sys.stderr.write("urusai: cannot write status: %r\n" % e)


def natural_report(n):
    """STATUS.txt lines on how the natural voice is doing."""
    with n.lock:
        st = dict(n.stats)
    if not (st["made"] or st["failed"]):
        return [] if not n.speaker.neural else ["  nothing made with it yet"]
    lines = ["  lines made: %d, failed: %d; said in it: %d, in the standard voice: %d" % (
        st["made"], st["failed"], st["natural"], st["standard"])]
    if st["audio"]:
        lines.append("  time to make 1 s of speech: %.2f s; pace: %.1f syllables a second" % (
            st["seconds"] / st["audio"], st["morae"] / st["audio"]))
    if st["error"]:
        lines.append("  last error: %s" % st["error"])
    return lines


def latency_report(latency):
    """STATUS.txt line: how long text waits before it's heard."""
    if not latency:
        return []
    total = sorted(t for t, _, _ in latency)
    return ["delay from text on screen to speech (last %d): typical %.2f s, longest %.2f s;"
            " waiting for the natural voice %.2f s, making the sound %.2f s (averages)" % (
                len(total), total[len(total) // 2], total[-1],
                sum(w for _, w, _ in latency) / len(latency), sum(m for _, _, m in latency) / len(latency))]


def keep_status(app, watcher, starter, port):
    while True:
        time.sleep(STATUS_EVERY)
        write_status(app, watcher, starter, port)


def main(argv=None):
    p = argparse.ArgumentParser(description="Pokémon Urusai screen-reader server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4404)
    p.add_argument("--font", default=os.path.join(HERE, "font", "gb_jp.json"))
    p.add_argument("--settings", default=None, help="settings file (default /roms/urusai_settings.txt)")
    p.add_argument("--capture", default=os.environ.get("URUSAI_CAPTURE_DIR"),
                   help="keep recent spoken frames + readings here (for fixing misreads)")
    p.add_argument("--cache", default=os.path.join(HERE, "cache"), help="speech cache folder ('' = memory only)")
    p.add_argument("--no-input", action="store_true", help="don't watch the gamepad or press keys")
    p.add_argument("--keys", default="f12+f10", help="RetroArch's hotkey-enable + AI Service keys "
                   "(dArkOS: f12+f10, as the installer sets them; Knulli: shift+f10)")
    a = p.parse_args(argv)

    settings = Settings(a.settings)
    app = App(a.font, settings, a.capture, cache_dir=a.cache or None)
    app.narrator.warm_up()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(app))

    watcher = starter = None
    if not a.no_input:
        starter = Starter(app, a.keys)
        app.can_interrupt = starter.kbd is not None
        threading.Thread(target=starter.watch_games, daemon=True, name="urusai-autostart").start()

        def say_again():
            if app.press():
                starter.kick("button")

        def toggle():
            what = app.toggle()
            if what == "start":
                starter.kick("reader on/off")
            elif what == "cut":
                starter.interrupt()

        def game_input():  # runs in the watcher thread: don't block it
            if app.want_interrupt():
                threading.Thread(target=starter.interrupt, daemon=True).start()

        def current_button():
            settings.reload()
            return settings["button"]

        def combo():  # in the watcher thread: don't block it
            taps.cancel()           # L2 went down first: it wasn't "say it again"
            threading.Thread(target=toggle, daemon=True).start()

        def current_combo():
            return settings["toggle_combo"]

        taps = Taps(say_again, toggle)
        watcher = ButtonWatcher(current_button, taps.press, game_input,
                                get_combo=current_combo,
                                on_combo=combo)
        starter.watcher = watcher
        watcher.start()
        threading.Timer(4.0, write_status, (app, watcher, starter, a.port)).start()
    write_status(app, watcher, starter, a.port)
    threading.Thread(target=keep_status, args=(app, watcher, starter, a.port), daemon=True, name="urusai-status").start()
    sys.stderr.write("urusai %s: listening on http://%s:%d (%d tiles)\n"
                     % (__version__, a.host, a.port, len(app.font.table)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
