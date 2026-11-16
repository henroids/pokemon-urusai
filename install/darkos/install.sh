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

# The natural voice (piper-plus): the program comes with this package, the voice
# itself (つくよみちゃん, about 40 MB) is fetched once, or copied from the SD card.
NEURAL="$DEST/neural"; MODEL_DIR="$NEURAL/model"; PP="$NEURAL/aarch64/bin/piper-plus"
if [ -d "$SRC/neural/aarch64" ]; then
  mkdir -p "$MODEL_DIR"
  rm -rf "$NEURAL/aarch64"; cp -r "$SRC/neural/aarch64" "$NEURAL/"; chmod +x "$PP"
  pp() { LD_LIBRARY_PATH="$NEURAL/aarch64/lib" OPENJTALK_DICTIONARY_PATH="$DEST/dic" PIPER_PLUS_AUTO_DOWNLOAD_DICT=0 "$PP" "$@"; }
  have_model() { find "$MODEL_DIR" -name '*tsukuyomi*.onnx' -size +1M 2>/dev/null | grep -q .; }
  if ! have_model; then
    for d in "$SRC/neural/model" "$SRC/../tsukuyomi" /roms/tsukuyomi /roms2/tsukuyomi /roms/ports/tsukuyomi; do
      ls "$d"/*tsukuyomi*.onnx >/dev/null 2>&1 || continue
      say "Natural voice: copying it from $d ..."
      cp "$d"/*.onnx "$d"/*.json "$MODEL_DIR/" 2>/dev/null
      break
    done
  fi
  if ! have_model; then
    say "Natural voice: downloading it (needs Wi-Fi, about 40 MB, a few minutes) ..."
    timeout 900 env LD_LIBRARY_PATH="$NEURAL/aarch64/lib" "$PP" --download-model tsukuyomi --model-dir "$MODEL_DIR" >> "$LOG" 2>&1
  fi
  if have_model; then
    M="$(find "$MODEL_DIR" -name '*tsukuyomi*.onnx' | head -1)"
    t0=$(date +%s.%N)
    if pp -q -m "$M" -l ja -t "ポケモンの せかいへ ようこそ" -f /tmp/urusai_neural.wav >> "$LOG" 2>&1 && [ -s /tmp/urusai_neural.wav ]; then
      say "Natural voice: ready ($(echo "$(date +%s.%N) $t0" | awk '{printf "%.1f", $1-$2}') s to start and say a test line)"
    else
      say "Natural voice: did not run on this system; the standard voice is used. (details in $LOG)"
    fi
    rm -f /tmp/urusai_neural.wav
  else
    say "Natural voice: not installed (no Wi-Fi?). The standard voice is used until it is."
    say "  Either connect Wi-Fi and run this installer again, or see INSTALL.md, 'Natural voice'."
  fi
fi

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
