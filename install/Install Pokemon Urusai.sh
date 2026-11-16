#!/bin/bash
# Put this file and the PokemonUrusai folder in the ports folder (dArkOS: /roms/ports,
# Knulli: /userdata/roms/ports), then run it from Ports. It picks the right installer.
HERE="$(dirname "$0")/PokemonUrusai/install"
if [ -d /userdata/system ]; then
  exec bash "$HERE/knulli/install.sh"
else
  exec bash "$HERE/darkos/install.sh"
fi
