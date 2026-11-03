"""Read the kana on a Gen 1 (Japanese) screen.

Gen 1 Japanese text sits on the 8x8 tile grid. Dakuten/handakuten (゛/゜)
are drawn in the tile *above* the kana they modify, so we combine a mark
with the kana directly below it.

analyze() describes a screen as a Reading:
  * dialogue — the lines of the message box at the bottom (rows 13-16);
  * options / selected — the entries of the menu holding the ▶ cursor;
  * other — every text line, for screens with neither (e.g. the Pokédex).
read_labels() flattens that to one string (dialogue, then the selected
entry), which is what the regression frames record.
"""
import unicodedata
from dataclasses import dataclass, field

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


def word_starts(seg):
    """Columns where a word starts in a segment."""
    starts, prev_blank = [], True
    for col, ch in zip(seg.cols, seg.chars):
        if ch != " " and prev_blank:
            starts.append(col)
        prev_blank = ch == " "
    return starts


def split_entries(seg, others):
    """Cut a menu row into entries at blanks where the next column starts a
    word on another row too (the menu's columns line up), e.g. the battle
    menu's たたかう|どうぐ or the name grid's single kana."""
    aligned = {col for o in others if o is not seg for col in word_starts(o)}
    entries, cur = [], []
    for i, (col, ch) in enumerate(zip(seg.cols, seg.chars)):
        if i and ch != " " and seg.chars[i - 1] == " " and col in aligned and cur:
            entries.append(cur)
            cur = []
        cur.append((col, ch))
    if cur:
        entries.append(cur)
    out = []
    for e in entries:
        text = " ".join("".join(ch for _, ch in e).split())
        first = next((col for col, ch in e if ch != " "), None)
        if text:
            out.append((seg.row, first, text))
    return out


EMPTY_ENTRIES = {"ー", "-", "－"}  # unused move slots


@dataclass
class Reading:
    dialogue: list = field(default_factory=list)   # message box lines, top to bottom
    options: list = field(default_factory=list)    # menu entries in reading order
    selected: int = None                           # index into options
    other: list = field(default_factory=list)      # all text lines (no box, no menu)
    more: bool = False                             # ▼ shown: the box waits for A

    @property
    def kind(self):
        return "menu" if self.selected is not None else "dialogue" if self.dialogue else \
            "other" if self.other else "none"

    @property
    def selected_text(self):
        return self.options[self.selected] if self.selected is not None else ""

    def flat(self):
        """One string: dialogue + selected entry, or the box, or everything."""
        if self.selected is not None:
            parts = self.dialogue + [self.selected_text]
        else:
            parts = self.dialogue or self.other
        return fix_shared(" ".join(p for p in parts if p))


def analyze(labels):
    segs = segments(labels)
    r = Reading()
    if not segs:
        return r
    box = has_dialogue_box(labels)
    sel = next((s for s in segs if s.selected), None)
    menu = []
    if sel is not None:
        l, rr, t, b = _box_around(labels, sel.row, sel.c0)
        menu = [s for s in segs if t <= s.row <= b and s.c1 >= l and s.c0 <= rr]
        entries = []
        for s in menu:
            entries.extend(split_entries(s, menu))
        entries.sort()
        first = next((c for c, ch in zip(sel.cols, sel.chars) if ch != " "), None)
        kept = [e for e in entries if e[2] not in EMPTY_ENTRIES or (e[0], e[1]) == (sel.row, first)]
        r.options = [fix_shared(e[2]) for e in kept]
        r.selected = next((i for i, e in enumerate(kept) if (e[0], e[1]) == (sel.row, first)), None)
        if r.selected is None and r.options:
            r.selected = 0
    if box:
        rows = {}
        for s in segs:
            if 13 <= s.row <= 16 and s not in menu:
                rows.setdefault(s.row, []).append(s.text)
        r.dialogue = [fix_shared(" ".join(rows[k])) for k in sorted(rows)]
        r.more = any(labels[row][c] == "<more>" for row in range(13, 17) for c in range(len(labels[0])))
    if r.selected is None and not r.dialogue:
        r.other = [fix_shared(s.text) for s in segs]
    return r


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
    return analyze(labels).flat()


def read_image(font, img):
    return analyze_image(font, img).flat()


def analyze_image(font, img):
    frame = screen.to_gb_frame(img)
    return analyze(label_grid(font, screen.tiles(frame)))
