"""A more natural voice: piper-plus (a small neural voice model), kept running.

piper-plus is started once per voice and fed one line at a time, so the
model is loaded only once. It is much slower than Open JTalk on a handheld
(about as long to make a line as to say it), so speech.Narrator only uses
it for clips it has had time to make, and says everything else with the
quick voice meanwhile.

Files (the installer puts them in place):
  neural/<machine>/bin/piper-plus, neural/<machine>/lib/   the program and ONNX Runtime
  neural/model/**/*<name>*.onnx  (+ .onnx.json or config.json)  the voice
"""
import glob
import json
import os
import platform
import select
import subprocess
import tempfile
import threading
from collections import OrderedDict

from . import audio
from .sounds import RATE, to_wav, wav_samples_rate

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("URUSAI_NEURAL", os.path.join(HERE, "neural"))
SCRATCH = "/dev/shm" if os.path.isdir("/dev/shm") else None
START_TIMEOUT = 90     # seconds for the first line (the model loads from the SD card)
LINE_TIMEOUT = 45
THREADS = "3"          # of the handheld's four cores; the game keeps one
NICE = 10              # …and goes first whenever both want the processor


def find_binary():
    exe = os.environ.get("URUSAI_PIPER", os.path.join(ROOT, platform.machine(), "bin", "piper-plus"))
    return exe if os.path.isfile(exe) else None


def find_model(name):
    """The .onnx of a neural voice called name (e.g. 'tsukuyomi'), or None."""
    if not find_binary():
        return None
    hits = sorted(glob.glob(os.path.join(ROOT, "model", "**", "*%s*.onnx" % glob.escape(name)), recursive=True))
    return hits[0] if hits else None


def find_config(model):
    for path in (model + ".json", os.path.join(os.path.dirname(model), "config.json")):
        if os.path.isfile(path):
            return path
    return None


class Engine:
    """One running piper-plus: text in, 16-bit samples at RATE out."""

    def __init__(self, model, length_scale, dic):
        self.model, self.length_scale, self.dic = model, length_scale, dic
        self.proc = None
        self.lock = threading.Lock()

    def _start(self):
        exe = find_binary()
        env = dict(os.environ, OPENJTALK_DICTIONARY_PATH=self.dic, PIPER_PLUS_INTRA_THREADS=THREADS,
                   PIPER_PLUS_DISABLE_MODEL_NOTICE="1", PIPER_PLUS_AUTO_DOWNLOAD_DICT="0",
                   LD_LIBRARY_PATH=os.path.join(os.path.dirname(os.path.dirname(exe)), "lib"))
        cmd = [exe, "-q", "-m", self.model, "-l", "ja", "--json-input",
               "--length_scale", "%.3f" % self.length_scale, "--sentence_silence", "0"]
        config = find_config(self.model)
        if config:
            cmd += ["-c", config]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env=env, preexec_fn=lambda: os.nice(NICE))
        return START_TIMEOUT

    def stop(self):
        with self.lock:
            self._kill()

    def _kill(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc.stdin.close()
            self.proc.stdout.close()
            self.proc = None

    def samples(self, text, rate_factor=1.0):
        """Speak text. rate_factor plays it back faster (>1, higher) or slower (<1, lower)."""
        fd, out = tempfile.mkstemp(suffix=".wav", dir=SCRATCH)
        os.close(fd)
        with self.lock:
            try:
                timeout = LINE_TIMEOUT if self.proc and self.proc.poll() is None else self._start()
                line = json.dumps({"text": text, "output_file": out}, ensure_ascii=False) + "\n"
                self.proc.stdin.write(line.encode("utf-8"))
                self.proc.stdin.flush()
                if not select.select([self.proc.stdout], [], [], timeout)[0] or not self.proc.stdout.readline():
                    raise RuntimeError("piper-plus gave no answer")
                with open(out, "rb") as f:
                    samples, rate = wav_samples_rate(f.read())
            except Exception:
                self._kill()   # start afresh next time
                raise
            finally:
                if os.path.exists(out):
                    os.unlink(out)
        return audio.resample(samples, int(round(rate * rate_factor / 50.0)) * 50, RATE)


MAX_ENGINES = 2        # dialogue and menu voice; each is a model in memory
_engines = OrderedDict()
_engines_lock = threading.Lock()


def engine(model, length_scale, dic):
    """The shared Engine for this voice and tempo; the least recently used one
    is stopped when a setting change calls for a third."""
    key = (model, round(length_scale, 3))
    with _engines_lock:
        if key not in _engines:
            while len(_engines) >= MAX_ENGINES:
                _engines.popitem(last=False)[1].stop()
            _engines[key] = Engine(model, key[1], dic)
        _engines.move_to_end(key)
        return _engines[key]


def wav(model, dic, text, speed, pitch):
    """WAV bytes (RATE) of text in a neural voice; pitch in semitones."""
    factor = 2.0 ** (pitch / 12.0)
    # Playing faster raises the pitch and shortens the clip, so the model speaks slower by as much.
    scale = factor / speed
    return to_wav(engine(model, scale, dic).samples(text, factor))
