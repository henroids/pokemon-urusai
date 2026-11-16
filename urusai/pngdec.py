"""Minimal stdlib-only PNG decoder (8-bit, non-interlaced) and encoder.

RetroArch sends the core frame as an 8-bit RGB PNG, so this is all the
handheld needs; no Pillow or numpy required on the device.
"""
import struct
import sys
import zlib
from array import array
from itertools import accumulate

_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Image:
    """RGB image: width, height and a flat list of (r, g, b) rows."""

    def __init__(self, width, height, rows):
        self.width = width
        self.height = height
        self.rows = rows  # list of bytes/bytearray, 3 bytes per pixel


def decode(data):
    if data[:8] != _SIG:
        raise ValueError("not a PNG")
    pos = 8
    idat = []
    palette = None
    width = height = depth = ctype = interlace = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if depth != 8:
        raise ValueError("only 8-bit PNGs are supported (got %s)" % depth)
    if interlace:
        raise ValueError("interlaced PNGs are not supported")
    ch = _CHANNELS[ctype]
    stride = width * ch
    raw = zlib.decompress(b"".join(idat))
    rows = []
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        _unfilter(f, line, prev, ch)
        rows.append(_to_rgb(line, ctype, width, palette))
        prev = line
    return Image(width, height, rows)


def _unfilter(f, line, prev, bpp):
    """Undo one row's PNG filter in place. RetroArch picks the best of all five
    per row, so every one of them is on the hot path: Sub and Up run at C speed,
    Average and Paeth (which depend on the byte just decoded) one channel at a time."""
    n = len(line)
    if f == 0:
        return
    if f == 1:      # Sub: a running sum along each channel
        for c in range(bpp):
            line[c::bpp] = array("I", accumulate(line[c::bpp])).tobytes()[_LOW_BYTE::4]
    elif f == 2:    # Up: add the row above, even and odd bytes in separate lanes so no carry crosses
        even = _lanes(n)
        a, b = int.from_bytes(line, "little"), int.from_bytes(prev, "little")
        odd = even << 8
        line[:] = ((((a & even) + (b & even)) & even) | (((a & odd) + (b & odd)) & odd)).to_bytes(n, "little")
    elif f == 3:    # Average of left and above
        for c in range(bpp):
            a = 0
            for i in range(c, n, bpp):
                a = line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
    elif f == 4:    # Paeth: whichever of left, above, upper-left is nearest to left + above - upper-left
        for c in range(bpp):
            a = ul = 0
            for i in range(c, n, bpp):
                b = prev[i]
                pa, pb = b - ul, a - ul
                pc = pa + pb
                if pa < 0:
                    pa = -pa
                if pb < 0:
                    pb = -pb
                if pc < 0:
                    pc = -pc
                a = line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else ul)) & 255
                ul = b
    else:
        raise ValueError("bad PNG filter %d" % f)


_LOW_BYTE = 0 if sys.byteorder == "little" else 3   # where a 32-bit sum keeps its low byte
_LANES = {}


def _lanes(n):
    """0x…00FF00FF, n bytes long."""
    if n not in _LANES:
        _LANES[n] = int.from_bytes(b"\xff\x00" * (n // 2 + 1), "little") & ((1 << (8 * n)) - 1)
    return _LANES[n]


def _to_rgb(line, ctype, width, palette):
    if ctype == 2:
        return bytes(line)
    out = bytearray(width * 3)
    if ctype == 3:                       # palette
        for c in range(3):
            out[c::3] = line.translate(palette[c::3].ljust(256, b"\0"))
    else:                                # RGBA: drop alpha; grey (+alpha): repeat the grey
        step = _CHANNELS[ctype]
        for c in range(3):
            out[c::3] = line[c if ctype == 6 else 0::step]
    return bytes(out)


def encode(img, level=6):
    """Encode an Image as an 8-bit RGB PNG (captures: level 1, quick on the handheld)."""
    return encode_rows(img.width, img.height, img.rows, 2, level)


def encode_rows(width, height, rows, color_type, level=6):
    """Rows of pixel bytes -> PNG (color_type 2 = RGB, 6 = RGBA)."""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, body):
        c = struct.pack(">I", len(body)) + kind + body
        return c + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level)) + chunk(b"IEND", b""))
