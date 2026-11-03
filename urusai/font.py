"""Tile font: maps 8x8 one-bit tiles to kana / marks / UI symbols.

Labels:
  single kana or punctuation   e.g. "か", "ー", "！"
  "゛" / "゜"                   dakuten / handakuten (drawn in the row above)
  "<box>"                       text-box / menu border
  "<cursor>"                    filled ▶ (current selection)
  "<cursor_off>"                hollow ▷
  "<more>"                      ▼ "press A" arrow
  "<ignore>"                    anything to skip silently
"""
import json
import os

MAX_DIST = 3  # tolerate a few bad pixels from screenshot scaling


def _popcount(v):
    return bin(v).count("1")


class Font:
    def __init__(self, table=None):
        self.table = dict(table or {})  # int -> label
        self._cache = {}

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls({int(k, 16): v for k, v in data.get("tiles", {}).items()})

    def save(self, path):
        data = {"tiles": {"%016x" % k: v for k, v in sorted(self.table.items(), key=lambda kv: kv[1])}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")

    def add(self, tile, label):
        self.table[tile] = label
        self._cache.clear()

    def match(self, tile):
        """Label for a tile, ' ' for blank, or None if unknown."""
        if tile == 0:
            return " "
        hit = self.table.get(tile)
        if hit is not None:
            return hit
        if tile in self._cache:
            return self._cache[tile]
        best, best_d, tie = None, MAX_DIST + 1, False
        for k, lab in self.table.items():
            d = _popcount(k ^ tile)
            if d < best_d:
                best, best_d, tie = lab, d, False
            elif d == best_d and lab != best:
                tie = True
        res = None if (best is None or tie) else best
        self._cache[tile] = res
        return res
