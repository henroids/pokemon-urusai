# Installing Pokémon Urusai on the RGB20 Pro (dArkOS)

**Press L2 in the game to hear the text.** The game keeps running while it talks.

The install takes about 10 minutes, once. After that, the reader starts by itself every time the handheld boots. It needs no Wi-Fi and no PC.

## What you need

- The release zip, e.g. `PokemonUrusai-0.3.0.zip`. The zip on the GitHub page isn't enough, because it doesn't include the 103 MB dictionary.
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
  - network commands on, which is how the L2 button asks RetroArch to read the screen
- creates `urusai_settings.txt` on the games SD card (see below). An existing one is kept as it is.
- backs up your RetroArch settings first (`retroarch.cfg.urusai-backup`)
- writes `urusai_install.log` to the games SD card

## 3. Try it

1. Start Pokémon and go to any text box, for example talking to someone.
2. Press **L2**. The text is read aloud in Japanese.

What it reads:

| On screen | It says |
|---|---|
| A text box at the bottom | the whole text box |
| A menu with ▶ (battle, items, Pokémon) | any message, then the option the ▶ points at |
| Anything else (e.g. the Pokédex) | all the text on screen |

**Backup button:** **Select + Y** also works. It's RetroArch's own hotkey; on dArkOS, every hotkey needs Select held.

## 4. Settings (volume, voice, button)

Open `urusai_settings.txt` on the games SD card with any text editor. Changes apply on the next button press, with no restart needed.

| Setting | Default | What it does |
|---|---|---|
| `button` | `L2` | Which button reads the screen: `L1 R1 L2 R2 L3 R3 SELECT START`, or `off` |
| `voice` | `tohoku` | `tohoku`, `tohoku_happy`, `mei`, `mei_happy` (female) or `nitech` (male) |
| `volume` | `200` | Voice volume in %. `100` is natural; higher is louder over the music. It's limited, so it never crackles. |
| `speed` | `0.95` | `1.0` is normal; `0.85` is slower |
| `captures_keep` | `50` | How many recent screenshots to keep in `urusai_captures` (each is about 2 KB). `0` saves none. |

**About captures:** each button press saves the screen and what was read. Only the newest `captures_keep` are kept and older ones are deleted automatically, so the folder can't fill up: 50 captures is about 100 KB. They're only useful for fixing misreads. Set it to `0` if you don't need them.

If the voice is still hard to hear, you can also lower the game's own volume. Open the RetroArch menu (**Select + X**), go to *Settings → Audio → Volume*, then *Main Menu → Configuration File → Save Current Configuration*.

## If it doesn't talk

Put the games SD card in your PC and check these files:

| File | What it tells us |
|---|---|
| `urusai_install.log` | Whether the installer finished. It should end with **Done!**; an **ERROR** line says what went wrong. |
| `urusai_captures/STATUS.txt` | Whether the reader is running, and whether it found the L2 button (`button: watching L2 …`). |
| `urusai_captures/*.png` + `.txt` | One pair per button press: what RetroArch sent and what was read. |

- **No `STATUS.txt`:** the reader isn't running. Send `urusai_install.log`.
- **L2 does nothing, but Select + Y works:** send `STATUS.txt`. The button line says whether L2 was found.
- **Neither works and no `.png` appears:** in the RetroArch menu, check *Settings → AI Service*:
  - AI Service is **ON**
  - Output is **Speech Mode**
  - the URL is `http://127.0.0.1:4404/`
- **A `.png` appears but it reads the wrong thing, or a word is skipped:** send the `.png` and `.txt` files.

## Updating

Copy the new `PokemonUrusai` folder and `.sh` over the old ones in `ports`, then run **Install Pokemon Urusai** again. Your `urusai_settings.txt` is kept.

## Uninstalling

Over SSH, run `sudo /opt/urusai/install/darkos/uninstall.sh`. It removes the reader and puts your RetroArch settings back. `urusai_captures` and `urusai_settings.txt` are kept.
