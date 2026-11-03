# Pokémon Urusai

An offline Japanese screen reader for **Gen 1 Pokémon (赤・緑・青・ピカチュウ)**. When you press one button, it reads the current text box, menu choice or battle message aloud in Japanese.

It runs entirely on the handheld. RetroArch's **AI Service** sends the frame to a tiny local server (`127.0.0.1:4404`). The server reads the kana by matching the game's 8×8 font tiles, speaks the result with **Open JTalk**, and sends back a WAV, which RetroArch plays.

## Status

| Part | State |
|---|---|
| RetroArch AI Service protocol (Speech mode) | done, checked against RetroArch source |
| Tile reader (゛/゜ above the line, boxes, ▶ cursor) | done, tested on synthetic screens |
| **Gen 1 font table** (`font/gen1_jp.json`) | **needs real frames from the game** |
| Offline TTS: static aarch64 `open_jtalk` + dictionary + voice | done (works on dArkOS and Knulli, no apt) |
| dArkOS installer + systemd service | written, not yet run on hardware |
| Knulli (RG35XXSP) | todo |

## What it reads

- **Dialogue box** (bottom of the screen): the whole box, for example 「やせいの ピカチュウが とびだしてきた！」.
- **Menus with a ▶ cursor**: any dialogue above the menu, then the **selected item** (for example 「どうぐ」). Your son can move the cursor and press the button to hear what he's on.
- **Anything else**: all the text on the screen, top to bottom.

## Install on dArkOS (RGB20 Pro)

See **[INSTALL.md](INSTALL.md)** for step-by-step instructions. In short: copy the release zip's contents to `ports`, run **Install Pokemon Urusai** from Ports, then press **Select + Y** in the game.

## Building the font (once)

Every button press saves the native 160×144 frame and what was read into **`/roms/urusai_captures/`**. That includes presses before the font exists. Play a little, press the button on the screens below, then copy that folder off the SD card:

1. Name entry: the ひらがな page and the カタカナ page
2. A few dialogue boxes with が / ぱ / ポケモン
3. The start menu (ずかん, ポケモン, どうぐ…)
4. A battle message and the battle menu

Then label the tiles:

```sh
tools/learn.py grid  captures/X.png                  # shows the tile grid; ?N = unknown tile
tools/learn.py label captures/X.png 14:1 "やせいの ピカチュウが" 16:1 "とびだしてきた！"
tools/learn.py tile  captures/X.png 12:0 "<box>"     # borders, "<cursor>", "<more>"
tools/learn.py read  captures/X.png --wav test.wav   # check it
```

The server reloads `font/gen1_jp.json` automatically when it changes.

AYN Thor screenshots also work (shaders off, Integer Scale on, Bilinear off). They are downscaled automatically.

## Options

- `--speed 0.95`: speaking speed.
- **Voice**: drop any `.htsvoice` file into `voice/`. A file named `mei*.htsvoice` (MMDAgent's Mei, a female voice) is preferred automatically.
- `URUSAI_VERBOSE=1`: log every request.

## Develop

```sh
python3 tests/test_pipeline.py      # needs open_jtalk + naist-jdic + a voice on the PC (apt install open-jtalk ...)
tools/make_release.sh               # builds dist/PokemonUrusai-<ver>.zip with the dictionary
```

`bin/open_jtalk-aarch64` is a static build of Open JTalk 1.11 with HTS Engine 1.10 (`--host=aarch64-linux-gnu LDFLAGS=-static`).

The dictionary (`dic/`, 103 MB) is not in git, because it is over GitHub's 100 MB per-file limit. The release zip includes it.
