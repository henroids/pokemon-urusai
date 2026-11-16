"""Level speech to a common loudness, then make it louder without harsh clipping.

Open JTalk already peaks at full scale, so plain gain would distort.
We apply the gain and then a soft knee: everything below ~50% of full
scale passes unchanged, louder parts are rounded off smoothly (tanh)
towards a -1 dBFS ceiling. Speech stays clear while its average level
rises a lot.

Pure Python, but no Python-level loop over the samples (a 4-second clip has
200,000 of them, and a new line must not wait on that): loudness is measured
with C-speed sums and counts, and gain + knee are one table lookup per sample.
"""
import array
import io
import math
import sys
import wave
from functools import lru_cache
from operator import mul

CEILING = 29000          # about -1 dBFS
KNEE = 16000             # linear below this
MAX_GAIN = 4.0
GAIN_STEPS = 32          # gains are rounded to 1/32 (0.27 dB at most), so their tables are reused
TARGET_RMS = 0.2 * 32768   # about -14 dBFS (speech parts only), the same for every voice


def _soft(v):
    head = CEILING - KNEE
    return int(v) if v <= KNEE else int(KNEE + head * math.tanh((v - KNEE) / head))


@lru_cache(maxsize=24)
def _curve(steps):
    """For gain steps/GAIN_STEPS: a list giving the output for every 16-bit sample,
    indexed by the sample itself (negative samples index from the end, as Python does)."""
    gain = steps / GAIN_STEPS
    up = [_soft(v * gain) for v in range(32768)]
    return up + [-_soft(v * gain) for v in range(32768, 0, -1)]


def level_gain(samples):
    """Gain that brings the speech (not the pauses) to TARGET_RMS.
    Pauses are the samples below 256, found by their high byte."""
    some = samples[::4]                      # every 4th sample measures loudness just as well
    high = some.tobytes()[1 if sys.byteorder == "little" else 0::2]
    n = len(some) - high.count(0) - high.count(255)
    if not n:
        return 1.0
    return min(MAX_GAIN, max(0.25, TARGET_RMS / math.sqrt(sum(map(mul, some, some)) / n)))


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
    gain = min(MAX_GAIN, max(0.0, volume_percent / 100.0) * (level_gain(samples) if level else 1.0))
    out = array.array("h", map(_curve(round(gain * GAIN_STEPS)).__getitem__, samples))
    if sys.byteorder == "big":
        out.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())
    return buf.getvalue()
