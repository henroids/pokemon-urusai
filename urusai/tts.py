"""Offline Japanese speech with Open JTalk (returns WAV bytes)."""
import glob
import os
import platform
import subprocess
import tempfile

from . import audio

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICE_DIR = os.path.join(HERE, "voice")
SYNTH_GAIN_DB = -3.0     # synthesise with headroom; audio.louder() levels and boosts


def _first(paths):
    for p in paths:
        for hit in sorted(glob.glob(p)) if p else []:
            return hit
    return None


def find_binary():
    return _first([os.environ.get("URUSAI_OPEN_JTALK", ""),
                   os.path.join(HERE, "bin", "open_jtalk-" + platform.machine()),
                   "/usr/bin/open_jtalk", "/usr/local/bin/open_jtalk"])


def find_dict():
    return _first([os.environ.get("URUSAI_DICT", ""),
                   os.path.join(HERE, "dic"),
                   "/var/lib/mecab/dic/open-jtalk/naist-jdic"])


def voices():
    """Names of the bundled voices, e.g. ['mei', 'mei_happy', 'nitech', 'tohoku', …]."""
    return sorted(os.path.basename(p)[:-9] for p in glob.glob(os.path.join(VOICE_DIR, "*.htsvoice")))


def find_voice(name):
    """voice/<name>.htsvoice, else any bundled voice, else a system one."""
    return _first([os.environ.get("URUSAI_VOICE", ""),
                   os.path.join(VOICE_DIR, "%s.htsvoice" % name),
                   os.path.join(VOICE_DIR, "*.htsvoice"),
                   "/usr/share/hts-voice/*/*.htsvoice"])


class Speaker:
    def __init__(self, voice="tohoku", speed=0.95, volume=200):
        self.binary = find_binary()
        self.dic = find_dict()
        self.configure(voice, speed, volume)
        missing = [n for n, v in (("open_jtalk", self.binary), ("dictionary", self.dic),
                                  ("voice", self.voice)) if not v]
        if missing:
            raise RuntimeError("missing: " + ", ".join(missing))

    def configure(self, voice, speed, volume):
        self.voice = find_voice(voice)
        self.speed = min(2.0, max(0.5, float(speed)))
        self.volume = min(400, max(0, int(volume)))

    def wav(self, text):
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            cmd = [self.binary, "-x", self.dic, "-m", self.voice, "-ow", out,
                   "-r", str(self.speed), "-g", str(SYNTH_GAIN_DB)]
            subprocess.run(cmd, input=text.encode("utf-8"), check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            with open(out, "rb") as f:
                raw = f.read()
        finally:
            os.unlink(out)
        return audio.louder(raw, self.volume, level=True)  # every voice equally loud
