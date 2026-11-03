"""Offline Japanese speech with Open JTalk (returns WAV bytes)."""
import glob
import os
import platform
import re
import subprocess
import tempfile

from . import audio, normalize

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


def parse_voice(spec):
    """'mei+3' -> ('mei', 3.0): a voice name plus a pitch shift in semitones."""
    m = re.match(r"^\s*([A-Za-z0-9_\-]+?)\s*(?:([+-]\s*\d+(?:\.\d+)?))?\s*$", str(spec))
    if not m:
        return str(spec).strip(), 0.0
    return m.group(1), float(m.group(2).replace(" ", "")) if m.group(2) else 0.0


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
        """voice may carry a pitch shift in semitones, e.g. 'mei+3' or 'tohoku-4'."""
        name, pitch = parse_voice(voice)
        self.voice = find_voice(name)
        self.pitch = max(-12.0, min(12.0, pitch))
        self.speed = min(2.0, max(0.5, float(speed)))
        self.volume = min(400, max(0, int(volume)))

    def wav(self, text, particles=()):
        """Speak text. particles: indices of は/へ that must sound wa/e; if Open JTalk
        read one differently, it's spelled わ/え and synthesised again."""
        raw, tokens = self._synth(text, analyse=bool(particles))
        wrong = misread_particles(text, tokens, particles) if particles else []
        if wrong:
            fixed = list(text)
            for i in wrong:
                fixed[i] = {"は": "わ", "へ": "え"}[text[i]]
            raw, _ = self._synth("".join(fixed), analyse=False)
        return audio.louder(raw, self.volume, level=True)  # every voice equally loud

    def _synth(self, text, analyse):
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        trace = out[:-4] + ".trace"
        try:
            cmd = [self.binary, "-x", self.dic, "-m", self.voice, "-ow", out,
                   "-r", str(self.speed), "-g", str(SYNTH_GAIN_DB), "-fm", str(self.pitch)]
            if analyse:
                cmd += ["-ot", trace]
            subprocess.run(cmd, input=text.encode("utf-8"), check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            with open(out, "rb") as f:
                raw = f.read()
            tokens = parse_trace(trace) if analyse else []
        finally:
            for p in (out, trace):
                if os.path.exists(p):
                    os.unlink(p)
        return raw, tokens


def parse_trace(path):
    """[(surface, part of speech, pronunciation)] from Open JTalk's -ot output."""
    tokens, inside = [], False
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("[Text analysis result]"):
                inside = True
            elif inside:
                if not line.strip():
                    break
                fields = line.rstrip("\n").split(",")
                if len(fields) > 9:
                    tokens.append((fields[0], fields[1], fields[9]))
    return tokens


def misread_particles(text, tokens, particles):
    """Indices in particles that Open JTalk didn't pronounce as wa/e."""
    if "".join(t[0] for t in tokens) != text:  # its normalisation changed the text: can't map
        return []
    wrong, pos = [], 0
    for surface, pos_tag, pron in tokens:
        for i in particles:
            if pos <= i < pos + len(surface):
                want = normalize.PARTICLES[text[i]]
                ok = pron == want if len(surface) == 1 else pron.endswith(want) and i == pos + len(surface) - 1
                if not ok and pos_tag not in ("フィラー",):
                    wrong.append(i)
        pos += len(surface)
    return wrong
