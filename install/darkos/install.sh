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
TTY=/dev/tty1

say() { echo "$*"; [ -w "$TTY" ] && echo "$*" > "$TTY"; }
die() { say "ERROR: $*"; sleep 8; exit 1; }

say "=== Pokemon Urusai installer ==="
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
cp -f "$SRC"/README.md "$SRC"/LICENSES.md "$DEST/" 2>/dev/null
chmod +x "$DEST/bin/open_jtalk-aarch64"
mkdir -p "$CAPTURE_DIR" && chown "$USER_NAME" "$CAPTURE_DIR" 2>/dev/null

say "Testing the voice ..."
echo "ポケモン" | "$DEST/bin/open_jtalk-aarch64" -x "$DEST/dic" -m "$(ls "$DEST"/voice/*.htsvoice | head -1)" -ow /tmp/urusai_test.wav \
  && [ -s /tmp/urusai_test.wav ] || die "open_jtalk test failed"
rm -f /tmp/urusai_test.wav

say "Installing the background service ..."
sed -e "s#@DEST@#$DEST#g" -e "s#@USER@#$USER_NAME#g" -e "s#@CAPTURE@#$CAPTURE_DIR#g" \
  "$SRC/install/darkos/urusai.service" > /etc/systemd/system/urusai.service
systemctl daemon-reload
systemctl enable urusai.service >/dev/null 2>&1
systemctl restart urusai.service
sleep 2
systemctl is-active --quiet urusai.service || die "service did not start: journalctl -u urusai"

say "Configuring RetroArch (AI Service -> Speech, localhost) ..."
set_cfg() {  # file key value
  local f="$1" k="$2" v="$3"
  if grep -q "^$k *=" "$f"; then sed -i "s#^$k *=.*#$k = \"$v\"#" "$f"; else echo "$k = \"$v\"" >> "$f"; fi
}
found=0
for cfg in "$HOME_DIR/.config/retroarch/retroarch.cfg" "$HOME_DIR/.config/retroarch32/retroarch.cfg"; do
  [ -f "$cfg" ] || continue
  cp -n "$cfg" "$cfg.urusai-backup"
  set_cfg "$cfg" ai_service_enable true
  set_cfg "$cfg" ai_service_mode 1
  set_cfg "$cfg" ai_service_url "http://127.0.0.1:4404/"
  set_cfg "$cfg" ai_service_pause true
  chown "$USER_NAME" "$cfg"
  say "  updated $cfg"
  found=1
done
[ "$found" = 1 ] || say "  (no retroarch.cfg found — set AI Service by hand, see README)"

say ""
say "Done! Last step, in RetroArch (once):"
say "  Settings > Input > Hotkeys > AI Service  -> pick a button"
say "  Main Menu > Configuration File > Save Current Configuration"
sleep 6
