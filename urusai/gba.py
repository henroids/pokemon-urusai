"""Read the Japanese text on a Game Boy Advance Pokémon screen (240x160).

Unlike the Game Boy, GBA text is not on a tile grid: letters sit at any
pixel, come in several fonts, sizes and colours, and have a drop shadow.
So letters are found by their ink, wherever they are:

  1. Text is always drawn on a plain window. Colours that fill long runs
     of many rows are taken as window backgrounds.
  2. On each background, the colours of pixels standing alone at a top-left
     corner are candidate text colours.
  3. For a text colour, every pixel that starts a stroke (background above
     it, another colour to its left) may be the top of a letter. The font
     table says which letter shapes have a top row like that, and a
     fingerprint of the ink in the shape's box says whether one is there.
  4. Letters are joined into lines (same font, baseline and colours), lines
     into a Reading: the menu holding the ▶ cursor, the message at the
     bottom of the screen, and the rest.

font/gba_jp.json (tools/build_gba_font.py) holds the fingerprints. Every
step works on whole rows at C speed (bytes.translate and big integers), so
the handheld needs nothing but Python.
"""
import hashlib
import json
import re
from collections import Counter

from .reader import Reading, fix_shared

SPECKS = set(" ー・．。：…！l1Iｌ")   # shapes a few stray pixels can form
MORE = "<more>"      # the "press A" arrow
CURSOR = "▶"
SCALE_W, SCALE_H = 240, 160
RUN = 24             # a background fills at least this many pixels in a row…
RUN_ROWS = 8         # …on at least this many rows
MAX_BACKGROUNDS = 4
MAX_INKS = 4         # text colours tried per background
WORD_GAP = 4         # pixels between letters that make a space
SEGMENT_GAP = 24     # …and that start another entry (menu columns)
MESSAGE_TOP = 104    # lines starting below this are the message box
COLUMN_REACH = 24    # menu options in a column are at most this far apart
_RUNS = re.compile(rb"\x00{%d,}" % (RUN - 1))
_ONLY = [bytes(49 if v == c else 48 for v in range(256)) for c in range(256)]   # "1" where a channel == c
_MIX = [bytes((v * m + a) & 255 for v in range(256)) for m, a in ((73, 11), (151, 97), (211, 5))]


def is_gba(img):
    """A GBA frame: 240x160 or a whole multiple of it."""
    k = img.width // SCALE_W
    return k >= 1 and (img.width, img.height) == (SCALE_W * k, SCALE_H * k)


def fingerprint(w, rows):
    """What the font table stores for a letter: a hash of its ink box (not the picture)."""
    data = bytes((w, len(rows))) + b"".join(r.to_bytes(2, "big") for r in rows)
    return hashlib.blake2b(data, digest_size=8).hexdigest()


def anchor_key(w, rows):
    """Index entry for a shape: ('bits:pattern' of its top row from the first ink
    pixel to the box's right edge, (that pixel's offset in the box, second row, box height))."""
    ax = w - rows[0].bit_length()
    return "%d:%x" % (w - ax, rows[0]), (ax, rows[1] if len(rows) > 1 else -1, len(rows))


class GbaFont:
    def __init__(self, data=None):
        data = data or {"fonts": [], "glyphs": {}, "anchors": {}}
        self.fonts = data["fonts"]
        self.glyphs = data["glyphs"]        # fingerprint -> [[label, font, left, top, advance], …]
        # top-row bits -> {top-row pattern: [(ax, {second row: [box heights]}), …]}, nearest ax first
        self.anchors = {}
        for key, shapes in data["anchors"].items():
            bits, pattern = key.split(":")
            by_ax = {}
            for ax, second, h in shapes:
                by_ax.setdefault(ax, {}).setdefault(second, []).append(h)
            self.anchors.setdefault(int(bits), {})[int(pattern, 16)] = sorted(by_ax.items())
        self.widths = sorted(self.anchors)
        self.known = {}                     # (w, h, ink box as one int) -> shapes or None, as seen on screen

    def identify(self, w, h, box):
        """The letters with this ink box (None if it isn't one), remembered:
        screens repeat, so fingerprints are rarely worked out twice."""
        if len(self.known) > 200000:
            self.known.clear()
        m = (1 << w) - 1
        hit = self.glyphs.get(fingerprint(w, [(box >> (w * i)) & m for i in range(h - 1, -1, -1)]))
        self.known[w, h, box] = hit
        return hit

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as f:
                return cls(json.load(f))
        except OSError:
            return cls()

    def __len__(self):
        return len(self.glyphs)


