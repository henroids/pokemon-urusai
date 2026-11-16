"""Watch one gamepad button (read-only; the game still sees every press).

RetroArch only fires hotkeys while its "hotkey enable" button (Select on
dArkOS) is held, so the "say it again" button is watched here instead.
No third-party modules: input events are read straight from /dev/input.

It also keeps track of which buttons are held, so the virtual keyboard
never presses hotkey-enable while the player holds one: RetroArch would
take that as Select + the button (Select+A = pause, Select+D-pad = fast
forward/rewind on dArkOS).

Buttons are named by the standard Linux codes (BUTTONS). Some handhelds send
others: the RG35XXSP's L2 sends the code that means "Menu" elsewhere. Where
EmulationStation keeps a map of each gamepad's buttons (es_input.cfg, as on
Knulli), each pad's codes are translated to the standard ones first.
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
import xml.etree.ElementTree as ET

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
# EmulationStation's button names -> ours. Its "hotkey" is the Menu/Function button.
ES_NAMES = {"a": "A", "b": "B", "x": "X", "y": "Y", "pageup": "L1", "pagedown": "R1",
            "l2": "L2", "r2": "R2", "select": "SELECT", "start": "START", "hotkey": "MENU",
            "l3": "L3", "r3": "R3"}
ES_INPUT = ("/userdata/system/configs/emulationstation/es_input.cfg",   # Knulli: the player's own setup
            "/usr/share/emulationstation/es_input.cfg")                  # …and the built-in ones
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


def combo_codes(spec):
    """'SELECT+L2' -> {0x13A, 0x138}. Empty set = off."""
    names = [n for n in str(spec).replace(" ", "").split("+") if n]
    if not names or names[0].upper() in ("OFF", "NONE", "NO"):
        return frozenset()
    codes = frozenset(button_code(n) for n in names)
    if len(codes) != 2:
        raise ValueError("toggle_combo needs two different buttons, e.g. SELECT+L2")
    return codes


def es_pad_maps(paths=ES_INPUT):
    """{gamepad name: {its key code: standard code}} from EmulationStation's
    es_input.cfg files (the first file that knows a pad wins). {} if there are none."""
    maps = {}
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        for pad in root.iter("inputConfig"):
            name = pad.get("deviceName")
            if pad.get("type") != "joystick" or not name or name in maps:
                continue
            m = {}
            for i in pad.iter("input"):
                ours, code = ES_NAMES.get(i.get("name")), i.get("code")
                if i.get("type") != "button" or not ours or not (code or "").isdigit():
                    continue
                if ours == "MENU" and int(code) in m:
                    continue        # a pad whose hotkey is Select: it stays Select
                m[int(code)] = BUTTONS[ours]
            if m:
                maps[name] = m
    return maps


def has_key(caps_hex, code):
    """Test a bit in a sysfs key capability bitmap ('ffff 0 3ff...' words, MSB first)."""
    words = caps_hex.split()
    bits = 8 * struct.calcsize("l")
    idx = len(words) - 1 - code // bits
    return 0 <= idx < len(words) and bool(int(words[idx], 16) >> (code % bits) & 1)


def devices_with(code, root="/sys/class/input", maps=None):
    """[(event device, its code -> standard code)] of gamepads that have this
    (standard) button. maps: es_pad_maps(); pads not in it use standard codes."""
    maps = es_pad_maps() if maps is None else maps
    found = []
    for caps in sorted(glob.glob(os.path.join(root, "event*", "device", "capabilities", "key"))):
        try:
            with open(caps) as f:
                bits = f.read()
            with open(os.path.join(os.path.dirname(os.path.dirname(caps)), "name")) as f:
                translate = maps.get(f.read().strip(), {})
        except OSError:
            continue
        own = {std: dev for dev, std in translate.items()}.get(code, code)
        if has_key(bits, own):
            found.append(("/dev/input/" + caps.split(os.sep)[-4], translate))
    return found


class ButtonWatcher(threading.Thread):
    """Calls on_press() whenever the configured button goes down,
    on_combo() when both buttons of the combo are down (Select+L2: reader off/on),
    and on_game_input() for any other game button (A, B, Start, D-pad…)."""

    def __init__(self, get_button, on_press, on_game_input=None, log=sys.stderr,
                 get_combo=lambda: "off", on_combo=None):
        super().__init__(daemon=True, name="urusai-button")
        self.get_button = get_button  # callable -> current button name (settings can change)
        self.on_press = on_press
        self.on_game_input = on_game_input or (lambda: None)
        self.get_combo = get_combo
        self.on_combo = on_combo or (lambda: None)
        self.combo_armed = True            # fires once per press of both buttons
        self.code, self.combo, self.last = None, frozenset(), 0.0
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

    def event(self, etype, ecode, value):
        """One input event from the gamepad."""
        self._track(etype, ecode, value)
        if etype == EV_KEY and ecode in self.combo:
            if value == 1 and self.combo <= self.held:
                if self.combo_armed:
                    self.combo_armed = False
                    self.on_combo()
                return                      # part of the combo, not a tap or a game press
            if value == 0 and not self.combo & self.held:
                self.combo_armed = True
        if etype == EV_KEY and ecode == self.code and value == 1:
            now = time.monotonic()
            if now - self.last >= DEBOUNCE:
                self.last = now
                self.on_press()
        elif (etype == EV_KEY and value == 1 and ecode not in NOT_GAME_INPUT) or \
                (etype == EV_ABS and ecode in ABS_HATS and value != 0):
            self.on_game_input()

    def get_combo_codes(self, current):
        """The combo setting now (the old one if the new one is invalid)."""
        try:
            return combo_codes(self.get_combo())
        except ValueError:
            return current

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
        pads = devices_with(code)
        if not pads:
            self.status = "no gamepad has button %s" % name
            time.sleep(10)
            return
        paths = [p for p, _ in pads]
        fds = [os.open(p, os.O_RDONLY | os.O_NONBLOCK) for p in paths]
        translate = dict(zip(fds, (t for _, t in pads)))
        with self.changed:
            self.fds, self.held = fds, set()
            self.changed.notify_all()
        self.status = "watching %s on %s" % (name, ", ".join(
            p + (" (button map from es_input.cfg)" if t else "") for p, t in pads))
        self.log.write("urusai: %s\n" % self.status)
        try:
            combo = combo_codes(self.get_combo())
        except ValueError as e:
            self.log.write("urusai: %s\n" % e)
            combo = frozenset()
        self.code, self.combo, self.last = code, combo, 0.0
        try:
            while self.get_button() == name and self.get_combo_codes(combo) == combo:
                ready, _, _ = select.select(fds, [], [], 2.0)
                for fd in ready:
                    data = os.read(fd, EVENT.size * 64)
                    tr = translate[fd]
                    for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                        etype, ecode, value = EVENT.unpack_from(data, off)[2:]
                        self.event(etype, tr.get(ecode, ecode) if etype == EV_KEY else ecode, value)
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

    def cancel(self):
        """Forget a press that turned out to be part of a combo."""
        with self.lock:
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None

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
