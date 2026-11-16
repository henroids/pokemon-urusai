# The natural voice (piper-plus + つくよみちゃん), shared by the dArkOS and Knulli installers.
# Sourced, not run. Needs: SRC, DEST, LOG, say(), and MODEL_SEARCH (folders that may hold a
# copied model). The program comes with this package; the voice itself (about 40 MB) is
# copied from the SD card if it's there, else downloaded once (needs Wi-Fi).

NEURAL="$DEST/neural"; MODEL_DIR="$NEURAL/model"
if [ -d "$SRC/neural/aarch64" ]; then
  mkdir -p "$MODEL_DIR"
  rm -rf "$NEURAL/aarch64"; cp -r "$SRC/neural/aarch64" "$NEURAL/" || say "  (copy of the natural voice program failed)"
  chmod +x "$NEURAL/aarch64/bin/piper-plus" 2>/dev/null
  # Some SD cards (FAT/exFAT) won't run programs: then it runs from memory (/tmp), as the reader does.
  RUN="$NEURAL/aarch64"
  "$RUN/bin/piper-plus" --help >/dev/null 2>&1
  if [ $? -ge 126 ]; then
    rm -rf /tmp/urusai-neural; cp -r "$RUN" /tmp/urusai-neural && chmod +x /tmp/urusai-neural/bin/piper-plus && RUN=/tmp/urusai-neural
  fi
  pp() { LD_LIBRARY_PATH="$RUN/lib" OPENJTALK_DICTIONARY_PATH="$DEST/dic" PIPER_PLUS_AUTO_DOWNLOAD_DICT=0 \
         PIPER_PLUS_DISABLE_MODEL_NOTICE=1 "$RUN/bin/piper-plus" "$@"; }
  have_model() { find "$MODEL_DIR" -name '*tsukuyomi*.onnx' -size +1M 2>/dev/null | grep -q .; }
  if ! have_model; then
    for d in "$SRC/neural/model" "$SRC/../tsukuyomi" $MODEL_SEARCH; do
      ls "$d"/*tsukuyomi*.onnx >/dev/null 2>&1 || continue
      say "Natural voice: copying it from $d ..."
      cp "$d"/*.onnx "$d"/*.json "$MODEL_DIR/" 2>/dev/null
      break
    done
  fi
  if ! have_model; then
    say "Natural voice: downloading it (needs Wi-Fi, about 40 MB, a few minutes) ..."
    timeout 900 env LD_LIBRARY_PATH="$RUN/lib" "$RUN/bin/piper-plus" --download-model tsukuyomi --model-dir "$MODEL_DIR" >> "$LOG" 2>&1
  fi
  if have_model; then
    M="$(find "$MODEL_DIR" -name '*tsukuyomi*.onnx' | head -1)"
    t0=$(date +%s.%N)
    if pp -q -m "$M" -l ja -t "ポケモンの せかいへ ようこそ" -f /tmp/urusai_neural.wav >> "$LOG" 2>&1 && [ -s /tmp/urusai_neural.wav ]; then
      NATURAL_VOICE=ready
      say "Natural voice: ready ($(echo "$(date +%s.%N) $t0" | awk '{printf "%.1f", $1-$2}') s to start and say a test line)"
    else
      NATURAL_VOICE=broken
      say "Natural voice: did not run on this system; the standard voice is used. (details in $LOG)"
    fi
    rm -f /tmp/urusai_neural.wav
  else
    NATURAL_VOICE=missing
    say "Natural voice: not installed (no Wi-Fi?). The standard voice is used until it is."
    say "  Either connect Wi-Fi and run this installer again, or see INSTALL.md, 'Natural voice'."
  fi
fi
