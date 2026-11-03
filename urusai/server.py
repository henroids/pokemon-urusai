"""RetroArch AI Service endpoint (VGTranslate-compatible), speech only, offline.

RetroArch POSTs {"image": <base64 PNG of the core frame>, ...} to
<url>?output=sound,wav and plays the base64 WAV we return under "sound".

We keep RetroArch in its "auto" mode: every reply carries "auto": "auto",
so RetroArch sends the next frame as soon as any speech has finished. That
stream lets us
  * read new dialogue and menu choices automatically,
  * prepare speech before it's needed (so it plays almost at once),
  * serve the "say it again" button on the next frame.
The stream starts with one press of RetroArch's AI Service hotkey; we press
it ourselves through a virtual keyboard when a game starts or L2 is pressed.

Run:  python3 -m urusai.server [--settings FILE] [--capture DIR]
"""
import argparse
import base64
import datetime
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, pngdec, reader, screen
from .button import ButtonWatcher
from .font import Font
from .settings import Settings
from .speech import RATE, Narrator
from .tts import HERE, Speaker

NO_TEXT = "No text found."
POLL = 0.15            # seconds between frames while nothing is said
STABLE_MENU = 0.2      # a menu must sit still this long before it's read
STABLE_TEXT = 0.6      # dialogue without ▼ must stop changing this long
PRESS_TIMEOUT = 1.5    # a press is served after this even if text still moves
STREAM_GAP = 1.2       # no frame for this long (and not speaking) = stream stopped


