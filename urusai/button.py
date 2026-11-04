"""Watch one gamepad button (read-only; the game still sees every press).

RetroArch only fires hotkeys while its "hotkey enable" button (Select on
dArkOS) is held, so the "say it again" button is watched here instead.
No third-party modules: input events are read straight from /dev/input.

It also keeps track of which buttons are held, so the virtual keyboard
never presses hotkey-enable while the player holds one: RetroArch would
take that as Select + the button (Select+A = pause, Select+D-pad = fast
forward/rewind on dArkOS).
"""
import contextlib
import fcntl
import glob
import os
import select
import struct
import sys
import threading
import time

EV_KEY = 0x01
EV_ABS = 0x03
ABS_HATS = (0x10, 0x11)          # D-pad on pads that report it as a hat
NOT_GAME_INPUT = {0x13A, 0x13C}   # Select (RetroArch hotkey enable), Menu/Function
EVENT = struct.Struct("llHHi")  # struct input_event (native long = time fields)
EVIOCGRAB = 0x40044590          # _IOW('E', 0x90, int): only we get the pad's events

BUTTONS = {
    "A": 0x130, "B": 0x131, "X": 0x133, "Y": 0x134,
    "L1": 0x136, "R1": 0x137, "L2": 0x138, "R2": 0x139,
    "SELECT": 0x13A, "START": 0x13B, "MENU": 0x13C, "L3": 0x13D, "R3": 0x13E,
}
DEBOUNCE = 0.06       # contact bounce
DOUBLE_TAP = 0.35     # second press within this = double tap


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
    """Calls on_press() whenever the configured button goes down, and
    on_game_input() for any other game button (A, B, Start, D-pad…)."""

    def __init__(self, get_button, on_press, on_game_input=None, log=sys.stderr):
        super().__init__(daemon=True, name="urusai-button")
        self.get_button = get_button  # callable -> current button name (settings can change)
        self.on_press = on_press
        self.on_game_input = on_game_input or (lambda: None)
        self.log = log
        self.status = "starting"
        self.fds = []
        self.held = set()                  # key codes and hat axes that are down
        self.changed = threading.Condition()

    def wait_released(self, timeout):
        """Wait until no button is held. False if one still is after timeout."""
        with self.changed:
            return self.changed.wait_for(lambda: not self.held, timeout)

    @contextlib.contextmanager
    def grabbed(self):
        """Keep new presses away from RetroArch for a moment (EVIOCGRAB)."""
        with self.changed:
            fds = list(self.fds)
        done = []
        try:
            for fd in fds:
                try:
                    fcntl.ioctl(fd, EVIOCGRAB, 1)
                    done.append(fd)
                except OSError:
                    pass
            yield
        finally:
            for fd in done:
                try:
                    fcntl.ioctl(fd, EVIOCGRAB, 0)
                except OSError:
                    pass

    def _track(self, etype, ecode, value):
        if etype == EV_KEY and value in (0, 1):
            key = ecode
        elif etype == EV_ABS and ecode in ABS_HATS:
            key, value = ("hat", ecode), int(value != 0)
        else:
            return
        with self.changed:
            if value:
                self.held.add(key)
            else:
                self.held.discard(key)
            self.changed.notify_all()

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
        with self.changed:
            self.fds, self.held = fds, set()
            self.changed.notify_all()
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
                        self._track(etype, ecode, value)
                        if etype == EV_KEY and ecode == code and value == 1:
                            now = time.monotonic()
                            if now - last >= DEBOUNCE:
                                last = now
                                self.on_press()
                        elif (etype == EV_KEY and value == 1 and ecode not in NOT_GAME_INPUT) or \
                                (etype == EV_ABS and ecode in ABS_HATS and value != 0):
                            self.on_game_input()
        finally:
            with self.changed:
                self.fds, self.held = [], set()
                self.changed.notify_all()
            for fd in fds:
                os.close(fd)


class Taps:
    """Turns presses into single / double taps. A single tap is reported
    DOUBLE_TAP seconds after the press, once no second press came."""

    def __init__(self, on_single, on_double, window=DOUBLE_TAP):
        self.on_single, self.on_double, self.window = on_single, on_double, window
        self.timer = None
        self.lock = threading.Lock()

    def press(self):
        with self.lock:
            if self.timer is not None:  # second tap in time
                self.timer.cancel()
                self.timer = None
                threading.Thread(target=self.on_double, daemon=True).start()
                return
            self.timer = threading.Timer(self.window, self._single)
            self.timer.daemon = True
            self.timer.start()

    def _single(self):
        with self.lock:
            self.timer = None
        self.on_single()
