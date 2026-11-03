"""Level speech to a common loudness, then make it louder without harsh clipping.

Open JTalk already peaks at full scale, so plain gain would distort.
We apply the gain and then a soft knee: everything below ~50% of full
scale passes unchanged, louder parts are rounded off smoothly (tanh)
towards a -1 dBFS ceiling. Speech stays clear while its average level
rises a lot. Pure Python with a lookup table, so it runs on the handheld.
"""
import array
import io
import math
import sys
import wave

CEILING = 29000          # about -1 dBFS
KNEE = 16000             # linear below this
RANGE = 4 * 32768        # gain up to 4x is handled by the table

_TABLE = None


def _table():
    global _TABLE
    if _TABLE is None:
        head = CEILING - KNEE
        t = array.array("h", bytes(2 * (2 * RANGE + 1)))
        for v in range(0, RANGE + 1):
            y = v if v <= KNEE else KNEE + head * math.tanh((v - KNEE) / head)
            t[RANGE + v] = int(y)
            t[RANGE - v] = -int(y)
        _TABLE = t
    return _TABLE


TARGET_RMS = 0.2 * 32768   # about -14 dBFS (speech parts only), the same for every voice
GATE = 300                 # ignore near-silence when measuring loudness


def level_gain(samples):
    """Gain that brings the speech (not the pauses) to TARGET_RMS."""
    total = n = 0
    for s in samples:
        if s > GATE or s < -GATE:
            total += s * s
            n += 1
    if not n:
        return 1.0
    return min(4.0, max(0.25, TARGET_RMS / math.sqrt(total / n)))


def louder(wav_bytes, volume_percent, level=False):
    """Return WAV bytes boosted by volume_percent (100 = unchanged, max 400).
    level=True first brings the clip to the common loudness (TARGET_RMS)."""
    if not level and volume_percent == 100:
        return wav_bytes
    with wave.open(io.BytesIO(wav_bytes)) as w:
        params = w.getparams()
        frames = w.readframes(params.nframes)
    if params.sampwidth != 2 or params.nchannels != 1:
        return wav_bytes
    samples = array.array("h", frames)
    if sys.byteorder == "big":
        samples.byteswap()
    gain = max(0.0, volume_percent / 100.0) * (level_gain(samples) if level else 1.0)
    gain = min(4.0, gain)
    table = _table()
    out = array.array("h", [table[RANGE + int(s * gain)] for s in samples])
    if sys.byteorder == "big":
        out.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())
    return buf.getvalue()