class App:
    def __init__(self, font_path, settings, capture_dir=None, speaker=None, menu_speaker=None,
                 clock=time.monotonic, sleep=time.sleep):
        self.font_path = font_path
        self.font = Font.load(font_path)
        self.font_mtime = self._mtime()
        self.settings = settings
        self.narrator = Narrator(speaker or Speaker(), menu_speaker or Speaker())
        self._apply_settings()
        self.capture_dir = capture_dir
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.last_frame = -1e9      # when RetroArch last sent a frame
        self.speaking_until = -1e9  # when the last speech we sent ends
        self.pending = None         # time of an unserved button press
        self.sig = None             # what's on screen now…
        self.stable_since = 0.0     # …and since when
        self.spoken_sig = None      # what we last read aloud

    # ---- state ----------------------------------------------------------
    def _mtime(self):
        try:
            return os.path.getmtime(self.font_path)
        except OSError:
            return 0

    def _apply_settings(self):
        s = self.settings
        n = self.narrator
        n.speaker.configure(s["voice"], s["speed"], s["volume"])
        n.menu_speaker.configure(s["menu_voice"], s["speed"], s["volume"])

    def refresh(self):
        """Pick up edits to the font or the settings file."""
        m = self._mtime()
        if m != self.font_mtime:
            self.font, self.font_mtime = Font.load(self.font_path), m
        if self.settings.reload():
            self._apply_settings()

    def stream_alive(self, now=None):
        now = self.clock() if now is None else now
        return now - self.last_frame < STREAM_GAP or now < self.speaking_until + 0.5

    def press(self):
        """The 'say it again' button. Returns True if the stream must be (re)started."""
        with self.lock:
            self.pending = self.clock()
            return not self.stream_alive()

    # ---- one frame from RetroArch ------------------------------------------
    def handle(self, body, query):
        req = json.loads(body.decode("utf-8"))
        img = screen.to_gb_frame(pngdec.decode(base64.b64decode(req["image"])))
        with self.lock:
            now = self.clock()
            fresh = not self.stream_alive(now)  # someone just pressed the AI Service hotkey
            self.last_frame = now
            self.refresh()
            reading = reader.analyze_image(self.font, img)
            sig = (reading.flat(), tuple(reading.options), reading.selected, tuple(reading.other))
            if sig != self.sig:
                self.sig, self.stable_since = sig, now
            stable = now - self.stable_since
            if fresh:
                self.pending = self.pending or now
                self.narrator.reset()

            ready = {"menu": stable >= STABLE_MENU,
                     "dialogue": reading.more or stable >= STABLE_TEXT,
                     "other": stable >= STABLE_MENU}.get(reading.kind, False)
            if self.pending is not None and (ready or now - self.pending >= PRESS_TIMEOUT or reading.kind == "none"):
                self.pending = None
                return self._say(reading, sig, img, now, repeat=True, fresh=fresh)
            if (self.settings["auto_read"] == "on" and ready and sig != self.spoken_sig
                    and reading.kind in ("menu", "dialogue")):
                return self._say(reading, sig, img, now, repeat=False, fresh=fresh)
            if ready and sig != self.spoken_sig:
                self.narrator.prepare(self.narrator.plan(reading))
        if not fresh:
            self.sleep(POLL)  # pace the stream while nothing is said
        return {"auto": "auto"} if not fresh else {"error": NO_TEXT, "auto": "auto"}

    def _say(self, reading, sig, img, now, repeat, fresh):
        pieces = self.narrator.plan(reading, repeat=repeat)
        self.spoken_sig = sig
        if not pieces:
            return {"error": NO_TEXT, "auto": "auto"} if fresh else {"auto": "auto"}
        wav = self.narrator.render(pieces)
        self.narrator.remember(reading)
        self.speaking_until = now + (len(wav) - 44) / (2.0 * RATE)
        try:
            self.capture(img, reading.flat())
        except OSError as e:  # a full or read-only SD card must never stop the speech
            sys.stderr.write("urusai: capture failed: %r\n" % e)
        return {"sound": base64.b64encode(wav).decode("ascii"), "auto": "auto"}

    def capture(self, img, text):
        """Keep the newest N spoken frames (+ what was read); oldest are deleted."""
        keep = self.settings["captures_keep"]
        if not self.capture_dir or keep <= 0:
            return
        os.makedirs(self.capture_dir, exist_ok=True)
        base = os.path.join(self.capture_dir, datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        with open(base + ".png", "wb") as f:
            f.write(pngdec.encode(img))
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
                resp = app.handle(body, parse_qs(urlparse(self.path).query))
            except Exception as e:  # never break the stream on one bad frame
                sys.stderr.write("urusai: %r\n" % e)
                resp = {"error": "Urusai: %s" % e, "auto": "auto"}
            self._send(resp)

        def log_message(self, fmt, *args):
            if os.environ.get("URUSAI_VERBOSE"):
                sys.stderr.write("urusai: " + fmt % args + "\n")

    return Handler


# ---- starting the stream ----------------------------------------------------
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
    """Presses RetroArch's AI Service hotkey (F8+F6) through a virtual keyboard:
    once when a game starts (if autostart is on) and when L2 finds the stream stopped."""

    def __init__(self, app, log=sys.stderr):
        self.app, self.log = app, log
        self.kbd, self.status = None, "off"
        try:
            from .vkbd import VirtualKeyboard
            self.kbd = VirtualKeyboard()
            self.status = "virtual keyboard ready"
        except Exception as e:  # no /dev/uinput, no permission…
            self.status = "no virtual keyboard (%s) - press Select+Y once to start" % e
        self.started_for = set()

    def kick(self, why):
        if self.kbd and not self.app.stream_alive():
            self.log.write("urusai: starting the reader (%s)\n" % why)
            self.kbd.chord()

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


def write_status(app, watcher, starter, port):
    """A breadcrumb in the captures folder so you can see the reader is running."""
    if not app.capture_dir:
        return
    try:
        os.makedirs(app.capture_dir, exist_ok=True)
        n = app.narrator
        with open(os.path.join(app.capture_dir, "STATUS.txt"), "w", encoding="utf-8") as f:
            f.write("Pokemon Urusai %s, started %s\n" % (__version__, datetime.datetime.now().isoformat(timespec="seconds")))
            f.write("port %d, %d font tiles\n" % (port, len(app.font.table)))
            f.write("voices: %s (dialogue), %s (menus), volume %d%%\n" % (
                os.path.basename(n.speaker.voice), os.path.basename(n.menu_speaker.voice), n.speaker.volume))
            f.write("auto read: %s, autostart: %s\n" % (app.settings["auto_read"], app.settings["autostart"]))
            f.write("button: %s\n" % (watcher.status if watcher else "off"))
            f.write("starter: %s\n" % (starter.status if starter else "off"))
            f.write("settings: %s\n" % app.settings.path)
    except OSError as e:
        sys.stderr.write("urusai: cannot write status: %r\n" % e)


def main(argv=None):
    p = argparse.ArgumentParser(description="Pokémon Urusai screen-reader server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4404)
    p.add_argument("--font", default=os.path.join(HERE, "font", "gen1_jp.json"))
    p.add_argument("--settings", default=None, help="settings file (default /roms/urusai_settings.txt)")
    p.add_argument("--capture", default=os.environ.get("URUSAI_CAPTURE_DIR"),
                   help="keep recent spoken frames + readings here (for fixing misreads)")
    p.add_argument("--no-input", action="store_true", help="don't watch the gamepad or press keys")
    a = p.parse_args(argv)

    settings = Settings(a.settings)
    app = App(a.font, settings, a.capture)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(app))

    watcher = starter = None
    if not a.no_input:
        starter = Starter(app)
        threading.Thread(target=starter.watch_games, daemon=True, name="urusai-autostart").start()

        def on_button():
            if app.press():
                starter.kick("button")

        def current_button():
            settings.reload()
            return settings["button"]

        watcher = ButtonWatcher(current_button, on_button)
        watcher.start()
        threading.Timer(4.0, write_status, (app, watcher, starter, a.port)).start()
    write_status(app, watcher, starter, a.port)
    sys.stderr.write("urusai %s: listening on http://%s:%d (%d tiles)\n"
                     % (__version__, a.host, a.port, len(app.font.table)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
