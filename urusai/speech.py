"""Decide what to say for a screen, and say it quickly.

  * Dialogue: when the box scrolls up one line, only the new line is read.
  * Menus: the question (dialogue voice), then every option in the menu
    voice with a chime ("biiing-booong") right after the selected one. Moving the cursor in the
    same menu says just the new choice.
  * Speech is synthesised in the background as soon as text appears, so a
    request usually finds it ready (cache keyed by voice + text).
"""
import array
import io
import math
import threading
import wave
from collections import OrderedDict

from . import normalize

RATE = 48000
MAX_OPTIONS = 12  # bigger "menus" (the name grid) just say the selection


def _wav_samples(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return array.array("h", w.readframes(w.getnframes()))


def trim(samples, threshold=500, lead_ms=50, tail_ms=80):
    """Cut Open JTalk's ~0.4 s lead-in and ~0.6 s tail of silence."""
    start = next((i for i, x in enumerate(samples) if abs(x) > threshold), None)
    if start is None:
        return array.array("h")
    end = len(samples) - next(i for i, x in enumerate(reversed(samples)) if abs(x) > threshold)
    lo = max(0, start - RATE * lead_ms // 1000)
    hi = min(len(samples), end + RATE * tail_ms // 1000)
    return samples[lo:hi]


def silence(ms):
    return array.array("h", bytes(2 * (RATE * ms // 1000)))


def chime(notes=((1318.5, 0.0), (1046.5, 0.30)), length=0.85, level=8000):
    """A soft two-note bell, "biiing-booong" (E6 then C6), marking the selection.
    Each note has a quick attack, a long decay and a quieter octave overtone."""
    n = int(RATE * length)
    out = [0.0] * n
    for freq, start in notes:
        s0 = int(RATE * start)
        for i in range(n - s0):
            t = i / RATE
            env = min(1.0, t / 0.004) * math.exp(-t * 5.0)
            out[s0 + i] += env * (math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t))
    peak = max(abs(x) for x in out) or 1.0
    return array.array("h", (int(level * x / peak) for x in out))


_CHIME = None


def beep():
    """The selection marker (cached: it's the same every time)."""
    global _CHIME
    if _CHIME is None:
        _CHIME = chime()
    return _CHIME


def to_wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def new_lines(lines, spoken):
    """Lines not yet read: if the box scrolled (its first lines are the
    last ones we read), keep only what's new. Same box again -> all of it."""
    for k in range(min(len(lines) - 1, len(spoken)), 0, -1):
        if lines[:k] == spoken[-k:]:
            return lines[k:]
    return lines


class Narrator:
    """Plans utterances and renders them with two Speakers (dialogue, menu)."""

    def __init__(self, speaker, menu_speaker=None, cache_size=64):
        self.speaker = speaker
        self.menu_speaker = menu_speaker or speaker
        self.cache = OrderedDict()
        self.cache_size = cache_size
        self.lock = threading.Lock()
        self.wanted = []  # pieces to prepare in the background (newest first)
        self.wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True, name="urusai-tts").start()
        self.reset()

    def reset(self):
        self.spoken_dialogue = []   # dialogue lines we last read
        self.spoken_menu = None     # (options tuple) we last read in full

    # ---- planning -------------------------------------------------------
    def plan(self, reading, repeat=False):
        """Pieces to say for this reading: ('talk'|'menu', text) or ('beep',).
        repeat=True reads everything again (the "say it again" button)."""
        pieces = []
        dialogue = reading.dialogue
        if reading.kind == "menu":
            opts = tuple(reading.options)
            same_menu = not repeat and opts == self.spoken_menu
            if dialogue and (repeat or dialogue != self.spoken_dialogue):
                pieces.append(("talk", " ".join(dialogue)))
            if len(opts) > MAX_OPTIONS or len(opts) == 1:
                pieces.append(("menu", reading.selected_text))
            elif same_menu:
                pieces.append(("menu", reading.selected_text))
            else:
                for i, opt in enumerate(opts):
                    pieces.append(("menu", opt))
                    if i == reading.selected:
                        pieces.append(("beep",))
        elif reading.kind == "dialogue":
            lines = dialogue if repeat else new_lines(dialogue, self.spoken_dialogue)
            pieces.append(("talk", " ".join(lines)))
        elif reading.kind == "other":
            pieces.append(("talk", " ".join(reading.other)))
        return [p for p in pieces if p[0] == "beep" or normalize.for_speech(p[1])]

    def remember(self, reading):
        """Call after speaking a reading, so the next plan knows what was said."""
        if reading.dialogue:
            self.spoken_dialogue = list(reading.dialogue)
        self.spoken_menu = tuple(reading.options) if reading.kind == "menu" else None

    # ---- rendering ------------------------------------------------------
    def _speaker(self, kind):
        return self.menu_speaker if kind == "menu" else self.speaker

    def _key(self, piece):
        sp = self._speaker(piece[0])
        return (sp.voice, sp.speed, sp.volume, normalize.for_speech(piece[1]))

    def _synth(self, piece):
        key = self._key(piece)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        samples = trim(_wav_samples(self._speaker(piece[0]).wav(key[3])))
        with self.lock:
            self.cache[key] = samples
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
        return samples

    def render(self, pieces):
        """WAV bytes for a plan (uses the cache, synthesises what's missing)."""
        out = array.array("h")
        for i, piece in enumerate(pieces):
            if piece[0] == "beep":
                out += silence(60) + beep()  # the chime's own tail is the pause after it
                continue
            out += self._synth(piece)
            if i + 1 < len(pieces) and pieces[i + 1][0] != "beep":
                out += silence(180)
        return to_wav(out)

    def prepare(self, pieces):
        """Synthesise these pieces in the background (latest request first)."""
        todo = [p for p in pieces if p[0] != "beep"]
        with self.lock:
            todo = [p for p in todo if self._key(p) not in self.cache]
            self.wanted = todo + [p for p in self.wanted if p not in todo]
        if todo:
            self.wake.set()

    def _worker(self):
        while True:
            self.wake.wait()
            with self.lock:
                piece = self.wanted.pop(0) if self.wanted else None
                if not self.wanted:
                    self.wake.clear()
            if piece is not None:
                try:
                    self._synth(piece)
                except Exception:
                    pass  # it'll be retried synchronously when actually needed
