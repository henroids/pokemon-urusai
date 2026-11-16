#!/bin/bash
# Remove Pokémon Urusai from Knulli and take its lines out of the system's settings files.
SERVICE=/userdata/system/services/urusai
[ -x "$SERVICE" ] && "$SERVICE" stop
for tool in knulli-services batocera-services; do
  command -v "$tool" >/dev/null 2>&1 && "$tool" disable urusai 2>/dev/null
done
rm -f "$SERVICE"
[ -f /userdata/system/custom.sh ] && sed -i "/services\/urusai/d" /userdata/system/custom.sh
for f in /userdata/system/*.conf; do
  [ -f "$f" ] && sed -i "/^# Pokemon Urusai (screen reader)/d; /^global\.retroarch\.ai_service_/d; /^global\.retroarch\.input_ai_service=/d; /^global\.retroarch\.audio_mute_enable=/d" "$f"
done
rm -f "/userdata/roms/ports/Uninstall Pokemon Urusai.sh"
rm -rf /userdata/system/urusai
echo "Pokemon Urusai removed (/userdata/roms/urusai_captures and urusai_settings.txt were kept)."
