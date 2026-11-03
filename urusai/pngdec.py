"""Minimal stdlib-only PNG decoder (8-bit, non-interlaced) and encoder.

RetroArch sends the core frame as an 8-bit RGB PNG, so this is all the
handheld needs; no Pillow or numpy required on the device.
"""
import struct
import zlib

_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Image:
    """RGB image: width, height and a flat list of (r, g, b) rows."""

    def __init__(self, width, height, rows):
        self.width = width
        self.height = height
        self.rows = rows  # list of bytes/bytearray, 3 bytes per pixel

    def pixel(self, x, y):
        r = self.rows[y]
        i = x * 3
        return r[i], r[i + 1], r[i + 2]


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
    n = len(line)
    if f == 0:
        return
    if f == 1:
        for i in range(bpp, n):
            line[i] = (line[i] + line[i - bpp]) & 255
    elif f == 2:
        for i in range(n):
            line[i] = (line[i] + prev[i]) & 255
    elif f == 3:
        for i in range(n):
            a = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
    elif f == 4:
        for i in range(n):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            line[i] = (line[i] + pr) & 255
    else:
        raise ValueError("bad PNG filter %d" % f)


def _to_rgb(line, ctype, width, palette):
    if ctype == 2:
        return bytes(line)
    out = bytearray(width * 3)
    for x in range(width):
        if ctype == 6:
            r, g, b = line[x * 4], line[x * 4 + 1], line[x * 4 + 2]
        elif ctype == 0:
            r = g = b = line[x]
        elif ctype == 4:
            r = g = b = line[x * 2]
        else:  # palette
            i = line[x] * 3
            r, g, b = palette[i], palette[i + 1], palette[i + 2]
        out[x * 3:x * 3 + 3] = bytes((r, g, b))
    return bytes(out)


def encode(img):
    """Encode an Image as an 8-bit RGB PNG (used for captures and tests)."""
    raw = b"".join(b"\x00" + bytes(r) for r in img.rows)

    def chunk(kind, body):
        c = struct.pack(">I", len(body)) + kind + body
        return c + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def downscale(img, scale, x0=0, y0=0, w=160, h=144):
    """Nearest-neighbour crop+downscale (sample each block's centre)."""
    half = scale // 2
    rows = []
    for ty in range(h):
        src = img.rows[y0 + ty * scale + half]
        out = bytearray(w * 3)
        for tx in range(w):
            i = (x0 + tx * scale + half) * 3
            out[tx * 3:tx * 3 + 3] = src[i:i + 3]
        rows.append(bytes(out))
    return Image(w, h, rows)
