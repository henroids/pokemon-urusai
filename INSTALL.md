# Installing Pokémon Urusai on the RGB20 Pro (dArkOS)

**The text is read aloud automatically** as it appears: dialogue, and menu choices as the cursor moves. **Tap L2** to hear it again; **double-tap L2** to switch automatic reading off or on. The game keeps running while it talks.

The install takes about 10 minutes, once. After that, the reader starts by itself every time the handheld boots. It needs no Wi-Fi and no PC.

## What you need

- The release zip, e.g. `PokemonUrusai-0.5.0.zip`. The zip on the GitHub page isn't enough, because it doesn't include the 103 MB dictionary.
- The RGB20 Pro's games SD card and a card reader. Or use any other way you normally copy ROMs over.
- Your Pokémon game (Game Boy) running in **RetroArch**. On dArkOS, Game Boy games use RetroArch by default, so your `gb` folder is fine.

## 1. Copy the files to the SD card

1. Unzip the release on your PC. You get two things:
   - a folder called `PokemonUrusai`
   - a file called `Install Pokemon Urusai.sh`
2. Put the games SD card in your PC and open the `ports` folder on it. It's the same place as your `gb` folder, usually shown as **EASYROMS**.
3. Copy **both** into `ports`. Replace the old ones if you're updating, and don't put the `.sh` file inside the folder.
4. Eject the card safely and put it back in the handheld.

## 2. Run the installer

**Run it while no game is open.** RetroArch reads its settings when a game starts.

1. Turn on the RGB20 Pro.
2. In EmulationStation, open **Ports**. If you don't see the new entry, go to *Start → Game Settings → Update Gamelists* (or restart).
3. Start **Install Pokemon Urusai**. A text screen shows the progress for about a minute and ends with **Done!**. It then returns to the menu by itself.

The installer does the following:

- copies everything to `/opt/urusai`
- starts the reader in the background, now and at every boot
- sets up RetroArch:
  - AI Service on, in Speech mode, at `http://127.0.0.1:4404/`
  - **no pause**, so the game keeps going while it talks
  - keyboard hotkeys F8 + F6 for the AI Service, which the reader presses on a virtual keyboard so nobody has to hold Select
- creates or refreshes `urusai_settings.txt` on the games SD card (see below). Your values are kept.
- backs up your RetroArch settings first (`retroarch.cfg.urusai-backup`)
- writes `urusai_install.log` to the games SD card

## 3. Try it

1. Start Pokémon and wait about 10 seconds. The reader switches itself on.
2. Talk to someone. The text is read as soon as the box has finished printing.

| On screen | What you hear |
|---|---|
| A new text box | the box; after it scrolls, **only the new line** |
| A menu or question opens | a rising "pop" sound, the question (if not read yet), then every option in the **menu voice**, with a **"biiing–booong" right after the selected one** |
| The cursor moves | just the newly selected option (a low "tok" on the first or last one) |
| The menu closes | a falling "pop" sound |
| A big grid (name entry) | just the selected letter |
| **Tap L2** | the whole screen again, once (e.g. the Pokédex page or a full menu) |
| **Double-tap L2** | 「よみあげ オフ」 / 「よみあげ オン」: automatic reading off/on. Tapping still works while it's off. |

If nothing is read after starting a game, press **L2** once (or **Select + Y**). **Select + Y** also switches the reader off and on.

## 4. Settings (volume, voice, button)

Open `urusai_settings.txt` on the games SD card with any text editor. Changes apply on the next button press, with no restart needed.

| Setting | Default | What it does |
|---|---|---|
| `auto_read` | `on` | Read new text and menu choices automatically. `off` = only when you press the button. |
| `autostart` | `on` | Switch the reader on by itself when a game starts |
| `button` | `L2` | Tap = say it again, double tap = reading off/on: `L1 R1 L2 R2 L3 R3 SELECT START`, or `off` |
| `sound_cues` | `on` | Sounds when a menu opens or closes and at the first/last option (the selection chime is always on) |
| `menu_position` | `off` | Say the position after the selected option, e.g. 「2ばんめ」 |
| `voice` | `tohoku` | Dialogue voice: `tohoku`, `tohoku_happy`, `mei`, `mei_happy` (female) or `nitech` (male) |
| `menu_voice` | `nitech` | Voice for menu options |
| `volume` | `200` | Voice volume in %. `100` is natural; higher is louder over the music. All voices are levelled to the same loudness, and it's limited so it never crackles. |
| `speed` | `0.95` | `1.0` is normal; `0.85` is slower |
| `captures_keep` | `50` | How many recently read screens to keep in `urusai_captures` (each is about 2 KB). `0` saves none. |

**About captures:** each time something is read, the screen and the text are saved. Only the newest `captures_keep` are kept and older ones are deleted automatically, so the folder can't fill up: 50 captures is about 100 KB. They're only useful for fixing misreads. Set it to `0` if you don't need them.

If the voice is still hard to hear, you can also lower the game's own volume. Open the RetroArch menu (**Select + X**), go to *Settings → Audio → Volume*, then *Main Menu → Configuration File → Save Current Configuration*.

## If it doesn't talk

Put the games SD card in your PC and check these files:

| File | What it tells us |
|---|---|
| `urusai_install.log` | Whether the installer finished. It should end with **Done!**; an **ERROR** line says what went wrong. |
| `urusai_captures/STATUS.txt` | Whether the reader is running, whether it found the L2 button (`button: watching L2 …`) and whether it can switch itself on (`starter: …`). |
| `urusai_captures/*.png` + `.txt` | One pair per thing read: the screen and the text. |

- **No `STATUS.txt`:** the reader isn't running. Send `urusai_install.log`.
- **Nothing is read, but Select + Y starts it:** the virtual keyboard didn't work. Send `STATUS.txt`; the `starter:` line says why. Until it's fixed, press Select + Y once per game; after that L2 and auto-reading work.
- **Select + Y doesn't start it either, and no `.png` appears:** in the RetroArch menu, check *Settings → AI Service*:
  - AI Service is **ON**
  - Output is **Speech Mode**
  - Pause is **OFF**
  - the URL is `http://127.0.0.1:4404/`
- **It reads the wrong thing, or a word is skipped:** send the `.png` and `.txt` files.

## Updating

Copy the new `PokemonUrusai` folder and `.sh` over the old ones in `ports`, then run **Install Pokemon Urusai** again. Your `urusai_settings.txt` is kept.

## Uninstalling

Over SSH, run `sudo /opt/urusai/install/darkos/uninstall.sh`. It removes the reader and puts your RetroArch settings back. `urusai_captures` and `urusai_settings.txt` are kept.
