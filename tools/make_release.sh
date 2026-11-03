#!/bin/bash
# Build dist/PokemonUrusai-<version>.zip (includes the 103 MB dictionary, which isn't in git).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(python3 -c "import sys; sys.path.insert(0,'$ROOT'); import urusai; print(urusai.__version__)")"
DIC="${URUSAI_DICT_SRC:-$ROOT/dic}"
[ -f "$DIC/sys.dic" ] || DIC=/var/lib/mecab/dic/open-jtalk/naist-jdic
[ -f "$DIC/sys.dic" ] || { echo "need naist-jdic (apt install open-jtalk-mecab-naist-jdic)"; exit 1; }
OUT="$ROOT/dist"; STAGE="$OUT/stage"; PKG="$STAGE/PokemonUrusai"
rm -rf "$STAGE"; mkdir -p "$PKG/dic"
cp -r "$ROOT"/{urusai,tools,bin,voice,install,README.md,INSTALL.md,LICENSES.md} "$PKG/"
mkdir -p "$PKG/font"; cp "$ROOT"/font/*.json "$PKG/font/" 2>/dev/null || true
cp "$DIC"/* "$PKG/dic/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +
cp "$ROOT/install/darkos/Install Pokemon Urusai.sh" "$STAGE/"
(cd "$STAGE" && rm -f "$OUT/PokemonUrusai-$VER.zip" && zip -qr9 "$OUT/PokemonUrusai-$VER.zip" .)
rm -rf "$STAGE"
ls -lh "$OUT/PokemonUrusai-$VER.zip"
