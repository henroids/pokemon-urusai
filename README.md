# Pokémon Urusai

An offline Japanese screen reader for **Gen 1 Pokémon (赤・緑・青・ピカチュウ)**. Press **L2** and the current text box, menu choice or battle message is read aloud in Japanese. The game keeps running while it talks.

Everything runs on the handheld, with no internet and no PC:

1. A small watcher sees the button press.
2. It asks RetroArch to send the current frame to a tiny local server (`127.0.0.1:4404`) through RetroArch's **AI Service**.
3. The server reads the kana by matching the game's 8×8 font tiles and speaks the result with **Open JTalk**.
4. RetroArch plays the returned WAV over the game.

**→ To install it, see [INSTALL.md](INSTALL.md).**

## Status

| Part | State |
|---|---|
| RetroArch AI Service (Speech mode, no pause) | works on the RGB20 Pro (dArkOS) |
| Single-button trigger (L2) via RetroArch network command | new in 0.3.0 |
| Gen 1 font (`font/gen1_jp.json`, 129 tiles) | all kana, marks, menus; some digits and symbols still missing |
| Offline voices: tohoku (default), mei, nitech | static aarch64 `open_jtalk`, no apt needed |
| Settings file on the SD card | volume, voice, speed, button, captures |
| Knulli (RG35XXSP) | todo |

## What it reads

- **Dialogue box** (bottom of the screen): the whole box, for example 「やせいの ピカチュウが とびだしてきた！」.
- **Menus with a ▶ cursor**: any message, then the **selected option** (for example 「たたかう」). Move the cursor, press L2, and hear what it's on.
- **Anything else** (e.g. the Pokédex): all the text on screen, top to bottom.

Missing symbols (some digits, ♂/♀, ×) are simply skipped until they're added.

## Layout

| Path | What |
|---|---|
| `urusai/server.py` | AI Service endpoint, settings, captures |
| `urusai/reader.py` | tiles → text (゛/゜ above the line, boxes, ▶ cursor, shared へ/ヘ tiles) |
| `urusai/screen.py`, `pngdec.py` | frame → 20×18 one-bit tiles (stdlib-only PNG) |
| `urusai/font.py` | tile → label table |
| `urusai/tts.py`, `audio.py`, `normalize.py` | Open JTalk, loudness, text clean-up for speech |
| `urusai/button.py` | gamepad watcher → RetroArch `AI_SERVICE` command |
| `urusai/settings.py` | `urusai_settings.txt` |
| `font/gen1_jp.json` | the font, built by `tools/build_font.py` from `tests/frames/` |
| `tests/frames/` | 36 reference frames (160×144) from 青, with expected readings |
| `install/darkos/` | installer, systemd unit, uninstaller |

## Adding missing symbols

Every button press saves the frame and what was read to `urusai_captures/` on the SD card (the newest 50 are kept). To teach new tiles:

```sh
tools/learn.py unknown captures/                    # unknown tiles next to text, with examples
tools/learn.py grid    captures/X.png               # the tile grid; ?N = unknown tile
tools/learn.py read    captures/X.png --wav t.wav   # what it would say
```

For a permanent fix:

1. Copy the frame into `tests/frames/`.
2. Add its text to `TEXT` / `TILES` (and its reading to `EXPECT`) in `tools/build_font.py`.
3. Run `tools/build_font.py`. It rebuilds the font and checks every reference frame.

## Develop

```sh
python3 -m unittest discover -s tests   # needs open_jtalk + naist-jdic on the PC (apt install open-jtalk open-jtalk-mecab-naist-jdic)
tools/build_font.py                      # rebuild font/gen1_jp.json and check all 36 frames
tools/make_release.sh                    # dist/PokemonUrusai-<ver>.zip, including the dictionary
```

`bin/open_jtalk-aarch64` is a static build of Open JTalk 1.11 with HTS Engine 1.10 (`--host=aarch64-linux-gnu LDFLAGS=-static`).

The dictionary (`dic/`, 103 MB) is not in git, because it is over GitHub's 100 MB per-file limit. The release zip includes it.
