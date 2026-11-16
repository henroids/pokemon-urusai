#!/bin/bash
# Remove Pokémon Urusai from Knulli and take its lines out of batocera.conf.
CONF=/userdata/system/batocera.conf
SERVICE=/userdata/system/services/urusai
[ -x "$SERVICE" ] && "$SERVICE" stop
command -v batocera-services >/dev/null && batocera-services disable urusai 2>/dev/null
rm -f "$SERVICE"
[ -f "$CONF" ] && sed -i "/^# Pokemon Urusai (screen reader)/d; /^global\.retroarch\.ai_service_/d; /^global\.retroarch\.input_ai_service=/d; /^global\.retroarch\.audio_mute_enable=/d" "$CONF"
rm -f "/userdata/roms/ports/Uninstall Pokemon Urusai.sh"
rm -rf /userdata/system/urusai
echo "Pokemon Urusai removed (/userdata/roms/urusai_captures and urusai_settings.txt were kept)."
