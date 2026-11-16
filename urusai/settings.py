"""User settings, read from a plain text file on the SD card.

The file is re-read automatically when it changes, so you can edit it on
a PC and the next button press uses the new values.
"""
import os

DEFAULT_PATH = "/roms/urusai_settings.txt"

DEFAULTS = {
    "auto_read": "on",       # read new dialogue and menu choices automatically
    "autostart": "on",       # switch the reader on by itself when a game starts
    "button": "L2",          # tap = say it again, double tap = reader off/on: L1 R1 L2 R2 L3 R3 SELECT START, or off
    "toggle_combo": "SELECT+L2",  # press both together: reader off/on, shown on screen
    "sound_cues": "on",      # sounds when a menu opens/closes and at the first/last option
    "interrupt": "on",       # stop talking when a game button is pressed
    "menu_position": "off",  # say 「2ばんめ」 after the selected option
    "voice": "tsukuyomi",    # dialogue voice: tsukuyomi (natural), or a file in voice/: tohoku, mei, nitech…
    "menu_voice": "tohoku-4",  # voice for menu options (a voice name, optionally +/- semitones)
    "volume": 220,           # percent; 100 = natural, higher = louder (soft-limited, never clips)
    "speed": 0.95,           # 1.0 = normal speaking speed
    "natural_speed": 0.85,   # the natural voice's speed on top of that (0.85 = 15% slower)
    "option_pause": 300,     # milliseconds of silence between menu options / choices
    "captures_keep": 50,     # newest spoken screens kept in urusai_captures (0 = don't save any)
    "gba_learn": "on",       # GBA games: also keep a screen now and then when nothing could be read
}

TEMPLATE = """\
# Pokémon Urusai settings — edit on your PC, changes apply on the next button press.

# Read new text and menu choices automatically: on / off
auto_read = {auto_read}

# Switch the reader on by itself a few seconds after a game starts: on / off
# (otherwise press the button, or Select + Y, once per game)
autostart = {autostart}

# Button (no Select needed): tap = say it again, double tap = reader off/on.
#   L1 R1 L2 R2 L3 R3 SELECT START, or off
button = {button}

# Press these two together to switch the reader off/on. 「よみあげ オフ／オン」
# is said and shown on screen. Two buttons joined by +, e.g. SELECT+L2, or off.
# (With SELECT, re-run the installer after changing it: it frees the other
# button from RetroArch's Select hotkeys.)
toggle_combo = {toggle_combo}

# Sounds when a menu opens or closes, and at the first/last option: on / off
# (the pip after the selected option is always on; はい/いいえ have no sound)
sound_cues = {sound_cues}

# Say the position after the selected option, e.g. 「2ばんめ」: on / off
menu_position = {menu_position}

# Voices. tsukuyomi is the natural one (piper-plus). It takes a few seconds to
# make a new line, so a line is said in the standard voice (tohoku) the first
# time and in the natural voice whenever it comes up again. If it isn't
# installed, tohoku is used. To go back to the old behaviour: voice = tohoku
# Standard voices (instant): tohoku, tohoku_happy, mei, mei_happy, mei_bashful (female), nitech (male).
# Add +N or -N to make one higher or lower in semitones, e.g. mei+3 or tohoku-4.
# (menu_voice = tsukuyomi-4 also works, but runs a second copy of the voice: more memory.)
voice = {voice}
menu_voice = {menu_voice}

# Stop talking whenever you press a game button (A, B, Start, D-pad), and read what's new: on / off
interrupt = {interrupt}

# Voice volume in percent. 100 = natural; 150-250 = louder over the music.
volume = {volume}

# Speaking speed. 1.0 = normal, 0.85 = slower, 1.15 = faster.
speed = {speed}

# The natural voice (tsukuyomi) only: its speed compared with the setting above.
# 0.85 = 15% slower, 1.0 = the same as the standard voice.
natural_speed = {natural_speed}

# Pause between menu options and choices, in milliseconds (text itself is read without pauses).
option_pause = {option_pause}

# How many recently read screens to keep in urusai_captures (each is ~2 KB).
# They're only for fixing misreads; the oldest are deleted. 0 = don't save any.
captures_keep = {captures_keep}

# GBA games are new: while this is on, a screen where nothing could be read is
# kept in urusai_captures every 10 seconds or so (within the limit above), so
# missing letters and menus can be added. Switch it off once GBA reads well.
gba_learn = {gba_learn}
"""


def _coerce(key, value):
    default = DEFAULTS[key]
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


class Settings:
    def __init__(self, path=None):
        self.path = path or os.environ.get("URUSAI_SETTINGS", DEFAULT_PATH)
        self._mtime = None
        self.values = dict(DEFAULTS)
        self.reload()

    def reload(self):
        """Re-read the file if it changed. Returns True if values changed."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            mtime = None
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        values = dict(DEFAULTS)
        if mtime is not None:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if "=" not in line:
                        continue
                    key, value = (x.strip() for x in line.split("=", 1))
                    if key in DEFAULTS:
                        values[key] = _coerce(key, value)
        changed = values != self.values
        self.values = values
        return changed

    def __getitem__(self, key):
        return self.values[key]


def write_template(path, overrides=None):
    """Create a commented settings file (used by the installer)."""
    values = dict(DEFAULTS, **(overrides or {}))
    with open(path, "w", encoding="utf-8") as f:
        f.write(TEMPLATE.format(**values))


# Old defaults that were never changed by hand are moved to the new default.
MIGRATIONS = {"menu_voice": {"nitech": "tohoku-4"},
              "voice": {"tohoku": "tsukuyomi"},          # the natural voice became the default
              "toggle_combo": {"L1+R1": "SELECT+L2"},   # L1/R1 change the shader on dArkOS
              "volume": {200: 220}}                     # 10% louder (Henry, 2026-11-17)


def upgrade(path):
    """Rewrite the file with the current comments and options, keeping the user's values."""
    current = Settings(path).values if os.path.exists(path) else {}
    for key, moves in MIGRATIONS.items():
        if current.get(key) in moves:
            current[key] = moves[current[key]]
    write_template(path, current)


if __name__ == "__main__":  # python3 -m urusai.settings PATH  -> create or upgrade the file
    import sys
    upgrade(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH)
