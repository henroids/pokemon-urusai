"""Sound cues and small audio helpers (16-bit mono, 48 kHz)."""
import array
import io
import math
import wave

RATE = 48000


def wav_samples(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return array.array("h", w.readframes(w.getnframes()))


def to_wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def duration(wav_bytes):
    return (len(wav_bytes) - 44) / (2.0 * RATE)


def silence(ms):
    return array.array("h", bytes(2 * (RATE * max(0, ms) // 1000)))


def trim(samples, threshold=500, lead_ms=50, tail_ms=80):
    """Cut Open JTalk's ~0.4 s lead-in and ~0.6 s tail of silence."""
    start = next((i for i, x in enumerate(samples) if abs(x) > threshold), None)
    if start is None:
        return array.array("h")
    end = len(samples) - next(i for i, x in enumerate(reversed(samples)) if abs(x) > threshold)
    lo = max(0, start - RATE * lead_ms // 1000)
    hi = min(len(samples), end + RATE * tail_ms // 1000)
    return samples[lo:hi]


def chime(notes=((1318.5, 0.0), (1046.5, 0.30)), length=0.85, level=8000):
    """A soft two-note bell, "biiing-booong" (E6 then C6): はい is selected."""
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


def buzzer(length=0.8, level=6500):
    """A game-over horn, "eerrrr": two slightly detuned buzzy tones. いいえ is selected."""
    n = int(RATE * length)
    attack, release = RATE * 10 // 1000, RATE * 60 // 1000
    out = array.array("h")
    for i in range(n):
        t = i / RATE
        env = min(1.0, i / attack, (n - i) / release)
        v = 0.0
        for f in (180.0, 186.0):
            for h, a in ((1, 1.0), (3, 0.45), (5, 0.25), (7, 0.12)):
                v += a * math.sin(2 * math.pi * f * h * t)
        out.append(int(level * env * v / 3.6))
    return out


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


CUES = {
    "yes": chime,                                        # biiing-booong: はい selected
    "no": buzzer,                                        # eerrrr: いいえ selected
    "select": lambda: blip((1568,), ms=80, level=6000),  # pip: the selected option of other menus
    "open": lambda: blip((784, 1175)),                   # rising: a menu opened
    "close": lambda: blip((1175, 784)),                  # falling: the menu closed
    "edge": lambda: blip((392,), ms=60, level=6000),     # low tok: first/last option
}
_made = {}


def cue(name):
    """A sound cue (made once, they never change)."""
    if name not in _made:
        _made[name] = CUES[name]()
    return _made[name]
