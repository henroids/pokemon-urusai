"""Offline Japanese speech with Open JTalk (returns WAV bytes)."""
import glob
import os
import platform
import subprocess
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _first(paths):
    for p in paths:
        for hit in sorted(glob.glob(p)):
            if os.path.exists(hit):
                return hit
    return None


def find_binary():
    arch = platform.machine()
    return _first([os.environ.get("URUSAI_OPEN_JTALK", ""),
                   os.path.join(HERE, "bin", "open_jtalk-" + arch),
                   "/usr/bin/open_jtalk", "/usr/local/bin/open_jtalk"])


def find_dict():
    return _first([os.environ.get("URUSAI_DICT", ""),
                   os.path.join(HERE, "dic"),
                   "/var/lib/mecab/dic/open-jtalk/naist-jdic"])


def find_voice():
    # A voice dropped into voice/ wins (e.g. mei_normal.htsvoice); then system voices.
    return _first([os.environ.get("URUSAI_VOICE", ""),
                   os.path.join(HERE, "voice", "mei*.htsvoice"),
                   os.path.join(HERE, "voice", "*.htsvoice"),
                   "/usr/share/hts-voice/*/*.htsvoice"])


class Speaker:
    def __init__(self, speed=0.95, volume_db=6.0, half_tone=0.0):
        self.binary = find_binary()
        self.dic = find_dict()
        self.voice = find_voice()
        missing = [n for n, v in (("open_jtalk", self.binary), ("dictionary", self.dic),
                                  ("voice", self.voice)) if not v]
        if missing:
            raise RuntimeError("missing: " + ", ".join(missing))
        self.speed, self.volume_db, self.half_tone = speed, volume_db, half_tone

    def wav(self, text):
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            cmd = [self.binary, "-x", self.dic, "-m", self.voice, "-ow", out,
                   "-r", str(self.speed), "-g", str(self.volume_db), "-fm", str(self.half_tone)]
            subprocess.run(cmd, input=text.encode("utf-8"), check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            with open(out, "rb") as f:
                return f.read()
        finally:
            os.unlink(out)
