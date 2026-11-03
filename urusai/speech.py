"""Decide what to say for a screen, and say it quickly.

  * Dialogue: when the box scrolls up one line, only the new line is read.
  * Menus: an "open" cue, the question (dialogue voice), then every option
    in the menu voice with a chime ("biiing-booong") right after the selected
    one. Moving the cursor says just the new choice (+ a low "tok" on the
    first/last option). A falling cue when the menu closes.
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


def blip(freqs, ms=70, level=7000, gap_ms=10):
    """Short tones in a row: a quick, quiet UI sound."""
    out = array.array("h")
    n, fade = RATE * ms // 1000, RATE * 6 // 1000
    for f in freqs:
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            out.append(int(level * env * math.sin(2 * math.pi * f * i / RATE)))
        out += silence(gap_ms)
    return out


_CUES = {}
CUE_SOUNDS = {
    "select": chime,                                    # biiing-booong: the selected option
    "open": lambda: blip((784, 1175)),                  # rising: a menu opened
    "close": lambda: blip((1175, 784)),                 # falling: the menu closed
    "edge": lambda: blip((392,), ms=60, level=6000),    # low tok: first/last option
}


def cue(name):
    """A sound cue (cached: they never change)."""
    if name not in _CUES:
        _CUES[name] = CUE_SOUNDS[name]()
    return _CUES[name]


def to_wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def new_lines(lines, spoken):
    """Lines not read yet. When the box scrolls, its first lines are the last
    ones we read: drop them. Nothing new (e.g. mid-scroll, the old line alone)
    gives []. The "say it again" button doesn't use this."""
    for k in range(min(len(lines), len(spoken)), 0, -1):
        if lines[:k] == spoken[-k:]:
            return lines[k:]
    return lines


class Narrator:
    """Plans utterances and renders them with two Speakers (dialogue, menu)."""

    def __init__(self, speaker, menu_speaker=None, cache_size=64):
        self.position = False  # say 「2ばんめ」 after the selected option
        self.cues = True       # open/close/edge sounds (the selection chime is always on)
        self.pause_ms = 300    # silence between menu options / choices (text itself flows on)
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
        self.spoken_menu = None     # options of the menu we last read in full

    def box_closed(self):
        """The message box went away: the next box is new even if its text repeats."""
        self.spoken_dialogue = []

    # ---- planning -------------------------------------------------------
    def plan(self, reading, repeat=False):
        """Pieces to say for this reading: ('talk'|'menu', text) or ('cue', name).
        repeat=True reads everything again (the "say it again" button)."""
        pieces = []
        if self.cues and self.spoken_menu is not None and reading.kind != "menu" and not repeat:
            pieces.append(("cue", "close"))
        dialogue = reading.dialogue
        if reading.kind == "menu":
            opts = reading.options
            same_menu = not repeat and frozenset(opts) == self.spoken_menu
            if dialogue:
                lines = dialogue if repeat else new_lines(dialogue, self.spoken_dialogue)
                if lines:
                    pieces.append(("talk", " ".join(lines)))
            position = [("menu", "%dばんめ" % (reading.selected + 1))] if self.position and len(opts) > 1 else []
            if len(opts) > MAX_OPTIONS or len(opts) == 1:
                pieces.append(("menu", reading.selected_text))
            elif same_menu:
                pieces += [("menu", reading.selected_text)] + position
                if self.cues and len(opts) > 2 and reading.selected in (0, len(opts) - 1):
                    pieces.append(("cue", "edge"))
            else:
                if self.cues and not repeat:
                    pieces.insert(0, ("cue", "open"))
                for i, opt in enumerate(opts):
                    pieces.append(("menu", opt))
                    if i == reading.selected:
                        pieces += [("cue", "select")] + position
        elif reading.kind == "dialogue":
            lines = dialogue if repeat else new_lines(dialogue, self.spoken_dialogue)
            if lines:
                pieces.append(("talk", " ".join(lines)))
        elif reading.kind == "other":
            pieces.append(("talk", " ".join(reading.other)))
        return [p for p in pieces if p[0] == "cue" or normalize.for_speech(p[1])]

    def remember(self, reading):
        """Call after a reading was handled, so the next plan knows what was said."""
        if reading.dialogue:
            self.spoken_dialogue = list(reading.dialogue)
        self.spoken_menu = frozenset(reading.options) if reading.kind == "menu" else None

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

    def say(self, text, kind="talk"):
        """WAV for a short message of our own (e.g. 「よみあげ オフ」)."""
        return self.render([(kind, text)])

    def render(self, pieces):
        """WAV bytes for a plan (uses the cache, synthesises what's missing)."""
        out = array.array("h")
        for i, piece in enumerate(pieces):
            if piece[0] == "cue":
                out += silence(60) + cue(piece[1]) + silence(60)
                continue
            out += self._synth(piece)
            if i + 1 < len(pieces) and pieces[i + 1][0] != "cue":
                out += silence(self.pause_ms)
        return to_wav(out)

    def prepare(self, pieces):
        """Synthesise these pieces in the background (latest request first)."""
        todo = [p for p in pieces if p[0] != "cue"]
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
