"""Read the kana on a Gen 1 (Japanese) screen.

Gen 1 Japanese text sits on the 8x8 tile grid. Dakuten/handakuten (゛/゜)
are drawn in the tile *above* the kana they modify, so we combine a mark
with the kana directly below it.

Reading policy (tuned for a child who can't read yet):
  * if a filled ▶ cursor is on screen, read the dialogue (if any) and
    then the selected menu item;
  * otherwise read the dialogue box (bottom rows);
  * otherwise read every line of text on screen.
"""
import unicodedata

from . import screen

MARKS = {"゛": "゙", "゜": "゚"}
MARK_NAMES = {"゛": "だくてん", "゜": "はんだくてん"}
DIALOGUE_TOP = 12  # the standard text box occupies rows 12-17
SPECIAL_BREAK = {"<box>", "<cursor_off>", None}
SPECIAL_BLANK = {"<more>", "<ignore>", " "}


def combine(base, mark):
    s = unicodedata.normalize("NFC", base + MARKS[mark])
    return s if len(s) == 1 else None


class Segment:
    def __init__(self, row, col):
        self.row, self.c0, self.c1 = row, col, col
        self.chars = []
        self.selected = False

    @property
    def text(self):
        return " ".join("".join(self.chars).split())

    def __repr__(self):
        return "Seg(r%d c%d-%d %s%r)" % (self.row, self.c0, self.c1, "*" if self.selected else "", self.text)


def label_grid(font, grid):
    return [[font.match(t) for t in row] for row in grid]


def segments(labels):
    rows, cols = len(labels), len(labels[0])
    # Pass 1: attach marks to the kana below them.
    consumed = set()
    combined = {}
    for r in range(1, rows):
        for c in range(cols):
            above = labels[r - 1][c]
            ch = labels[r][c]
            if above in MARKS and ch and len(ch) == 1 and ch not in MARKS:
                k = combine(ch, above)
                if k:
                    combined[(r, c)] = k
                    consumed.add((r - 1, c))
    # Pass 2: split each row into runs of text.
    out = []
    for r in range(rows):
        seg = None
        for c in range(cols):
            lab = labels[r][c]
            if (r, c) in consumed:
                lab = " "
            if lab in SPECIAL_BREAK or lab == "<cursor>":
                if seg and seg.text:
                    out.append(seg)
                seg = None
                if lab == "<cursor>":
                    seg = Segment(r, c + 1)
                    seg.selected = True
                continue
            if lab in SPECIAL_BLANK:
                if seg:
                    seg.chars.append(" ")
                continue
            ch = combined.get((r, c), lab)
            if ch in MARKS:
                ch = MARK_NAMES[ch]
            if seg is None:
                seg = Segment(r, c)
            seg.chars.append(ch)
            seg.c1 = c
        if seg and seg.text:
            out.append(seg)
    # A selected item is one menu entry: cut it at a wide gap (2+ blanks).
    for s in out:
        if s.selected:
            raw = "".join(s.chars).strip()
            s.chars = list(raw.split("  ")[0])
    return out


def _menu_box(labels, row, col):
    """Column span and row span of the box that contains (row, col)."""
    cols = len(labels[0])
    left, right = col, col
    while left > 0 and labels[row][left - 1] != "<box>":
        left -= 1
    while right < cols - 1 and labels[row][right + 1] != "<box>":
        right += 1
    top, bot = row, row
    edge = left - 1
    if edge >= 0:
        while top > 0 and labels[top - 1][edge] == "<box>":
            top -= 1
        while bot < len(labels) - 1 and labels[bot + 1][edge] == "<box>":
            bot += 1
    return left, right, top, bot


def read_labels(labels):
    segs = segments(labels)
    if not segs:
        return ""
    selected = [s for s in segs if s.selected]
    if selected:
        sel = selected[0]
        l, r, t, b = _menu_box(labels, sel.row, sel.c0)
        dialogue = [s for s in segs if not s.selected and s.row >= DIALOGUE_TOP
                    and not (t <= s.row <= b and s.c1 >= l and s.c0 <= r)]
        parts = [s.text for s in dialogue] + [sel.text]
        return " ".join(p for p in parts if p)
    dialogue = [s for s in segs if s.row >= DIALOGUE_TOP]
    use = dialogue or segs
    return " ".join(s.text for s in use)


def read_image(font, img):
    frame = screen.to_gb_frame(img)
    return read_labels(label_grid(font, screen.tiles(frame)))
