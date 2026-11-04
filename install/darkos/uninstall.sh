#!/bin/bash
# Remove Pokémon Urusai and restore RetroArch's AI Service settings from the backup.
[ "$(id -u)" -eq 0 ] || exec sudo bash "$0" "$@"
systemctl disable --now urusai.service 2>/dev/null
rm -f /etc/systemd/system/urusai.service
systemctl daemon-reload
HOME_DIR="$(getent passwd "${URUSAI_USER:-ark}" | cut -d: -f6)"
for cfg in "$HOME_DIR/.config/retroarch/retroarch.cfg" "$HOME_DIR/.config/retroarch32/retroarch.cfg"; do
  [ -f "$cfg" ] && for k in ai_service_enable ai_service_mode ai_service_url ai_service_pause network_cmd_enable input_ai_service_btn input_enable_hotkey input_ai_service; do
    old="$(grep "^$k *=" "$cfg.urusai-backup" 2>/dev/null)"
    if [ -n "$old" ]; then sed -i "s#^$k *=.*#$old#" "$cfg"; else sed -i "/^$k *=/d" "$cfg"; fi
  done
done
# Put back RetroArch hotkeys that were moved off L2 for the reader's Select + L2.
(cd /opt/urusai 2>/dev/null && python3 -m urusai.racfg restore \
  "$HOME_DIR/.config/retroarch/retroarch.cfg" "$HOME_DIR/.config/retroarch32/retroarch.cfg")
rm -rf /opt/urusai
echo "Pokemon Urusai removed (/roms/urusai_captures and /roms/urusai_settings.txt were kept)."
