"""A tiny virtual keyboard (Linux uinput), used to press RetroArch's
AI Service hotkey for us.

dArkOS only fires RetroArch hotkeys while the "hotkey enable" button is
held. The installer binds hotkey-enable to F8 and AI Service to F6 on the
keyboard (Select / Select+Y on the pad still work), so tapping F8+F6 here
starts reading without anyone holding Select. Stdlib only.
"""
import fcntl
import os
import struct
import time

EV_SYN, EV_KEY = 0x00, 0x01
KEY_F6, KEY_F8 = 64, 66
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EVENT = struct.Struct("llHHi")
BUS_VIRTUAL = 0x06


class VirtualKeyboard:
    def __init__(self, keys=(KEY_F6, KEY_F8), name=b"urusai-keys", path="/dev/uinput"):
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

    def chord(self, keys=(KEY_F8, KEY_F6), hold=0.1):
        """Press keys in order, hold, release in reverse (like a person would)."""
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
