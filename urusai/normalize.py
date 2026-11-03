"""Make game text friendly for Open JTalk.

Open JTalk reads は/へ particles correctly even without the game's word
spaces, so spaces are dropped: the text is read in one natural flow
instead of pausing at every word. Game-specific symbols are mapped too.
"""
import re

_MAP = {
    "‥": "、", "…": "、", "・": "、",
    "♂": "オス", "♀": "メス",
    "×": "かける", "／": "の ", "/": "の ",
    "『": "、", "』": "、", "「": "", "」": "",
    "▶": "", "▷": "", "▼": "",
}


def for_speech(text):
    t = "".join(_MAP.get(ch, ch) for ch in text)
    t = re.sub(r"(?<![0-9])\.|\.(?![0-9])", "", t)  # keep only decimal points
    t = re.sub(r"、+", "、", t)
    t = re.sub(r"(?<=[0-9])[ 　]+(?=[0-9])", "、", t)  # "20/ 20": keep numbers apart
    t = re.sub(r"[ 　]+", "", t).strip("、")
    return t