class Frame:
    """A 240x160 screen as one bytes object per colour channel."""

    def __init__(self, img):
        k = img.width // SCALE_W
        rows = img.rows[k // 2::k]
        first = (k // 2) * 3
        self.w, self.h = SCALE_W, SCALE_H
        self.chan = [b"".join(row[first + c::3 * k] for row in rows) for c in range(3)]
        self.full = (1 << self.w) - 1

    def colour(self, x, y):
        i = y * self.w + x
        return tuple(ch[i] for ch in self.chan)

    def mask(self, colour):
        """Per row, an int with a 1 bit where the pixel has this colour (leftmost = highest).
        The whole frame is compared in a handful of C calls, then cut into rows."""
        r, g, b = (int.from_bytes(ch.translate(_ONLY[v]), "big") for ch, v in zip(self.chan, colour))
        n = self.w * self.h
        bits = int((r & g & b).to_bytes(n, "big"), 2)
        w, full = self.w, self.full
        return [(bits >> shift) & full for shift in range(n - w, -1, -w)]

    def backgrounds(self):
        """Colours that fill long runs on many rows, most rows first."""
        r, g, b = (int.from_bytes(ch.translate(t), "big") for ch, t in zip(self.chan, _MIX))
        mixed = r ^ g ^ b                       # one byte per pixel that differs between colours
        same_as_left = (mixed ^ (mixed >> 8)).to_bytes(self.w * self.h, "big")   # 0 = same as the pixel before
        rows_with, seen = Counter(), set()
        for m in _RUNS.finditer(same_as_left):
            y, x = divmod(m.start(), self.w)
            c = self.colour(x, y)
            if (c, y) not in seen:
                seen.add((c, y))
                rows_with[c] += 1
        return [c for c, n in rows_with.most_common(MAX_BACKGROUNDS) if n >= RUN_ROWS]

    def inks(self, bg):
        """Text colour candidates on a background: colours of pixels whose left,
        upper and upper-left neighbours are all background."""
        seen = Counter()
        w = self.w
        prev = bg[0]
        for y in range(1, self.h):
            cur = bg[y]
            corners = ~cur & (cur >> 1) & prev & (prev >> 1) & self.full
            while corners:
                low = corners & -corners
                seen[self.colour(w - low.bit_length(), y)] += 1
                corners ^= low
            prev = cur
        return [c for c, n in seen.most_common(MAX_INKS) if n >= 2]


class Glyph:
    __slots__ = ("x", "y", "w", "h", "shapes", "ink", "bg", "labels", "font", "cell_x", "cell_y", "advance")

    def __init__(self, x, y, w, h, shapes, ink, bg):
        self.x, self.y, self.w, self.h = x, y, w, h     # the ink's box on screen
        self.shapes, self.ink, self.bg = shapes, ink, bg

    def choose(self, shape):
        _, self.font, left, top, self.advance = shape
        self.cell_x, self.cell_y = self.x - left, self.y - top
        # letters this font draws alike (0/O, へ/ヘ…): told apart by their neighbours later
        self.labels = [s[0] for s in self.shapes if (s[1], s[3]) == (self.font, top)]

    @property
    def label(self):
        return self.labels[0]


def find_glyphs(font, frame):
    """Every letter on the screen, as Glyphs (not yet assigned a font)."""
    out = []
    w, h = frame.w, frame.h
    known = font.known
    for bg in frame.backgrounds():
        bg_rows = frame.mask(bg)
        for ink in frame.inks(bg_rows):
            if ink == bg:
                continue
            rows = frame.mask(ink) + [0]
            found = []
            for y in range(1, h):
                row = rows[y]
                starts = row & ~(row >> 1) & bg_rows[y - 1]   # a stroke's left end with background above it
                while starts:
                    low = starts & -starts
                    starts ^= low
                    x = w - low.bit_length()
                    left = row >> (w - x)                       # the pixels to the left, nearest lowest
                    room = (left & -left).bit_length() - 1 if left else x   # …how many of them aren't ink
                    above, below = bg_rows[y - 1], rows[y + 1]
                    for bits in font.widths:
                        if x + bits > w:
                            break
                        shift = w - x - bits
                        for ax, seconds in font.anchors[bits].get((row >> shift) & ((1 << bits) - 1), ()):
                            if ax > room:
                                break
                            gw = bits + ax
                            m = (1 << gw) - 1
                            if (above >> shift) & m != m:
                                continue   # not plain background above the box: not a letter
                            heights = seconds.get((below >> shift) & m, ())
                            if -1 in seconds:              # shapes one row high
                                heights = seconds[-1] + list(heights)
                            for gh in heights:
                                if y + gh > h or (rows[y + gh] >> shift) & m:
                                    continue   # ink right below the box: part of something bigger
                                box = 0
                                for r in rows[y:y + gh]:
                                    box = (box << gw) | ((r >> shift) & m)
                                try:
                                    hit = known[gw, gh, box]
                                except KeyError:
                                    hit = font.identify(gw, gh, box)
                                if hit:
                                    found.append(Glyph(x - ax, y, gw, gh, hit, ink, bg))
            # A small letter's ink can be part of a bigger one (ー in エ): biggest first, no overlaps.
            found.sort(key=lambda g: -g.w * g.h)
            kept = []
            for g in found:
                if not any(g.x < k.x + k.w and k.x < g.x + g.w and g.y < k.y + k.h and k.y < g.y + g.h for k in kept):
                    kept.append(g)
            out += kept
    # White text's shadow, seen "on" the white letters, can pass for tiny letters of
    # its own: drop letters whose background is the ink of a letter they touch.
    inks = {g.ink for g in out}
    return [g for g in out if g.bg not in inks or not any(
        k.ink == g.bg and g.x <= k.x + k.w + 2 and k.x <= g.x + g.w + 2 and g.y <= k.y + k.h + 2 and k.y <= g.y + g.h + 2
        for k in out)]


def assign_fonts(glyphs):
    """A shape can belong to several fonts (at different heights in the cell).
    Each letter takes the reading that most letters of its colour agree on."""
    votes = Counter()
    for g in glyphs:
        for font, top in {(s[1], s[3]) for s in g.shapes}:
            votes[(g.ink, g.bg, font, g.y - top)] += 1
    for g in glyphs:
        g.choose(max(g.shapes, key=lambda s: votes[(g.ink, g.bg, s[1], g.y - s[3])]))


def pick(labels, before, after):
    """One of the letters a shape can be, by the letters next to it:
    0 rather than O unless it stands in a word, × before a number; kana pairs
    like へ/ヘ are settled afterwards by reader.fix_shared."""
    if len(labels) == 1:
        return labels[0]
    near = [n[0] for n in (before, after) if n]
    if "0" in labels and "O" in labels:
        in_word = any(n.isascii() and n.isalpha() for n in near) and not any(n.isdigit() for n in near)
        return "O" if in_word else "0"
    if "×" in labels:
        return "×" if after and after[0].isdigit() else next(x for x in labels if x != "×")
    return labels[0]


class Segment:
    """Letters in a row with no big gap: a line of text or one menu entry."""

    def __init__(self, glyphs):
        g0 = glyphs[0]
        self.y, self.ink, self.bg = g0.cell_y, g0.ink, g0.bg
        self.selected = g0.label == CURSOR
        self.more = any(g.label == MORE for g in glyphs)
        letters = [g for g in glyphs if g.label not in (CURSOR, MORE)]
        self.x = letters[0].cell_x if letters else g0.cell_x
        text, end = [], None
        for i, g in enumerate(letters):
            if end is not None and g.cell_x - end >= WORD_GAP:
                text.append(" ")
            text.append(pick(g.labels, letters[i - 1].labels if i else (), letters[i + 1].labels if i + 1 < len(letters) else ()))
            end = g.cell_x + g.advance
        self.text = fix_shared("".join(text))
        self.letters = len(letters)

    def __repr__(self):
        return "Seg(%d,%d %s%r)" % (self.x, self.y, "*" if self.selected else "", self.text)


def segments(glyphs):
    lines = {}
    for g in glyphs:
        lines.setdefault((g.cell_y, g.ink, g.bg, g.font), []).append(g)
    out = []
    for _, line in sorted(lines.items(), key=lambda kv: kv[0][0]):
        line.sort(key=lambda g: g.cell_x)
        cur = [line[0]]
        for g in line[1:]:
            if g.cell_x - (cur[-1].cell_x + cur[-1].advance) >= SEGMENT_GAP:
                out.append(Segment(cur))
                cur = []
            cur.append(g)
        out.append(Segment(cur))
    # marks on their own are more likely specks of the picture than text
    return [s for s in out if s.selected or s.more or any(ch not in SPECKS for ch in s.text)]


def menu_of(selected, segs):
    """The entries of the cursor's menu: same colours, and reached from the
    selected one through entries in the same column or on the same row."""
    pool = [s for s in segs if (s.ink, s.bg) == (selected.ink, selected.bg) and s.text]
    menu, todo = [selected], [selected]
    while todo:
        a = todo.pop()
        for s in pool:
            if s not in menu and ((abs(s.x - a.x) <= 2 and abs(s.y - a.y) <= COLUMN_REACH) or s.y == a.y):
                menu.append(s)
                todo.append(s)
    return sorted(menu, key=lambda s: (s.y, s.x))


def reading_of(segs):
    r = Reading(more=any(s.more for s in segs))
    cursors = [s for s in segs if s.selected and s.text]
    menu = []
    if cursors:
        sel = max(cursors, key=lambda s: (s.y, s.x))   # the menu opened last sits lowest
        menu = menu_of(sel, segs)
        r.options = [s.text for s in menu]
        r.selected = menu.index(sel)
    rest = [s for s in segs if s not in menu and s.text]
    lines = {}
    for s in rest:
        if s.y >= MESSAGE_TOP:
            lines.setdefault(s.y, []).append(s)
    r.dialogue = [" ".join(s.text for s in sorted(lines[y], key=lambda s: s.x)) for y in sorted(lines)]
    if r.selected is None and not r.dialogue:
        r.other = [s.text for s in sorted(rest, key=lambda s: (s.y, s.x))]
    return r


def analyze(font, img):
    """Reading of a GBA frame (any whole multiple of 240x160)."""
    glyphs = find_glyphs(font, Frame(img))
    assign_fonts(glyphs)
    return reading_of(segments(glyphs))
