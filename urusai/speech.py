"""Decide what to say for a screen, and have it ready as fast as possible.

What is said (Narrator.plan) comes as *chunks*, short clips played one
after another. Between chunks RetroArch sends a fresh frame, so if the
screen moved on (cursor moved, menu closed) the rest is dropped:
  * Dialogue: a line is read as soon as it's printed (line 1 while line 2
    is still typing). After a scroll, only the new line.
  * Menus: the question (dialogue voice), an "open" sound, then each option
    as its own chunk in the menu voice, with a sound after the selected one:
    はい "biiing-booong", いいえ a buzzer, anything else a "pip". A cursor
    move says just the new option (はい/いいえ with their sound, a low "tok"
    on the first/last option). A falling sound when the menu closes.

Speed (Narrator.render): every clip is cached in memory and on disk, made
in the background as soon as text appears, and common menu words are made
at start-up, so most speech plays at once.
"""
import array
import hashlib
import os
import threading
from collections import OrderedDict

from . import normalize
from .sounds import cue, silence, to_wav, trim, wav_samples

MAX_OPTIONS = 12   # bigger "menus" (the name grid) just say the selection
CACHE_VERSION = 3  # bump when synthesis or trimming changes
YES, NO = "はい", "いいえ"

# Said a lot in Gen 1: made at start-up so they're instant from the first press.
COMMON_MENU = [
    "はい", "いいえ", "たたかう", "どうぐ", "ポケモン", "にげる", "ずかん", "レポート", "せってい", "とじる",
    "つかう", "すてる", "つよさをみる", "ならびかえ", "キャンセル", "やめる", "かう", "うる", "あずける",
    "ひきだす", "さいしょからはじめる", "つづきからはじめる", "せっていを かえる", "じぶんできめる",
]


def selection_cue(option):
    """Which sound marks the selected option."""
    return "yes" if option == YES else "no" if option == NO else "select"


def new_lines(lines, spoken):
    """Lines not read yet. When the box scrolls, its first lines are the last
    ones we read: drop them. Nothing new (e.g. mid-scroll) gives []."""
    for k in range(min(len(lines), len(spoken)), 0, -1):
        if lines[:k] == spoken[-k:]:
            return lines[k:]
    return lines


class ClipCache:
    """Speech clips by key: in memory (LRU) and as raw files on disk."""

    def __init__(self, directory=None, memory_items=128, disk_bytes=150 * 1024 * 1024):
        self.dir = directory
        self.mem = OrderedDict()
        self.memory_items = memory_items
        self.disk_bytes = disk_bytes
        self.lock = threading.Lock()
        self.writes = 0
        if self.dir:
            os.makedirs(self.dir, exist_ok=True)
            self.prune()

    @staticmethod
    def name(key):
        return hashlib.sha1(repr((CACHE_VERSION,) + key).encode("utf-8")).hexdigest() + ".pcm"

    def get(self, key):
        with self.lock:
            if key in self.mem:
                self.mem.move_to_end(key)
                return self.mem[key]
        if self.dir:
            path = os.path.join(self.dir, self.name(key))
            try:
                with open(path, "rb") as f:
                    samples = array.array("h", f.read())
                os.utime(path)  # recently used: keep it when pruning
                self._remember(key, samples)
                return samples
            except OSError:
                pass
        return None

    def put(self, key, samples):
        self._remember(key, samples)
        if self.dir:
            path = os.path.join(self.dir, self.name(key))
            try:
                with open(path + ".tmp", "wb") as f:
                    f.write(samples.tobytes())
                os.replace(path + ".tmp", path)
                self.writes += 1
                if self.writes % 200 == 0:
                    self.prune()
            except OSError:
                pass  # a full disk only costs speed

    def _remember(self, key, samples):
        with self.lock:
            self.mem[key] = samples
            self.mem.move_to_end(key)
            while len(self.mem) > self.memory_items:
                self.mem.popitem(last=False)

    def has(self, key):
        with self.lock:
            if key in self.mem:
                return True
        return bool(self.dir) and os.path.exists(os.path.join(self.dir, self.name(key)))

    def prune(self):
        """Keep the disk cache under its size limit, oldest-used files first."""
        try:
            files = [os.path.join(self.dir, f) for f in os.listdir(self.dir) if f.endswith(".pcm")]
            stats = sorted(((os.path.getmtime(p), os.path.getsize(p), p) for p in files))
        except OSError:
            return
        total = sum(s for _, s, _ in stats)
        for _, size, path in stats:
            if total <= self.disk_bytes:
                break
            try:
                os.unlink(path)
                total -= size
            except OSError:
                pass


