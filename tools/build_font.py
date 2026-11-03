#!/usr/bin/env python3
"""Rebuild font/gen1_jp.json from Henry's reference screenshots.

  build_font.py [FRAMES_DIR] [--out font/gen1_jp.json]

FRAMES_DIR (default tests/frames) holds the numbered reference frames
01.png … 36.png, captured from 青 / Blue. Each entry below says what text
sits where; EXPECT is what each frame must read as (also run by the tests).
Text labels voiced kana's ゛/゜ in the row above automatically; a space
must land on a blank tile, so a misplaced line fails loudly.
"""
import argparse
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from urusai import pngdec, reader, screen  # noqa: E402
from urusai.font import Font  # noqa: E402

SPLIT = {"゙": "゛", "゚": "゜"}

# (shot, row, col, text)  — text runs left to right, one tile per character
TEXT = [
    # name entry, hiragana page
    ("11", 2, 1, "あなたのなまえは？"),
    ("11", 5, 2, "あ か さ た な は ま や ら"),
    ("11", 7, 2, "い き し ち に ひ み ゆ り"),
    ("11", 9, 2, "う く す つ ぬ ふ む よ る"),
    ("11", 11, 2, "え け せ て ね へ め わ れ"),
    ("11", 13, 2, "お こ そ と の ほ も ん ろ"),
    ("11", 15, 2, "ゃ ゅ ょ っ ゛ ゜ ー"),
    ("11", 17, 2, "カナ にゅうりょく"),
    # name entry, katakana page
    ("10", 5, 2, "ア カ サ タ ナ ハ マ ヤ ラ"),
    ("10", 7, 2, "イ キ シ チ ニ ヒ ミ ユ リ"),
    ("10", 9, 2, "ウ ク ス ツ ヌ フ ム ヨ ル"),
    ("10", 11, 2, "エ ケ セ テ ネ ヘ メ ワ レ"),
    ("10", 13, 2, "オ コ ソ ト ノ ホ モ ン ロ"),
    ("10", 15, 2, "ャ ュ ョ ッ ゛ ゜ ー"),
    ("10", 17, 2, "かな にゅうりょく"),
    # title menu, name candidates
    ("03", 2, 2, "さいしょからはじめる"),
    ("03", 4, 2, "せっていを かえる"),
    ("09", 0, 3, "なまえこうほ"),
    ("09", 2, 2, "じぶんできめる"),
    ("09", 4, 2, "ブルー"),
    ("09", 6, 2, "ツネカズ"),
    ("09", 8, 2, "ジャン"),
    # Oak's intro and the lab
    ("04", 14, 1, "この せかいには"), ("04", 16, 1, "ポケット モンスターと よばれる"),
    ("05", 14, 1, "いきもの たちが"), ("05", 16, 1, "いたるところに すんでいる！"),
    ("06", 14, 1, "その ポケモン という いきものを"), ("06", 16, 1, "ひとは ペットに したり"),
    ("07", 16, 1, "しょうぶに つかったり・・・"),
    ("08", 14, 1, "では はじめに きみの なまえを"), ("08", 16, 1, "おしえて もらおう！"),
    ("34", 14, 1, "ふむ・・・"), ("34", 16, 1, "ヘンリー と いうんだな！"),
    ("21", 14, 1, "ミユ『まてよ！ ヘンリー！"), ("21", 16, 1, "せっかく じーさんに"),
    ("35", 14, 1, "ミユ『あっ！ ずるい！"), ("35", 16, 1, "じいさん！ おれにも くれよお！"),
    ("36", 14, 1, "オーキド『まー！"), ("36", 16, 1, "あわてるな ミユ！"),
    # battle
    ("22", 1, 2, "フシギダネ"), ("22", 8, 11, "ゼニガメ"),
    ("22", 14, 11, "たたかう どうぐ"), ("22", 16, 11, "ポケモン にげる"),
    ("22", 10, 12, "20／ 20"),
    ("23", 10, 2, "たいあたり"), ("23", 12, 2, "しっぽをふる"), ("23", 14, 2, "ー"),
    ("23", 13, 14, "35／35"), ("23", 15, 10, "わざタイプ"), ("23", 16, 14, "／ノーマル"),
    ("25", 14, 1, "ダメだ！"), ("25", 16, 1, "しょうぶの さいちゅうに"),
    ("24", 1, 3, "ゼニガメ"), ("24", 14, 1, "ポケモンを えらんで ください"),
    # Pokédex
    ("20", 2, 9, "ゼニガメ"), ("20", 4, 9, "かめのこポケモン"),
    ("20", 6, 9, "たかさ"), ("20", 6, 14, "0.5"), ("20", 8, 9, "おもさ"), ("20", 8, 14, "9.0"),
    ("20", 8, 3, ".007"),
    ("20", 11, 1, "うまれたあと せなかが ふくらみ"),
    ("20", 13, 1, "かたい こうらが できる。くちから"),
    ("20", 15, 1, "きょうりょくな あわを だす。"),
]

