"""Make game text friendly for Open JTalk.

Open JTalk already reads は/へ particles correctly and turns the game's
word spaces into short pauses, so only game-specific symbols need care.
"""
import re

_MAP = {
    "‥": "、", "…": "、", "・": "、",
    "♂": "オス", "♀": "メス",
    "×": "かける", "／": "、", "/": "、",
    "『": "", "』": "", "「": "", "」": "",
    "▶": "", "▷": "", "▼": "",
}


def for_speech(text):
    t = "".join(_MAP.get(ch, ch) for ch in text)
    t = re.sub(r"、+", "、", t)
    t = re.sub(r"[ 　]+", "　", t).strip("　、 ")
    return t
