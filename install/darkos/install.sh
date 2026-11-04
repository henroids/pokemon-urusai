#!/bin/bash
# Pokémon Urusai — installer for dArkOS (RGB20 Pro and other RK3326/RK3566 devices).
# Fully offline: everything it needs is inside this folder.
#
# Run it from a terminal / SSH:      sudo ./install/darkos/install.sh
# or copy "Install Pokemon Urusai.sh" + the PokemonUrusai folder to /roms/ports and run it from Ports.

set -u
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" "$@"

SRC="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/opt/urusai
USER_NAME="${URUSAI_USER:-ark}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CAPTURE_DIR="${URUSAI_CAPTURE_DIR:-/roms/urusai_captures}"
SETTINGS="${URUSAI_SETTINGS:-/roms/urusai_settings.txt}"
TTY=/dev/tty1
LOG="${URUSAI_LOG:-/roms/urusai_install.log}"
: > "$LOG" 2>/dev/null || LOG=/tmp/urusai_install.log

say() { echo "$*"; echo "$*" >> "$LOG"; [ -w "$TTY" ] && echo "$*" > "$TTY"; }
die() { say "ERROR: $*"; say "Please send $LOG"; sleep 12; exit 1; }

say "=== Pokemon Urusai installer ($(date)) ==="
say "source: $SRC  user: $USER_NAME  home: $HOME_DIR"
[ "$(uname -m)" = "aarch64" ] || die "this build is for aarch64 (got $(uname -m))"
command -v python3 >/dev/null || die "python3 not found. Connect Wi-Fi once and run: sudo apt install python3-minimal"
for f in urusai/server.py bin/open_jtalk-aarch64 dic/sys.dic; do
  [ -e "$SRC/$f" ] || die "missing $f in $SRC (use the release zip, it includes the dictionary)"
done
ls "$SRC"/voice/*.htsvoice >/dev/null 2>&1 || die "no voice in $SRC/voice"

say "Copying files to $DEST ..."
mkdir -p "$DEST"
for d in urusai tools bin voice dic font install; do
  [ -d "$SRC/$d" ] && { rm -rf "${DEST:?}/$d"; cp -r "$SRC/$d" "$DEST/"; }
done
cp -f "$SRC"/README.md "$SRC"/INSTALL.md "$SRC"/LICENSES.md "$DEST/" 2>/dev/null
chmod +x "$DEST/bin/open_jtalk-aarch64"
mkdir -p "$CAPTURE_DIR" && chown "$USER_NAME" "$CAPTURE_DIR" 2>/dev/null

# Create the settings file, or refresh its comments/new options keeping your values.
(cd "$DEST" && python3 -m urusai.settings "$SETTINGS") && say "Settings: $SETTINGS"

say "Testing the voice ..."
echo "ポケモン" | "$DEST/bin/open_jtalk-aarch64" -x "$DEST/dic" -m "$DEST/voice/tohoku.htsvoice" -ow /tmp/urusai_test.wav \
  && [ -s /tmp/urusai_test.wav ] || die "open_jtalk test failed"
rm -f /tmp/urusai_test.wav

say "Installing the background service ..."
sed -e "s#@DEST@#$DEST#g" -e "s#@CAPTURE@#$CAPTURE_DIR#g" -e "s#@SETTINGS@#$SETTINGS#g" \
  "$SRC/install/darkos/urusai.service" > /etc/systemd/system/urusai.service
systemctl daemon-reload
systemctl enable urusai.service >/dev/null 2>&1
systemctl restart urusai.service
sleep 2
systemctl is-active --quiet urusai.service || die "service did not start: journalctl -u urusai"

say "Configuring RetroArch (AI Service -> Speech, no pause, keyboard hotkey) ..."
set_cfg() {  # file key value
  local f="$1" k="$2" v="$3"
  if grep -q "^$k *=" "$f"; then sed -i "s#^$k *=.*#$k = \"$v\"#" "$f"; else echo "$k = \"$v\"" >> "$f"; fi
}
found=0
for cfg in "$HOME_DIR/.config/retroarch/retroarch.cfg" "$HOME_DIR/.config/retroarch32/retroarch.cfg"; do
  [ -f "$cfg" ] || continue
  [ -f "$cfg.urusai-backup" ] || cp "$cfg" "$cfg.urusai-backup"
  set_cfg "$cfg" ai_service_enable true
  set_cfg "$cfg" ai_service_mode 1
  set_cfg "$cfg" ai_service_url "http://127.0.0.1:4404/"
  set_cfg "$cfg" ai_service_pause false          # no pause; also needed for auto mode
  # The reader presses F8+F6 on a virtual keyboard to start RetroArch's AI Service:
  # F8 = hotkey enable (Select still works on the pad), F6 = AI Service.
  set_cfg "$cfg" input_enable_hotkey f8
  set_cfg "$cfg" input_ai_service f6
  # By hand: Select + Y starts/stops the reader.
  set_cfg "$cfg" input_ai_service_btn 3
  set_cfg "$cfg" network_cmd_enable false        # was used by v0.3.0
  chown "$USER_NAME" "$cfg"
  say "  updated $cfg"
  found=1
done
[ "$found" = 1 ] || say "  (no retroarch.cfg found — set AI Service by hand, see README)"

# Select + L2 switches the reader off/on: make sure RetroArch has no hotkey there too.
(cd "$DEST" && python3 -m urusai.racfg free "$SETTINGS" \
  "$HOME_DIR/.config/retroarch/retroarch.cfg" "$HOME_DIR/.config/retroarch32/retroarch.cfg") 2>&1 | while read -r l; do say "$l"; done

say ""
say "Done! Start a game: the text is read automatically."
say "L2 = say it again.  Select + L2 = reader off/on."
say "Settings (volume, voice, button): $SETTINGS"
say "(log: $LOG)"
sleep 6
