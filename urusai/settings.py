"""User settings, read from a plain text file on the SD card.

The file is re-read automatically when it changes, so you can edit it on
a PC and the next button press uses the new values.
"""
import os

DEFAULT_PATH = "/roms/urusai_settings.txt"

DEFAULTS = {
    "button": "L2",          # L1 R1 L2 R2 L3 R3 SELECT START, or an evdev code like 0x138; "off" to disable
    "voice": "tohoku",       # a file in voice/: tohoku, tohoku_happy, mei, mei_happy, nitech
    "volume": 200,           # percent; 100 = natural, higher = louder (soft-limited, never clips)
    "speed": 0.95,           # 1.0 = normal speaking speed
    "captures_keep": 50,     # newest screenshots kept in urusai_captures (0 = don't save any)
    "retroarch_port": 55355,
}

TEMPLATE = """\
# Pokémon Urusai settings — edit on your PC, changes apply on the next button press.

# Button that reads the screen aloud (no Select needed):
#   L1 R1 L2 R2 L3 R3 SELECT START, or "off"
button = {button}

# Voice: tohoku (female, default), tohoku_happy, mei (female), mei_happy, nitech (male)
voice = {voice}

# Voice volume in percent. 100 = natural; 150-250 = louder over the music.
volume = {volume}

# Speaking speed. 1.0 = normal, 0.85 = slower, 1.15 = faster.
speed = {speed}

# How many recent screenshots to keep in urusai_captures (each is ~2 KB).
# They're only for fixing misreads. 0 = don't save any.
captures_keep = {captures_keep}
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


if __name__ == "__main__":  # python3 -m urusai.settings PATH  -> write a fresh file
    import sys
    write_template(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH)
