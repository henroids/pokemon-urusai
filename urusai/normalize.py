"""Make game text friendly for Open JTalk.

Spaces are dropped so the text is read in one natural flow instead of
pausing at every word. The spaces still matter, though: they end the
game's phrases, so a は/へ right before one is a particle (wa/e).
with_particles() reports where those are, and tts.Speaker checks that
Open JTalk really read them as particles (it can be fooled without the
spaces, e.g. かれは -> 枯れ葉 "kareha").

Numbers: Open JTalk only applies Japanese counter sound changes when the
counter is written in kanji (3本 さんぼん, 1個 いっこ, 6匹 ろっぴき), but the
game writes counters in kana (1こ would be read いちこ). So a kana counter
right after a number becomes its kanji, and game number formats are put
into words: HP 15/20 -> 20のうち15, No.007 -> 7番, 9.0kg -> 9キログラム,
×3 -> 3個, 12:34 (play time) -> 12時間34分.
"""
import re

_MAP = {
    "‥": "、", "…": "、", "・": "、",
    "♂": "オス", "♀": "メス",
    "『": "、", "』": "、", "「": "", "」": "",
    "▶": "", "▷": "", "▼": "",
}

# kana counter -> kanji, so Open JTalk says いっこ / さんびき / はっぽん / じゅっかい …
# (longest first; only when the counter really ends the word, see _AFTER)
COUNTERS = [
    ("ばんめ", "番目"), ("じかん", "時間"), ("びょう", "秒"),
    ("ひき", "匹"), ("びき", "匹"), ("ぴき", "匹"),
    ("ほん", "本"), ("ぼん", "本"), ("ぽん", "本"),
    ("ふん", "分"), ("ぷん", "分"),
    ("かい", "回"), ("ばん", "番"), ("まい", "枚"), ("にん", "人"), ("ばい", "倍"),
    ("えん", "円"), ("こ", "個"), ("ど", "度"), ("つ", "つ"),
]
# what may follow a counter: end, space/punctuation, a particle, or katakana/kanji
_AFTER = r"(?=$|[ 　、。！？!?…‥・』」）\)]|[をがはにのもでとやへ]|め|まで|だけ|ずつ|[゠-ヿ一-鿿])"
_COUNTER_RE = re.compile(r"(?<=[0-9])(" + "|".join(k for k, _ in COUNTERS) + r")" + _AFTER)
_COUNTER_KANJI = dict(COUNTERS)


def numbers(t):
    """Put the game's number formats into words Open JTalk reads correctly."""
    t = re.sub(r"(\d+)\s*[／/]\s*(\d+)", r"\2のうち\1", t)                # HP/PP 15/20
    t = re.sub(r"ナンバー\s*\.?\s*0*(\d+)", r"\1番", t)                   # Pokédex No.007
    t = re.sub(r"(\d+)\s*[:：]\s*(\d\d)(?!\d)", r"\1時間\2分", t)          # play time 12:34
    t = re.sub(r"[×xX]\s*(\d+)", r"\1個", t)                               # item count ×3
    t = re.sub(r"[¥￥]\s*(\d+)", r"\1円", t)                                # money ¥3000
    t = re.sub(r"(\d+)\.0(?!\d)", r"\1", t)                                # 9.0 -> 9
    t = re.sub(r"(?<![\d.])0+(\d)", r"\1", t)                              # 007 -> 7
    t = _COUNTER_RE.sub(lambda m: _COUNTER_KANJI[m.group(1)], t)           # 1こ -> 1個
    return t


PARTICLES = {"は": "ワ", "へ": "エ", "わ": "ワ", "え": "エ"}  # particle (or its fix) -> how it must sound
_MARK = {"は": "", "へ": ""}       # private-use placeholders while normalising
_UNMARK = {v: k for k, v in _MARK.items()}
_PHRASE_END = re.compile(r"(?<=[ぁ-ゖァ-ヺーー])([はへ])(?=[ 　！？!?、。…‥』」]|$)")
_LAUGH = re.compile(r"^[あえはへっッー！？!?]*$")


def with_particles(text):
    """(text for Open JTalk, indices of phrase-final は/へ that are particles)."""
    words = re.split(r"([ 　]+)", text)
    marked = "".join(w if _LAUGH.match(w) and sum(w.count(c) for c in "はへ") > 1
                     else _PHRASE_END.sub(lambda m: _MARK[m.group(1)], w) for w in words)
    t = for_speech(marked)
    hints = [i for i, ch in enumerate(t) if ch in _UNMARK]
    return "".join(_UNMARK.get(ch, ch) for ch in t), hints


def for_speech(text):
    t = numbers(text)
    t = "".join(_MAP.get(ch, ch) for ch in t)
    t = re.sub(r"(?<![0-9])\.|\.(?![0-9])", "", t)  # keep only decimal points
    t = re.sub(r"、+", "、", t)
    t = re.sub(r"(?<=[0-9])[ 　]+(?=[0-9])", "、", t)  # two numbers in a row stay apart
    t = re.sub(r"[ 　]+", "", t).strip("、")
    return t