class Narrator:
    """Plans what to say and renders it with two Speakers (dialogue, menu)."""

    def __init__(self, speaker, menu_speaker=None, cache_dir=None):
        self.speaker = speaker
        self.menu_speaker = menu_speaker or speaker
        self.position = False  # say 「2ばんめ」 after the selected option
        self.cues = True       # open/close/edge sounds (selection sounds are always on)
        self.pause_ms = 300    # pause between menu options (text itself flows on)
        self.cache = ClipCache(cache_dir)
        self.lock = threading.Lock()
        self.wanted = []       # pieces to make in the background, most urgent first
        self.wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True, name="urusai-tts").start()
        self.reset()

    def reset(self):
        self.spoken_lines = []  # dialogue lines already read (for scroll detection)
        self.spoken_menu = None  # options of the menu last read in full

    def box_closed(self):
        """The message box went away: the next box is new even if its text repeats."""
        self.spoken_lines = []

    # ---- what to say ------------------------------------------------------
    def plan(self, reading, repeat=False, settled=True):
        """Chunks (lists of pieces) to say for this reading.
        A piece is ('talk'|'menu', text), ('cue', name) or ('gap',) (the option pause).
        repeat: read everything again (the button). settled: the text has
        finished printing; otherwise only lines followed by another are read."""
        chunks = []
        if self.cues and self.spoken_menu is not None and reading.kind != "menu" and not repeat:
            chunks.append([("cue", "close")])
        lines = self._lines_to_read(reading, repeat, settled)
        if lines:
            chunks.append([("talk", " ".join(lines))])
        if reading.kind == "menu":
            chunks += self._menu_chunks(reading, repeat)
        elif reading.kind == "other" and repeat:
            chunks.append([("talk", " ".join(reading.other))])
        chunks = [[p for p in c if self._audible(p)] for c in chunks]
        return [c for c in chunks if any(p[0] != "gap" for p in c)]

    @staticmethod
    def _audible(piece):
        return piece[0] in ("cue", "gap") or bool(normalize.for_speech(piece[1]))

    def _lines_to_read(self, reading, repeat, settled):
        lines = reading.dialogue
        if not lines:
            return []
        if repeat:
            return lines
        if reading.kind == "dialogue" and not settled:
            lines = lines[:-1]  # the last line may still be typing
        return new_lines(lines, self.spoken_lines)

    def _menu_chunks(self, reading, repeat):
        opts = reading.options
        sel = reading.selected
        position = [("menu", "%dばんめ" % (sel + 1))] if self.position and len(opts) > 1 else []
        if len(opts) > MAX_OPTIONS or len(opts) == 1:
            return [[("menu", reading.selected_text)]]
        if not repeat and frozenset(opts) == self.spoken_menu:  # the cursor moved
            chunk = [("menu", reading.selected_text)] + position
            if reading.selected_text in (YES, NO):
                chunk.append(("cue", selection_cue(reading.selected_text)))
            elif self.cues and len(opts) > 2 and sel in (0, len(opts) - 1):
                chunk.append(("cue", "edge"))
            return [chunk]
        chunks = []
        for i, opt in enumerate(opts):
            chunk = [("gap",)] if i else ([("cue", "open")] if self.cues and not repeat else [])
            chunk.append(("menu", opt))
            if i == sel:
                chunk += [("cue", selection_cue(opt))] + position
            chunks.append(chunk)
        return chunks

    def remember(self, reading, settled=True):
        """Call after a reading was handled, so the next plan knows what was said."""
        lines = reading.dialogue if settled or reading.kind != "dialogue" else reading.dialogue[:-1]
        if lines:
            self.spoken_lines = list(lines)
        self.spoken_menu = frozenset(reading.options) if reading.kind == "menu" else None

    # ---- making the sound --------------------------------------------------
    def _speaker(self, kind):
        return self.menu_speaker if kind == "menu" else self.speaker

    def _key(self, piece):
        sp = self._speaker(piece[0])
        return (os.path.basename(sp.voice), sp.pitch, sp.speed, sp.volume, piece[1])

    def _synth(self, piece):
        key = self._key(piece)
        samples = self.cache.get(key)
        if samples is None:
            text, particles = normalize.with_particles(piece[1])
            samples = trim(wav_samples(self._speaker(piece[0]).wav(text, particles)))
            self.cache.put(key, samples)
        return samples

    def say(self, text, kind="talk"):
        """WAV for a short message of our own (e.g. 「よみあげ オフ」)."""
        return self.render([(kind, text)])

    def render(self, chunk):
        """WAV bytes for one chunk (uses the cache, synthesises what's missing)."""
        out = array.array("h")
        for i, piece in enumerate(chunk):
            if piece[0] == "gap":
                out += silence(self.pause_ms - 120)  # RetroArch's own round trip adds ~0.1 s
            elif piece[0] == "cue":
                out += silence(60) + cue(piece[1]) + silence(60)
            else:
                out += self._synth(piece)
                if i + 1 < len(chunk) and chunk[i + 1][0] in ("talk", "menu"):
                    out += silence(self.pause_ms)
        return to_wav(out)

    def ready(self, chunk):
        return all(self.cache.has(self._key(p)) for p in chunk if p[0] in ("talk", "menu"))

    def prepare(self, chunks, urgent=True):
        """Make these chunks' speech in the background."""
        todo = [p for c in chunks for p in c if p[0] in ("talk", "menu")]
        todo = [p for p in todo if not self.cache.has(self._key(p))]
        if not todo:
            return
        with self.lock:
            rest = [p for p in self.wanted if p not in todo]
            self.wanted = todo + rest if urgent else rest + todo
        self.wake.set()

    def warm_up(self, phrases=COMMON_MENU):
        """Make common menu words at start-up (lowest priority)."""
        self.prepare([[("menu", p)] for p in phrases], urgent=False)

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
                    pass  # it'll be retried when it's actually needed
