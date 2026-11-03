"""RetroArch AI Service endpoint (VGTranslate-compatible), speech only, offline.

RetroArch POSTs {"image": <base64 PNG of the core frame>, "label": ..., "state": {...}}
to  <url>?source_lang=ja&target_lang=ja&output=sound,wav  and, in Speech mode,
plays the base64 WAV we return under "sound".

Run:  python3 -m urusai.server [--port 4404] [--capture DIR]
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

from . import normalize, pngdec, reader, screen
from .font import Font
from .tts import HERE, Speaker

NO_TEXT = "No text found."


class App:
    def __init__(self, font_path, capture_dir=None, capture_keep=300, speaker=None):
        self.font_path = font_path
        self.font = Font.load(font_path)
        self.font_mtime = self._mtime()
        self.speaker = speaker or Speaker()
        self.capture_dir = capture_dir
        self.capture_keep = capture_keep
        self.lock = threading.Lock()
        self.last = (None, None)  # (text, wav)

    def _mtime(self):
        try:
            return os.path.getmtime(self.font_path)
        except OSError:
            return 0

    def _reload_font_if_changed(self):
        m = self._mtime()
        if m != self.font_mtime:
            self.font = Font.load(self.font_path)
            self.font_mtime = m

    def handle(self, body, query):
        outputs = set()
        for v in query.get("output", ["sound,wav"]):
            outputs.update(v.split(","))
        req = json.loads(body.decode("utf-8"))
        png = base64.b64decode(req["image"])
        img = screen.to_gb_frame(pngdec.decode(png))
        with self.lock:
            self._reload_font_if_changed()
            text = reader.read_image(self.font, img)
            spoken = normalize.for_speech(text)
            try:
                self._capture(img, text)
            except OSError as e:  # never let a full/read-only SD card stop the speech
                sys.stderr.write("urusai: capture failed: %r\n" % e)
            if not spoken:
                return {"error": NO_TEXT}
            resp = {}
            if "text" in outputs:
                resp["text"] = text
            if "sound" in outputs or "wav" in outputs or not outputs - {"image", "png", "png-a"}:
                if self.last[0] == spoken:
                    wav = self.last[1]
                else:
                    wav = self.speaker.wav(spoken)
                    self.last = (spoken, wav)
                resp["sound"] = base64.b64encode(wav).decode("ascii")
            return resp or {"text": text}

    def _capture(self, img, text):
        if not self.capture_dir:
            return
        os.makedirs(self.capture_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        base = os.path.join(self.capture_dir, stamp)
        with open(base + ".png", "wb") as f:
            f.write(pngdec.encode(img))
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text + "\n")
        files = sorted(os.listdir(self.capture_dir))
        pngs = [x for x in files if x.endswith(".png")]
        for old in pngs[:-self.capture_keep] if self.capture_keep else []:
            for ext in (".png", ".txt"):
                try:
                    os.unlink(os.path.join(self.capture_dir, old[:-4] + ext))
                except OSError:
                    pass


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"status": "ok", "service": "pokemon-urusai", "tiles": len(app.font.table)})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
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


def main(argv=None):
    p = argparse.ArgumentParser(description="Pokémon Urusai screen-reader server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4404)
    p.add_argument("--font", default=os.path.join(HERE, "font", "gen1_jp.json"))
    p.add_argument("--capture", default=os.environ.get("URUSAI_CAPTURE_DIR"),
                   help="save every received frame + its reading here (for building the font)")
    p.add_argument("--speed", type=float, default=0.95)
    a = p.parse_args(argv)
    app = App(a.font, a.capture, speaker=Speaker(speed=a.speed))
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(app))
    if a.capture:  # a breadcrumb on the SD card so you can see the reader is running
        try:
            os.makedirs(a.capture, exist_ok=True)
            with open(os.path.join(a.capture, "STATUS.txt"), "w", encoding="utf-8") as f:
                f.write("Pokemon Urusai %s started %s\nport %d, %d font tiles, voice %s\n" % (
                    __import__("urusai").__version__, datetime.datetime.now().isoformat(timespec="seconds"),
                    a.port, len(app.font.table), os.path.basename(app.speaker.voice)))
        except OSError as e:
            sys.stderr.write("urusai: cannot write status: %r\n" % e)
    sys.stderr.write("urusai: listening on http://%s:%d (%d tiles, voice %s)\n"
                     % (a.host, a.port, len(app.font.table), os.path.basename(app.speaker.voice)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
