# Finding out how this system is set up, instead of assuming. Sourced by install.sh.
#
# The installer first assumed Knulli's settings file is /userdata/system/batocera.conf
# and its service tool is batocera-services, as in Knulli's public source. On Henry's
# RG35XXSP neither existed, so RetroArch never got the reader's settings. So: ask the
# system's own game launcher which file it reads, look for the tools under both names,
# and write down what was found (urusai_system_report.txt) for when it still goes wrong.

# The settings file the game launcher (configgen) really reads.
find_conf() {
  local found
  found="$(python3 - <<'PY' 2>/dev/null
import importlib
hits = []
for mod in ("configgen.batoceraPaths", "configgen.batoceraFiles", "configgen.knulliPaths", "configgen.knulliFiles"):
    try:
        m = importlib.import_module(mod)
    except Exception:
        continue
    for name in dir(m):
        v = str(getattr(m, name))
        if name.upper().endswith("CONF") and v.startswith("/userdata/system/") and v.endswith(".conf") and v.count("/") == 3:
            hits.append(v)
main = [h for h in hits if h.rsplit("/", 1)[1] in ("knulli.conf", "batocera.conf", "system.conf")]
print((main or hits or [""])[0])
PY
)"
  if [ -n "$found" ]; then echo "$found"; return; fi
  for found in /userdata/system/knulli.conf /userdata/system/batocera.conf /userdata/system/system.conf; do
    [ -f "$found" ] && { echo "$found"; return; }
  done
  echo /userdata/system/batocera.conf
}

# The tool that switches start-up services on (empty if there is none).
find_services_tool() {
  local c
  for c in knulli-services batocera-services; do command -v "$c" >/dev/null 2>&1 && { echo "$c"; return; }; done
}

# Everything needed to see why RetroArch didn't get its settings, in one file.
system_report() {
  local out="$1" cg
  {
    echo "=== Pokemon Urusai system report ($(date)) ==="
    echo "--- system"; uname -a; python3 --version 2>&1
    cat /usr/share/batocera/batocera.version /usr/share/knulli/knulli.version 2>/dev/null
    head -4 /etc/os-release 2>/dev/null
    echo "--- settings file chosen: $CONF"
    echo "--- /userdata/system"; ls -la /userdata/system 2>&1
    echo "--- tools"; ls /usr/bin /usr/sbin 2>/dev/null | grep -iE "knulli|batocera" | tr '\n' ' '; echo
    echo "--- the reader's lines in each settings file"
    grep -HnE "Urusai|retroarch\.(ai_service|input_ai_service|audio_mute)|ai_service|^system\.services" /userdata/system/*.conf 2>&1 | head -40
    echo "--- services"; ls -la /userdata/system/services 2>&1; grep -n "urusai" /userdata/system/custom.sh 2>&1
    echo "--- game launcher (configgen)"
    cg="$(python3 -c 'import configgen, os; print(os.path.dirname(configgen.__file__))' 2>&1)"; echo "$cg"
    ls "$cg" 2>&1 | tr '\n' ' '; echo
    grep -nE "\.conf['\"]" "$cg"/batoceraPaths.py "$cg"/batoceraFiles.py "$cg"/*Paths.py 2>/dev/null | head -12
    find "$cg" -name "libretroConfig.py*" 2>/dev/null | head -3
    grep -nE "ai_service|retroarch\.\"|\"retroarch\.|'retroarch\.|\[:10\]" "$cg"/generators/libretro/libretroConfig.py 2>&1 | head -24
    echo "--- what RetroArch last ran with"
    grep -HnE "^(ai_service|input_ai_service|input_enable_hotkey |input_enable_hotkey=|audio_mute_enable)" \
      /userdata/system/configs/retroarch/retroarchcustom.cfg /userdata/system/configs/retroarch/retroarch.cfg 2>&1 | head -24
    echo "--- reader"; "$SERVICE" status 2>&1; tail -15 /userdata/system/logs/urusai.log 2>&1
  } > "$out" 2>&1
}
