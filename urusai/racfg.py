"""Free a gamepad button from RetroArch's hotkeys (used by the installer).

The reader's on/off combo is Select + L2. Select is RetroArch's hotkey
enable, so if RetroArch also has a hotkey on L2 (rewind, a save state…)
both would happen. This unbinds those hotkeys in retroarch.cfg and the
gamepad autoconfig files, and writes what it changed to a .urusai-freed
file next to each one, so the uninstaller can put them back.

    python3 -m urusai.racfg free SETTINGS RETROARCH_CFG...   # the combo's button, + autoconfig files
    python3 -m urusai.racfg restore RETROARCH_CFG...
"""
import glob
import os
import re
import sys

# RetroPad buttons: these are the pad's own mapping, never hotkeys.
PAD = {"b", "y", "select", "start", "up", "down", "left", "right", "a", "x",
       "l", "r", "l2", "r2", "l3", "r3"}
NOT_HOTKEYS = {"enable_hotkey", "ai_service"}   # ai_service_btn is the reader's own Select+Y
LINE = re.compile(r'^\s*input_(\w+?)_btn\s*=\s*"?([^"\s]*)"?\s*$')


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def button_number(lines, button):
    """The pad's number for a RetroPad button, e.g. l2 -> '6' (None if not set)."""
    for line in lines:
        m = LINE.match(line)
        if m and m.group(1) in (button, "player1_" + button):
            return m.group(2)
    return None


def hotkeys_on(lines, number):
    """[(index, name)] of hotkey binds that use this button number."""
    out = []
    for i, line in enumerate(lines):
        m = LINE.match(line)
        if not m or m.group(2) != number:
            continue
        name = m.group(1)
        if re.match(r"player\d+_", name) or name in PAD or name in NOT_HOTKEYS:
            continue
        out.append((i, name))
    return out


def free(button, paths, log=print):
    """Unbind every hotkey on `button` in these files. Returns the names freed."""
    files = {p: read(p) for p in paths if os.path.isfile(p)}
    numbers = {n for n in (button_number(lines, button) for lines in files.values()) if n}
    freed = []
    for path, lines in files.items():
        own = button_number(lines, button)
        hits = [(i, name) for n in ({own} if own else numbers) for i, name in hotkeys_on(lines, n)]
        if not hits:
            continue
        with open(path + ".urusai-freed", "a", encoding="utf-8") as f:
            for i, name in hits:
                f.write(lines[i] + "\n")
                lines[i] = 'input_%s_btn = "nul"' % name
                freed.append(name)
                log("  Select+%s was RetroArch's %s: turned off (%s)" % (button.upper(), name, os.path.basename(path)))
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return freed


def restore(paths):
    for path in paths:
        saved = path + ".urusai-freed"
        if not (os.path.isfile(path) and os.path.isfile(saved)):
            continue
        old = {LINE.match(x).group(1): x for x in read(saved) if LINE.match(x)}
        lines = [old.get(LINE.match(x).group(1), x) if LINE.match(x) else x for x in read(path)]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.unlink(saved)


def with_autoconfig(cfgs):
    """retroarch.cfg files plus the gamepad autoconfig files they use."""
    out = []
    for cfg in cfgs:
        if not os.path.isfile(cfg):
            continue
        out.append(cfg)
        dirs = [os.path.join(os.path.dirname(cfg), "autoconfig")]
        for line in read(cfg):
            m = re.match(r'^\s*joypad_autoconfig_dir\s*=\s*"([^"]*)"', line)
            if m and m.group(1) and m.group(1) != "default":
                dirs.append(os.path.expanduser(m.group(1)))
        for d in dirs:
            out += sorted(glob.glob(os.path.join(d, "**", "*.cfg"), recursive=True))
    return list(dict.fromkeys(out))


def combo_button(settings_path):
    """'SELECT+L2' -> 'l2': the button besides Select (None if Select isn't in it)."""
    from .settings import Settings
    names = [n.strip().lower() for n in str(Settings(settings_path)["toggle_combo"]).split("+")]
    rest = [n for n in names if n != "select"]
    return rest[0] if "select" in names and len(rest) == 1 else None


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "free":
        button = combo_button(args[0])
        if button:
            free(button, with_autoconfig(args[1:]))
    elif cmd == "restore":
        restore(with_autoconfig(args))
