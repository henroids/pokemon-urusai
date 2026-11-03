"""Read the kana on a Gen 1 (Japanese) screen.

Gen 1 Japanese text sits on the 8x8 tile grid. Dakuten/handakuten (゛/゜)
are drawn in the tile *above* the kana they modify, so we combine a mark
with the kana directly below it.

Reading policy (tuned for a child who can't read yet):
  * if a filled ▶ cursor is on screen, read the dialogue box (if one is
    open) and then the selected menu entry;
  * otherwise read the dialogue box;
  * otherwise read every line of text on screen, top to bottom.
"""
import unicodedata

from . import screen

MARKS = {"゛": "゙", "゜": "゚"}
MARK_NAMES = {"゛": "だくてん", "゜": "はんだくてん"}
BREAK = {"<box>", "<cursor_off>", None}
BLANK = {"<more>", "<ignore>", " "}

# Tiles the game shares between hiragana and katakana; we pick by context.
SHARED = {"へ": "ヘ", "べ": "ベ", "ぺ": "ペ", "り": "リ", "っ": "ッ"}
SHARED.update({v: k for k, v in list(SHARED.items())})


def combine(base, mark):
    s = unicodedata.normalize("NFC", base + MARKS[mark])
    return s if len(s) == 1 else None


def is_kata(ch):
    return "ァ" <= ch <= "ヺ" or ch == "ー"


def is_hira(ch):
    return "ぁ" <= ch <= "ゖ"


class Segment:
    def __init__(self, row):
        self.row = row
        self.cols = []   # column of each entry in chars
        self.chars = []  # one string per tile (" " for a blank)
        self.selected = False

    @property
    def c0(self):
        return self.cols[0] if self.cols else 0

    @property
    def c1(self):
        return self.cols[-1] if self.cols else 0

    @property
    def text(self):
        return " ".join("".join(self.chars).split())

    def add(self, col, ch):
        self.cols.append(col)
        self.chars.append(ch)

    def __repr__(self):
        return "Seg(r%d c%d-%d %s%r)" % (self.row, self.c0, self.c1, "*" if self.selected else "", self.text)


def label_grid(font, grid):
    return [[font.match(t) for t in row] for row in grid]


def segments(labels):
    rows, cols = len(labels), len(labels[0])
    consumed, combined = set(), {}
    for r in range(1, rows):
        for c in range(cols):
            above, ch = labels[r - 1][c], labels[r][c]
            if above in MARKS and ch and len(ch) == 1 and ch not in MARKS:
                k = combine(ch, above)
                if k:
                    combined[(r, c)] = k
                    consumed.add((r - 1, c))
    out = []
    for r in range(rows):
        seg = None
        for c in range(cols):
            lab = " " if (r, c) in consumed else labels[r][c]
            if lab is None and seg is not None and seg.selected and not seg.text:
                continue  # e.g. the party screen's Pokémon icon right after ▶
            if lab in BREAK or lab == "<cursor>":
                if seg and seg.text:
                    out.append(seg)
                seg = None
                if lab == "<cursor>":
                    seg = Segment(r)
                    seg.selected = True
                continue
            if lab in BLANK:
                if seg and seg.chars:
                    seg.add(c, " ")
                continue
            ch = combined.get((r, c), lab)
            if ch in MARKS:
                ch = MARK_NAMES[ch]
            if seg is None:
                seg = Segment(r)
            seg.add(c, ch)
        if seg and seg.text:
            out.append(seg)
    return out


def _box_around(labels, row, col):
    """(left, right, top, bottom) of the box that contains (row, col)."""
    cols = len(labels[0])
    left, right = col, col
    while left > 0 and labels[row][left - 1] != "<box>":
        left -= 1
    while right < cols - 1 and labels[row][right + 1] != "<box>":
        right += 1
    # Walk up/down the cursor's own column to the box's top/bottom border
    # (walking the side edge would run into a box stacked below it).
    top = bot = row
    while top > 0 and labels[top - 1][col] != "<box>":
        top -= 1
    while bot < len(labels) - 1 and labels[bot + 1][col] != "<box>":
        bot += 1
    return left, right, top, bot


def has_dialogue_box(labels):
    """The standard message box: full-width borders on rows 12 and 17."""
    def full(r):
        return sum(1 for x in labels[r] if x == "<box>") >= 18
    return len(labels) == 18 and full(12) and full(17)


def cut_selected(sel, segs):
    """A ▶ row can hold several entries (battle menu, name grid). Cut the
    selected one at the first blank whose next column starts a word on
    another row too, i.e. where the menu's columns line up."""
    starts = set()
    for s in segs:
        if s is sel:
            continue
        prev_blank = True
        for col, ch in zip(s.cols, s.chars):
            if ch != " " and prev_blank:
                starts.add(col)
            prev_blank = ch == " "
    for i in range(1, len(sel.chars)):
        if sel.chars[i - 1] == " " and sel.chars[i] != " " and sel.cols[i] in starts:
            return " ".join("".join(sel.chars[:i]).split())
    return sel.text


def fix_shared(text):
    """Choose へ/ヘ, り/リ, っ/ッ… from the nearest real letter on each side
    within the same word (the game draws them with one shared tile)."""
    out = list(text)
    for i, ch in enumerate(text):
        if ch not in SHARED:
            continue
        votes = []
        for step in (-1, 1):
            j = i + step
            while 0 <= j < len(text) and text[j] != " " and text[j] in SHARED:
                j += step
            if 0 <= j < len(text) and text[j] != " ":
                votes.append(is_kata(text[j]) - is_hira(text[j]))
        want_kata = sum(votes) > 0
        if want_kata != is_kata(ch):
            out[i] = SHARED[ch]
    return "".join(out)


def read_labels(labels):
    segs = segments(labels)
    if not segs:
        return ""
    box = has_dialogue_box(labels)
    selected = [s for s in segs if s.selected]
    if selected:
        sel = selected[0]
        l, r, t, b = _box_around(labels, sel.row, sel.c0)
        dialogue = [s for s in segs if box and not s.selected and 13 <= s.row <= 16
                    and not (t <= s.row <= b and s.c1 >= l and s.c0 <= r)]
        mates = [s for s in segs if t <= s.row <= b and s.c1 >= l and s.c0 <= r]
        parts = [s.text for s in dialogue] + [cut_selected(sel, mates)]
    elif box and any(13 <= s.row <= 16 for s in segs):
        parts = [s.text for s in segs if 13 <= s.row <= 16]
    else:
        parts = [s.text for s in segs]
    return fix_shared(" ".join(p for p in parts if p))


def read_image(font, img):
    frame = screen.to_gb_frame(img)
    return read_labels(label_grid(font, screen.tiles(frame)))
