#!/bin/bash
# Pokémon Urusai — installer for Knulli (RG35XXSP and other handhelds; Batocera-based).
# Fully offline: everything it needs is inside this folder.
#
# Run it from Ports: put "Install Pokemon Urusai.sh" and the PokemonUrusai folder in
# /userdata/roms/ports, update the game lists, and start it from Ports.
# Or over SSH:  bash /userdata/roms/ports/PokemonUrusai/install/knulli/install.sh
#
# Knulli rewrites RetroArch's settings at every game start, so the reader's
# settings go in batocera.conf as global.retroarch.* lines, which Knulli
# applies last. Everything else lives in /userdata, which survives updates.

set -u
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
DEST=/userdata/system/urusai
CONF=/userdata/system/batocera.conf
SERVICE=/userdata/system/services/urusai
CAPTURE_DIR="${URUSAI_CAPTURE_DIR:-/userdata/roms/urusai_captures}"
SETTINGS="${URUSAI_SETTINGS:-/userdata/roms/urusai_settings.txt}"
LOG="${URUSAI_LOG:-/userdata/roms/urusai_install.log}"
MARK="# Pokemon Urusai (screen reader)"
: > "$LOG" 2>/dev/null || LOG=/tmp/urusai_install.log

say() { echo "$*"; echo "$*" >> "$LOG"; }
# Ports show no text, so the installer also says how it went, out loud.
speak() {
  local w=/tmp/urusai_say.wav
  "$DEST/bin/open_jtalk-aarch64" -x "$DEST/dic" -m "$DEST/voice/tohoku.htsvoice" -ow "$w" <<< "$1" >/dev/null 2>&1 \
    && aplay -q "$w" >/dev/null 2>&1; rm -f "$w"
}
die() { say "ERROR: $*"; say "Please send $LOG"; speak "インストール できませんでした"; exit 1; }

say "=== Pokemon Urusai installer for Knulli ($(date)) ==="
say "source: $SRC"
[ "$(id -u)" -eq 0 ] || die "run this as root (Knulli's Ports and SSH already are)"
[ -d /userdata/system ] || die "this doesn't look like Knulli (no /userdata/system)"
[ "$(uname -m)" = "aarch64" ] || die "this build is for aarch64 (got $(uname -m))"
command -v python3 >/dev/null || die "python3 not found"
for f in urusai/server.py bin/open_jtalk-aarch64 dic/sys.dic; do
  [ -e "$SRC/$f" ] || die "missing $f in $SRC (use the release zip, it includes the dictionary)"
done

# Stop an older copy first.
[ -x "$SERVICE" ] && "$SERVICE" stop >> "$LOG" 2>&1

say "Copying files to $DEST ..."
mkdir -p "$DEST" || die "can't create $DEST"
for d in urusai bin dic voice font; do
  rm -rf "${DEST:?}/$d"
  cp -r "$SRC/$d" "$DEST/" || die "copy of $d failed (SD card full?)"
done
cp "$SRC/install/knulli/uninstall.sh" "$DEST/" && chmod +x "$DEST/uninstall.sh"
chmod +x "$DEST/bin/"* 2>/dev/null
mkdir -p "$DEST/cache" "$CAPTURE_DIR"

# Does the voice program run from here? (FAT/exFAT cards can forbid running programs.)
if ! echo "テスト" | "$DEST/bin/open_jtalk-aarch64" -x "$DEST/dic" -m "$DEST/voice/tohoku.htsvoice" -ow /tmp/urusai_test.wav >> "$LOG" 2>&1; then
  say "  (the voice program can't run from the SD card: the service will run it from memory)"
fi
rm -f /tmp/urusai_test.wav
(cd "$DEST" && python3 -c "import urusai.server" >> "$LOG" 2>&1) || die "python3 is missing a module the reader needs (see $LOG)"

# Settings file: create it, or refresh its comments while keeping the values.
(cd "$DEST" && python3 -m urusai.settings "$SETTINGS") >> "$LOG" 2>&1 || say "  (couldn't write $SETTINGS)"

