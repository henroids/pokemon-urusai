"""RetroArch AI Service endpoint (VGTranslate-compatible), speech only, offline.

RetroArch POSTs {"image": <base64 PNG of the core frame>, ...} to
<url>?output=sound,wav and, in Speech mode, plays the base64 WAV we return
under "sound". A button watcher lets a single gamepad button trigger it.

Run:  python3 -m urusai.server [--settings FILE] [--capture DIR]
"""
import argparse
import base64
import datetime
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, normalize, pngdec, reader, screen
from .button import ButtonWatcher, retroarch_command
from .font import Font
from .settings import Settings
from .tts import HERE, Speaker

NO_TEXT = "No text found."


class App:
    def __init__(self, font_path, settings, capture_dir=None, speaker=None):
        self.font_path = font_path
        self.font = Font.load(font_path)
        self.font_mtime = self._mtime()
        self.settings = settings
        self.speaker = speaker or Speaker()
        self._apply_settings()
        self.capture_dir = capture_dir
        self.lock = threading.Lock()
        self.last = (None, None)  # (spoken text, wav) — repeat presses are instant

    def _mtime(self):
        try:
            return os.path.getmtime(self.font_path)
        except OSError:
            return 0

    def _apply_settings(self):
        s = self.settings
        self.speaker.configure(s["voice"], s["speed"], s["volume"])
        self.last = (None, None)

    def refresh(self):
        """Pick up edits to the font or the settings file."""
        m = self._mtime()
        if m != self.font_mtime:
            self.font, self.font_mtime = Font.load(self.font_path), m
        if self.settings.reload():
            self._apply_settings()

    def handle(self, body, query):
        outputs = set()
        for v in query.get("output", ["sound,wav"]):
            outputs.update(v.split(","))
        req = json.loads(body.decode("utf-8"))
        img = screen.to_gb_frame(pngdec.decode(base64.b64decode(req["image"])))
        with self.lock:
            self.refresh()
            text = reader.read_image(self.font, img)
            spoken = normalize.for_speech(text)
            try:
                self.capture(img, text)
            except OSError as e:  # a full or read-only SD card must never stop the speech
                sys.stderr.write("urusai: capture failed: %r\n" % e)
            if not spoken:
                return {"error": NO_TEXT}
            resp = {}
            if "text" in outputs:
                resp["text"] = text
            if outputs & {"sound", "wav"} or not outputs - {"image", "png", "png-a"}:
                if self.last[0] != spoken:
                    self.last = (spoken, self.speaker.wav(spoken))
                resp["sound"] = base64.b64encode(self.last[1]).decode("ascii")
            return resp or {"text": text}

    def capture(self, img, text):
        """Keep the newest N frames (+ what was read) for fixing misreads; oldest are deleted."""
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
                        "tiles": len(app.font.table)})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                resp = app.handle(body, parse_qs(urlparse(self.path).query))
            except Exception as e:  # never crash the service on one bad frame
                sys.stderr.write("urusai: %r\n" % e)
                resp = {"error": "Urusai: %s" % e}
            self._send(resp)

        def log_message(self, fmt, *args):
            if os.environ.get("URUSAI_VERBOSE"):
                sys.stderr.write("urusai: " + fmt % args + "\n")

    return Handler


def write_status(app, watcher, port):
    """A breadcrumb in the captures folder so you can see the reader is running."""
    if not app.capture_dir:
        return
    try:
        os.makedirs(app.capture_dir, exist_ok=True)
        with open(os.path.join(app.capture_dir, "STATUS.txt"), "w", encoding="utf-8") as f:
            f.write("Pokemon Urusai %s, started %s\n" % (__version__, datetime.datetime.now().isoformat(timespec="seconds")))
            f.write("port %d, %d font tiles, voice %s, volume %d%%\n" % (
                port, len(app.font.table), os.path.basename(app.speaker.voice), app.speaker.volume))
            f.write("button: %s\nsettings: %s\n" % (watcher.status if watcher else "off", app.settings.path))
    except OSError as e:
        sys.stderr.write("urusai: cannot write status: %r\n" % e)


def main(argv=None):
    p = argparse.ArgumentParser(description="Pokémon Urusai screen-reader server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4404)
    p.add_argument("--font", default=os.path.join(HERE, "font", "gen1_jp.json"))
    p.add_argument("--settings", default=None, help="settings file (default /roms/urusai_settings.txt)")
    p.add_argument("--capture", default=os.environ.get("URUSAI_CAPTURE_DIR"),
                   help="keep recent frames + readings here (for fixing misreads)")
    p.add_argument("--no-button", action="store_true", help="don't watch the gamepad")
    a = p.parse_args(argv)

    settings = Settings(a.settings)
    app = App(a.font, settings, a.capture)
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(app))

    watcher = None
    if not a.no_button:
        def press():
            retroarch_command("AI_SERVICE", settings["retroarch_port"])

        def current_button():
            settings.reload()
            return settings["button"]

        watcher = ButtonWatcher(current_button, press)
        watcher.start()
        threading.Timer(4.0, write_status, (app, watcher, a.port)).start()  # after the watcher settles
    write_status(app, watcher, a.port)
    sys.stderr.write("urusai %s: listening on http://%s:%d (%d tiles, voice %s)\n"
                     % (__version__, a.host, a.port, len(app.font.table), os.path.basename(app.speaker.voice)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
