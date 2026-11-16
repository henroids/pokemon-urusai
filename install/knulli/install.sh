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
# Knulli runs Ports with the screen blank, so the installer talks instead, and leaves a
# message box in the menu (EmulationStation's own API) that shows once you're back there.
speak() {
  wait   # (let the "starting" message finish first)
  local w=/tmp/urusai_say.wav bin="$SRC/bin/open_jtalk-aarch64"
  [ -x "$bin" ] || { cp "$bin" /tmp/urusai_oj 2>/dev/null && chmod +x /tmp/urusai_oj && bin=/tmp/urusai_oj; }
  "$bin" -x "$SRC/dic" -m "$SRC/voice/tohoku.htsvoice" -ow "$w" <<< "$1" >/dev/null 2>&1 \
    && aplay -q "$w" >/dev/null 2>&1; rm -f "$w"
}
popup() { curl -s -m 3 -X POST http://127.0.0.1:1234/messagebox -d "$1" >/dev/null 2>&1; }
# die "what went wrong" "the same, short, to say out loud"
die() {
  say "ERROR: $1"; say "Please send $LOG"
  popup "$(printf 'Pokemon Urusai: install FAILED\n\n%s\n\nDetails: roms/urusai_install.log' "$1")"
  speak "インストール できませんでした。${2:-}"; exit 1
}

say "=== Pokemon Urusai installer for Knulli ($(date)) ==="
speak "インストール しています。すこし まってね。" &
say "source: $SRC"
[ "$(id -u)" -eq 0 ] || die "run this as root (Knulli's Ports and SSH already are)" "かんりしゃ では ありません"
[ -d /userdata/system ] || die "this doesn't look like Knulli (no /userdata/system)" "ニュリ では ありません"
[ "$(uname -m)" = "aarch64" ] || die "this build is for aarch64 (got $(uname -m))" "この きかいには あいません"
command -v python3 >/dev/null || die "python3 not found" "パイソンが ありません"
for f in urusai/server.py bin/open_jtalk-aarch64 dic/sys.dic; do
  [ -e "$SRC/$f" ] || die "missing $f in $SRC (use the release zip, it includes the dictionary)" "ファイルが たりません"
done

# Stop an older copy first.
[ -x "$SERVICE" ] && "$SERVICE" stop >> "$LOG" 2>&1

say "Copying files to $DEST ..."
mkdir -p "$DEST" || die "can't create $DEST" "フォルダが つくれません"
for d in urusai bin dic voice font; do   # (neural/: below, it keeps the downloaded voice)
  rm -rf "${DEST:?}/$d"
  cp -r "$SRC/$d" "$DEST/" || die "copy of $d failed (SD card full?)" "コピー できません。カードが いっぱい かも"
done
cp "$SRC/install/knulli/uninstall.sh" "$DEST/" && chmod +x "$DEST/uninstall.sh"
chmod +x "$DEST/bin/"* 2>/dev/null
mkdir -p "$DEST/cache" "$CAPTURE_DIR"

# Does the voice program run from here? (FAT/exFAT cards can forbid running programs.)
if ! echo "テスト" | "$DEST/bin/open_jtalk-aarch64" -x "$DEST/dic" -m "$DEST/voice/tohoku.htsvoice" -ow /tmp/urusai_test.wav >> "$LOG" 2>&1; then
  say "  (the voice program can't run from the SD card: the service will run it from memory)"
fi
rm -f /tmp/urusai_test.wav
(cd "$DEST" && python3 -c "import urusai.server" >> "$LOG" 2>&1) || die "python3 is missing a module the reader needs (see $LOG)" "パイソンの ぶひんが たりません"

NATURAL_VOICE=none
MODEL_SEARCH="/userdata/roms/tsukuyomi /userdata/roms/ports/tsukuyomi /userdata/tsukuyomi"
. "$SRC/install/common/natural_voice.sh"

# Settings file: create it, or refresh its comments while keeping the values.
(cd "$DEST" && python3 -m urusai.settings "$SETTINGS") >> "$LOG" 2>&1 || say "  (couldn't write $SETTINGS)"

say "RetroArch settings (in $CONF) ..."
if [ ! -f "$CONF" ]; then
  # Knulli makes batocera.conf on first boot, or when a setting is first saved; it
  # can be missing. Start it from Knulli's own default, as that first boot would.
  say "  ($CONF didn't exist yet: creating it from Knulli's default)"
  cp /usr/share/batocera/datainit/system/batocera.conf "$CONF" 2>/dev/null || : > "$CONF" \
    || die "can't create $CONF" "せっていファイルが つくれません"
fi
[ -f "$CONF.urusai-backup" ] || cp "$CONF" "$CONF.urusai-backup"
sed -i "/^$MARK/d; /^global\.retroarch\.ai_service_/d; /^global\.retroarch\.input_ai_service=/d; /^global\.retroarch\.audio_mute_enable=/d" "$CONF"
cat >> "$CONF" <<EOF
$MARK: reads the screen aloud through RetroArch's AI Service. Remove with the uninstaller.
global.retroarch.ai_service_enable=true
global.retroarch.ai_service_mode=1
global.retroarch.ai_service_url=http://127.0.0.1:4404/
global.retroarch.ai_service_pause=false
global.retroarch.input_ai_service=f10
global.retroarch.audio_mute_enable=false
EOF
# (Knulli's hotkey-enable key is always Shift, so the reader presses Shift+F10. Not F9:
#  that's RetroArch's mute key, which 0.10.0 used. audio_mute_enable undoes a stuck mute.
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
    PP="\$DEST/neural/aarch64/bin/piper-plus"   # the natural voice, same check
    if [ -f "\$PP" ]; then
      "\$PP" --help >/dev/null 2>&1
      if [ \$? -ge 126 ]; then
        rm -rf /tmp/urusai-neural; cp -r "\$DEST/neural/aarch64" /tmp/urusai-neural && chmod +x /tmp/urusai-neural/bin/piper-plus
        export URUSAI_PIPER=/tmp/urusai-neural/bin/piper-plus
      fi
    fi
    cd "\$DEST" || exit 1
    URUSAI_OPEN_JTALK="\$BIN" nohup nice -n 5 python3 -m urusai.server --port 4404 --keys shift+f10 \\
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
  case "$NATURAL_VOICE" in
    ready) VOICE_LINE="Natural voice: ready" ;;
    none)  VOICE_LINE="" ;;
    *)     VOICE_LINE="Natural voice: not installed (needs Wi-Fi during install); the standard voice is used" ;;
  esac
  popup "$(printf 'Pokemon Urusai: installed\n\nStart a Game Boy or GBA game: the text is read aloud.\nL2 = say it again\nSelect + L2 = reader off/on\n%s' "$VOICE_LINE")"
  case "$NATURAL_VOICE" in
    ready) speak "インストール できました。ゲームを はじめてね。" ;;
    *)     speak "インストール できました。でも、しぜんな こえは まだ ありません。" ;;
  esac
else
  die "the reader didn't start (see /userdata/system/logs/urusai.log)" "よみあげが はじまりません"
fi