say "RetroArch settings (in $CONF) ..."
[ -f "$CONF" ] || die "no $CONF"
[ -f "$CONF.urusai-backup" ] || cp "$CONF" "$CONF.urusai-backup"
sed -i "/^$MARK/d; /^global\.retroarch\.ai_service_/d; /^global\.retroarch\.input_ai_service=/d" "$CONF"
cat >> "$CONF" <<EOF
$MARK: reads the screen aloud through RetroArch's AI Service. Remove with the uninstaller.
global.retroarch.ai_service_enable=true
global.retroarch.ai_service_mode=1
global.retroarch.ai_service_url=http://127.0.0.1:4404/
global.retroarch.ai_service_pause=false
global.retroarch.input_ai_service=f9
EOF
# (Knulli's hotkey-enable key is always Shift, so the reader presses Shift+F9.
#  By hand: Hotkey + R1 starts/stops it, Knulli's own AI Service hotkey.)

say "Start-up service ..."
mkdir -p "$(dirname "$SERVICE")"
cat > "$SERVICE" <<EOF
#!/bin/bash
# Pokemon Urusai screen reader (RetroArch AI Service on 127.0.0.1:4404). Made by its installer.
DEST=$DEST
PID=/var/run/urusai.pid
case "\$1" in
  start)
    [ -f "\$PID" ] && kill -0 "\$(cat "\$PID")" 2>/dev/null && exit 0
    modprobe uinput 2>/dev/null
    BIN="\$DEST/bin/open_jtalk-aarch64"
    "\$BIN" </dev/null >/dev/null 2>&1
    if [ \$? -ge 126 ]; then   # 126/127: the card won't let programs run, so run it from memory
      mkdir -p /tmp/urusai-bin && cp "\$BIN" /tmp/urusai-bin/ && chmod +x /tmp/urusai-bin/* && BIN=/tmp/urusai-bin/open_jtalk-aarch64
    fi
    cd "\$DEST" || exit 1
    URUSAI_OPEN_JTALK="\$BIN" nohup nice -n 5 python3 -m urusai.server --port 4404 --keys shift+f9 \\
      --capture $CAPTURE_DIR --settings $SETTINGS --cache "\$DEST/cache" >> /userdata/system/logs/urusai.log 2>&1 &
    echo \$! > "\$PID"
    ;;
  stop)
    [ -f "\$PID" ] && kill "\$(cat "\$PID")" 2>/dev/null
    pkill -f "urusai.server --port 4404" 2>/dev/null   # (a copy started some other way)
    for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -f "urusai.server --port 4404" >/dev/null || break; sleep 0.5; done
    rm -f "\$PID"
    ;;
  status)
    [ -f "\$PID" ] && kill -0 "\$(cat "\$PID")" 2>/dev/null && echo running || echo stopped
    ;;
esac
EOF
chmod +x "$SERVICE"
mkdir -p /userdata/system/logs
if command -v batocera-services >/dev/null; then
  batocera-services enable urusai >> "$LOG" 2>&1 || say "  (couldn't enable it: turn on 'urusai' in System settings → Services)"
else
  say "  (no batocera-services: turn on 'urusai' in System settings → Services)"
fi
"$SERVICE" start >> "$LOG" 2>&1

# An uninstaller in Ports, next to the installer.
cat > "$(dirname "$SRC")/Uninstall Pokemon Urusai.sh" <<EOF 2>/dev/null
#!/bin/bash
exec bash $DEST/uninstall.sh
EOF

sleep 4
if curl -s -m 3 http://127.0.0.1:4404/ >/dev/null 2>&1 || [ "$("$SERVICE" status)" = running ]; then
  say ""
  say "Done! Start a Game Boy or GBA game: the text is read automatically."
  say "L2 = say it again.  Select + L2 = reader off/on.  Hotkey + R1 = start/stop by hand."
  say "Settings: $SETTINGS   Status: $CAPTURE_DIR/STATUS.txt"
  speak "インストール できました。ゲームを はじめてね。"
else
  die "the reader didn't start (see /userdata/system/logs/urusai.log)"
fi
