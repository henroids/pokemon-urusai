# Pokémon Urusai

An offline Japanese screen reader for **Gen 1 Pokémon (赤・緑・青・ピカチュウ)**. Text is read aloud as it appears: dialogue, and menu choices as the cursor moves, with a chime marking the selected one. **Tap L2** to hear it again, **double-tap** to switch automatic reading off/on. The game keeps running while it talks.

Everything runs on the handheld, with no internet and no PC:

- RetroArch's **AI Service** runs in its *auto* mode: it keeps sending frames to a tiny local server (`127.0.0.1:4404`), and plays any speech we send back.
- The server reads the kana by matching the game's 8×8 font tiles. It decides what's new: a scrolled line, a menu that opened, a cursor that moved.
- It speaks with **Open JTalk** and prepares the speech in the background, so it plays almost at once.
- A virtual keyboard presses RetroArch's AI Service hotkey to start the stream when a game launches (or when L2 is pressed).

**→ To install it, see [INSTALL.md](INSTALL.md).**

## Status

| Part | State |
|---|---|
| RetroArch AI Service (Speech mode, no pause) | works on the RGB20 Pro (dArkOS) |
| Auto reading via RetroArch auto mode, L2 = say again, autostart via uinput | new in 0.4.0, needs hardware testing |
| Gen 1 font (`font/gen1_jp.json`, 129 tiles) | all kana, marks, menus; some digits and symbols still missing |
| Offline voices: tohoku (dialogue), nitech (menus), mei | static aarch64 `open_jtalk`, no apt needed |
| Settings file on the SD card | auto read, autostart, button, voices, volume, speed, captures |
| Knulli (RG35XXSP) | todo |

## What it reads

- **Dialogue** (the box at the bottom): read once it has finished printing. When the box scrolls one line, **only the new line** is read.
- **Menus and questions**: the question, an "open" sound, then every option in the menu voice, with a sound after the selected one: **はい "biiing–booong"**, **いいえ a buzzer "eerrrr"**, other options a short "pip". Moving the cursor reads **just the new option**, with a low "tok" at the first/last one. A "close" sound when the menu goes away. Big grids (name entry) read only the selected letter.
- **Tap L2**, any time: the whole screen again, once, including screens that aren't read automatically (e.g. the Pokédex). **Double-tap**: 「よみあげ オフ/オン」.
- Text is read in one flow (no pauses at the game's word spaces). The spaces are still used to check particles: a は/へ ending a phrase must sound "wa"/"e", and if Open JTalk misreads one (e.g. かれは as 枯れ葉 "kareha") it's corrected and re-spoken.
- All voices are levelled to the same loudness; `menu_position = on` adds 「2ばんめ」 after the selection.

Missing symbols (some digits, ♂/♀, ×) are simply skipped until they're added.

## Layout

| Path | What |
|---|---|
| `urusai/server.py` | AI Service endpoint: the frame stream, when to speak, autostart, captures |
| `urusai/speech.py` | what to say (new lines only, menus with selection sounds) + background speech cache |
| `urusai/vkbd.py` | virtual keyboard (uinput) that presses the AI Service hotkey |
| `urusai/reader.py` | tiles → `Reading` (dialogue lines, menu options + selection, other text) |
| `urusai/screen.py`, `pngdec.py` | frame → 20×18 one-bit tiles (stdlib-only PNG) |
| `urusai/font.py` | tile → label table |
| `urusai/tts.py`, `audio.py`, `normalize.py` | Open JTalk, loudness, text clean-up for speech |
| `urusai/button.py` | gamepad watcher + single/double tap detection |
| `urusai/settings.py` | `urusai_settings.txt` |
| `font/gen1_jp.json` | the font, built by `tools/build_font.py` from `tests/frames/` |
| `tests/frames/` | 36 reference frames (160×144) from 青, with expected readings |
| `install/darkos/` | installer, systemd unit, uninstaller |

## Adding missing symbols

Everything read aloud also saves the frame and the text to `urusai_captures/` on the SD card (the newest 50 are kept). To teach new tiles:

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
