"""A tiny virtual keyboard (Linux uinput), used to press RetroArch's
AI Service hotkey for us.

RetroArch only fires hotkeys while its "hotkey enable" key is held. On
dArkOS the installer binds hotkey-enable to F8 and AI Service to F6 on the
keyboard (Select / Select+Y on the pad still work); Knulli always uses
Shift for hotkey-enable, and its installer binds AI Service to F9. Tapping
the pair here starts reading without anyone holding a button. Stdlib only.
"""
import fcntl
import os
import struct
import time

EV_SYN, EV_KEY = 0x00, 0x01
KEYS = {"shift": 42, "f6": 64, "f8": 66, "f9": 67, "f10": 68, "f11": 87}


def key_codes(spec):
    """'f8+f6' -> (66, 64): hotkey enable first, then AI Service."""
    try:
        codes = tuple(KEYS[k.strip().lower()] for k in spec.split("+"))
    except KeyError as e:
        raise ValueError("unknown key %s (use %s)" % (e, ", ".join(KEYS)))
    if len(codes) != 2:
        raise ValueError("keys must be two keys joined by +, e.g. f8+f6")
    return codes
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EVENT = struct.Struct("llHHi")
BUS_VIRTUAL = 0x06


class VirtualKeyboard:
    def __init__(self, keys=(66, 64), name=b"urusai-keys", path="/dev/uinput"):
        self.keys = tuple(keys)
        self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            for k in keys:
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, k)
            # legacy struct uinput_user_dev: name[80], input_id (4 x u16), ff_effects_max,
            # then absmax/absmin/absfuzz/absflat (4 x 64 x s32)
            dev = struct.pack("80sHHHHi", name, BUS_VIRTUAL, 0x1209, 0x5552, 1, 0) + bytes(4 * 64 * 4)
            os.write(self.fd, dev)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
        except OSError:
            os.close(self.fd)
            raise
        time.sleep(0.2)  # let udev/RetroArch notice the new device

    def _emit(self, etype, code, value):
        os.write(self.fd, EVENT.pack(0, 0, etype, code, value))

    def chord(self, hold=0.1):
        """Press the keys in order, hold, release in reverse (like a person would)."""
        keys = self.keys
        for k in keys:
            self._emit(EV_KEY, k, 1)
            self._emit(EV_SYN, 0, 0)
            time.sleep(0.03)
        time.sleep(hold)
        for k in reversed(keys):
            self._emit(EV_KEY, k, 0)
            self._emit(EV_SYN, 0, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
