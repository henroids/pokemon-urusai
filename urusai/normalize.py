"""Make game text friendly for Open JTalk.

Spaces are dropped so the text is read in one natural flow instead of
pausing at every word. The spaces still matter, though: they end the
game's phrases, so a は/へ right before one is a particle (wa/e).
with_particles() reports where those are, and tts.Speaker checks that
Open JTalk really read them as particles (it can be fooled without the
spaces, e.g. かれは -> 枯れ葉 "kareha"). Game-specific symbols are mapped too.
"""
import re

_MAP = {
    "‥": "、", "…": "、", "・": "、",
    "♂": "オス", "♀": "メス",
    "×": "かける", "／": "の ", "/": "の ",
    "『": "、", "』": "、", "「": "", "」": "",
    "▶": "", "▷": "", "▼": "",
}


PARTICLES = {"は": "ワ", "へ": "エ", "わ": "ワ", "え": "エ"}  # particle (or its fix) -> how it must sound
_MARK = {"は": "\ue000", "へ": "\ue001"}       # private-use placeholders while normalising
_UNMARK = {v: k for k, v in _MARK.items()}
_PHRASE_END = re.compile(r"(?<=[\u3041-\u3096\u30a1-\u30fa\u30fcー])([はへ])(?=[ \u3000！？!?、。…‥』」]|$)")
_LAUGH = re.compile(r"^[あえはへっッー！？!?]*$")


def with_particles(text):
    """(text for Open JTalk, indices of phrase-final は/へ that are particles)."""
    words = re.split(r"([ \u3000]+)", text)
    marked = "".join(w if _LAUGH.match(w) and sum(w.count(c) for c in "はへ") > 1
                     else _PHRASE_END.sub(lambda m: _MARK[m.group(1)], w) for w in words)
    t = for_speech(marked)
    hints = [i for i, ch in enumerate(t) if ch in _UNMARK]
    return "".join(_UNMARK.get(ch, ch) for ch in t), hints


def for_speech(text):
    t = "".join(_MAP.get(ch, ch) for ch in text)
    t = re.sub(r"(?<![0-9])\.|\.(?![0-9])", "", t)  # keep only decimal points
    t = re.sub(r"、+", "、", t)
    t = re.sub(r"(?<=[0-9])[ 　]+(?=[0-9])", "、", t)  # "20/ 20": keep numbers apart
    t = re.sub(r"[ 　]+", "", t).strip("、")
    return t
