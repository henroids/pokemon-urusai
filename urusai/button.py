"""Watch one gamepad button (read-only; the game still sees every press).

RetroArch only fires hotkeys while its "hotkey enable" button (Select on
dArkOS) is held, so the "say it again" button is watched here instead.
No third-party modules: input events are read straight from /dev/input.
"""
import glob
import os
import select
import struct
import sys
import threading
import time

EV_KEY = 0x01
EVENT = struct.Struct("llHHi")  # struct input_event (native long = time fields)

BUTTONS = {
    "A": 0x130, "B": 0x131, "X": 0x133, "Y": 0x134,
    "L1": 0x136, "R1": 0x137, "L2": 0x138, "R2": 0x139,
    "SELECT": 0x13A, "START": 0x13B, "MENU": 0x13C, "L3": 0x13D, "R3": 0x13E,
}
DEBOUNCE = 0.4


def button_code(name):
    """'L2' -> 0x138; also accepts a raw code like '0x138' or '312'. None = off."""
    name = str(name).strip().upper()
    if name in ("", "OFF", "NONE", "NO"):
        return None
    if name in BUTTONS:
        return BUTTONS[name]
    try:
        return int(name, 0)
    except ValueError:
        raise ValueError("unknown button %r (use one of %s)" % (name, " ".join(BUTTONS)))


def has_key(caps_hex, code):
    """Test a bit in a sysfs key capability bitmap ('ffff 0 3ff...' words, MSB first)."""
    words = caps_hex.split()
    bits = 8 * struct.calcsize("l")
    idx = len(words) - 1 - code // bits
    return 0 <= idx < len(words) and bool(int(words[idx], 16) >> (code % bits) & 1)


def devices_with(code, root="/sys/class/input"):
    found = []
    for caps in sorted(glob.glob(os.path.join(root, "event*", "device", "capabilities", "key"))):
        try:
            with open(caps) as f:
                if has_key(f.read(), code):
                    found.append("/dev/input/" + caps.split(os.sep)[-4])
        except OSError:
            pass
    return found


class ButtonWatcher(threading.Thread):
    """Calls on_press() whenever the configured button goes down."""

    def __init__(self, get_button, on_press, log=sys.stderr):
        super().__init__(daemon=True, name="urusai-button")
        self.get_button = get_button  # callable -> current button name (settings can change)
        self.on_press = on_press
        self.log = log
        self.status = "starting"

    def run(self):
        while True:
            try:
                self._watch()
            except Exception as e:  # unplugged device, permissions, bad setting…
                self.status = "error: %s" % e
                self.log.write("urusai: button watcher: %r\n" % e)
            time.sleep(3)

    def _watch(self):
        name = self.get_button()
        code = button_code(name)
        if code is None:
            self.status = "off"
            time.sleep(5)
            return
        paths = devices_with(code)
        if not paths:
            self.status = "no gamepad has button %s" % name
            time.sleep(10)
            return
        fds = [os.open(p, os.O_RDONLY | os.O_NONBLOCK) for p in paths]
        self.status = "watching %s on %s" % (name, ", ".join(paths))
        self.log.write("urusai: %s\n" % self.status)
        last = 0.0
        try:
            while self.get_button() == name:
                ready, _, _ = select.select(fds, [], [], 2.0)
                for fd in ready:
                    data = os.read(fd, EVENT.size * 64)
                    for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                        _, _, etype, ecode, value = EVENT.unpack_from(data, off)
                        if etype == EV_KEY and ecode == code and value == 1:
                            now = time.monotonic()
                            if now - last >= DEBOUNCE:
                                last = now
                                self.on_press()
        finally:
            for fd in fds:
                os.close(fd)

