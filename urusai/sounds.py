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


def pad_to(wav_bytes, seconds):
    """The same WAV, with silence added so it lasts at least this long."""
    samples = array.array("h", wav_bytes[44:])
    return to_wav(samples + silence(int(1000 * seconds) - len(samples) * 1000 // RATE))


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