# (shot, row, col, label) — single tiles: borders, cursors, symbols
TILES = [
    ("11", 4, 0, "<box>"), ("11", 4, 1, "<box>"), ("11", 4, 19, "<box>"), ("11", 5, 0, "<box>"),
    ("11", 16, 0, "<box>"), ("11", 16, 19, "<box>"), ("11", 17, 1, "<cursor>"),
    ("11", 15, 18, "おわり"),               # the ED button
    ("01", 3, 13, "<ignore>"), ("01", 3, 15, "<ignore>"),  # name underline / caret
    ("04", 12, 0, "<box>"), ("04", 12, 1, "<box>"), ("04", 12, 19, "<box>"), ("04", 13, 0, "<box>"),
    ("04", 17, 0, "<box>"), ("04", 17, 19, "<box>"),
    ("07", 16, 18, "<more>"),
    ("09", 0, 0, "<box>"), ("09", 0, 1, "<box>"), ("09", 0, 10, "<box>"), ("09", 1, 0, "<box>"),
    ("09", 11, 0, "<box>"), ("09", 11, 10, "<box>"),
    ("03", 0, 0, "<box>"), ("03", 0, 14, "<box>"), ("03", 5, 0, "<box>"), ("03", 5, 14, "<box>"),
    ("22", 1, 7, "レベル"), ("22", 1, 8, "5"), ("22", 12, 9, "<box>"), ("22", 17, 9, "<box>"),
    ("22", 13, 9, "<box>"),
    ("23", 8, 0, "<box>"), ("23", 8, 9, "<box>"), ("23", 12, 9, "<box>"), ("23", 12, 19, "<box>"),
    ("23", 17, 0, "<box>"), ("23", 17, 9, "<box>"), ("23", 17, 19, "<box>"),
    ("24", 1, 0, "<cursor>"), ("24", 1, 8, "レベル"),
    ("20", 6, 17, "メートル"), ("20", 8, 17, "キロ"), ("20", 8, 18, "グラム"), ("20", 8, 2, "ナンバー"),
]

# What each frame must read as (checked by tools/build_font.py and the tests).
EXPECT = {
    "01": "はんだくてん",
    "02": "だくてん",
    "03": "さいしょからはじめる",
    "04": "この せかいには ポケット モンスターと よばれる",
    "05": "いきもの たちが いたるところに すんでいる！",
    "06": "その ポケモン という いきものを ひとは ペットに したり",
    "07": "ひとは ペットに したり しょうぶに つかったり・・・",
    "08": "では はじめに きみの なまえを おしえて もらおう！",
    "09": "では はじめに きみの なまえを おしえて もらおう！ じぶんできめる",
    "10": "ア",
    "11": "カナ にゅうりょく",
    "12": "ゃ",
    "13": "だくてん",
    "14": "だくてん",
    "15": "だくてん",
    "16": "だくてん",
    "17": "だくてん",
    "18": "はんだくてん",
    "19": "はんだくてん",
    "20": "ゼニガメ かめのこポケモン たかさ 0.5メートル ナンバー.007 おもさ 9.0キログラム うまれたあと せなかが ふくらみ かたい こうらが できる。くちから きょうりょくな あわを だす。",
    "21": "ミユ『まてよ！ ヘンリー！ せっかく じーさんに",
    "22": "たたかう",
    "23": "たいあたり",
    "24": "ポケモンを えらんで ください ゼニガメ レベル5 20／ 20",
    "25": "ダメだ！ しょうぶの さいちゅうに",
    "26": "だくてん",
    "27": "だくてん",
    "28": "だくてん",
    "29": "だくてん",
    "30": "だくてん",
    "31": "はんだくてん",
    "32": "はんだくてん",
    "33": "はんだくてん",
    "34": "ふむ・・・ ヘンリー と いうんだな！",
    "35": "ミユ『あっ！ ずるい！ じいさん！ おれにも くれよお！",
    "36": "オーキド『まー！ あわてるな ミユ！",
}


def load(frames, name, cache={}):
    key = (frames, name)
    if key not in cache:
        with open(os.path.join(frames, name + ".png"), "rb") as f:
            cache[key] = screen.tiles(screen.to_gb_frame(pngdec.decode(f.read())))
    return cache[key]


def build(frames, log=print):
    """Label every tile listed in TEXT/TILES and return the Font."""
    font = Font()
    seen = {}

    def put(tile, label, where):
        old = seen.get(tile)
        if old and old[0] != label and reader.SHARED.get(old[0]) != label:
            log("conflict: %s says %r, %s says %r" % (old[1], old[0], where, label))
        seen.setdefault(tile, (label, where))
        font.add(tile, seen[tile][0])

    for shot, r, c, text in TEXT:
        g = load(frames, shot)
        for ch in text:
            where = "%s@%d:%d" % (shot, r, c)
            if ch == " ":
                if g[r][c]:
                    raise ValueError("%s should be blank" % where)
                c += 1
                continue
            d = unicodedata.normalize("NFD", ch)
            if not g[r][c]:
                raise ValueError("%s is blank but text says %r" % (where, ch))
            put(g[r][c], d[0], where)
            if len(d) > 1:
                if not g[r - 1][c]:
                    raise ValueError("%s: no mark above %r" % (where, ch))
                put(g[r - 1][c], SPLIT[d[1]], where + "^")
            c += 1
    for shot, r, c, label in TILES:
        g = load(frames, shot)
        if not g[r][c]:
            raise ValueError("%s@%d:%d is blank" % (shot, r, c))
        put(g[r][c], label, "%s@%d:%d" % (shot, r, c))
    return font


def readings(font, frames):
    """{frame name: what the reader says}."""
    names = sorted(n[:-4] for n in os.listdir(frames) if n.endswith(".png"))
    return {n: reader.read_labels(reader.label_grid(font, load(frames, n))) for n in names}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("frames", nargs="?", default=os.path.join(ROOT, "tests", "frames"))
    p.add_argument("--out", default=os.path.join(ROOT, "font", "gen1_jp.json"))
    a = p.parse_args()
    font = build(a.frames)
    font.save(a.out)
    print("font: %d tiles -> %s" % (len(font.table), a.out))
    bad = 0
    for n, got in readings(font, a.frames).items():
        want = EXPECT.get(n)
        flag = "" if want is None else ("  ok" if got == want else "  MISMATCH (want %r)" % want)
        bad += bool(want is not None and got != want)
        print("%s: %s%s" % (n, got, flag))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
