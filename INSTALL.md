# Installing Pokémon Urusai on the RGB20 Pro (dArkOS)

**The read-aloud button is SELECT + Y.** The installer sets it up for you.

This takes about 10 minutes, once. After that, the reader starts by itself every time the handheld boots. It needs no Wi-Fi and no PC.

## What you need

- The release zip, e.g. `PokemonUrusai-0.2.1.zip`. The zip on the GitHub page isn't enough, because it doesn't include the 103 MB dictionary.
- The RGB20 Pro's games SD card and a card reader. Or use any other way you normally copy ROMs over.
- Your Pokémon game (Game Boy) running in **RetroArch**. On dArkOS, Game Boy games use RetroArch by default.

## 1. Copy the files to the SD card

1. Unzip `PokemonUrusai-0.2.1.zip` on your PC. You get two things:
   - a folder called `PokemonUrusai`
   - a file called `Install Pokemon Urusai.sh`
2. Put the games SD card in your PC and open the `ports` folder on it. It's the same place as your `gb` folder, usually shown as **EASYROMS**.
3. Copy **both** the `PokemonUrusai` folder and `Install Pokemon Urusai.sh` into `ports`. Don't put the `.sh` file inside the folder.
4. Eject the card safely and put it back in the handheld.

## 2. Run the installer

1. Turn on the RGB20 Pro.
2. In EmulationStation, open **Ports**. If you don't see the new entry, go to *Start → Game Settings → Update Gamelists* (or restart).
3. Start **Install Pokemon Urusai**. A text screen shows the progress for about a minute and ends with **Done!**. It then returns to the menu by itself.

The installer does the following:

- copies everything to `/opt/urusai`
- starts the reader in the background, now and at every boot
- turns on RetroArch's AI Service:
  - Speech mode
  - address `http://127.0.0.1:4404/`
  - pause on
- sets the button to **Select + Y**. On dArkOS every RetroArch hotkey is Select + a button, and Game Boy games don't use Y.
- backs up your RetroArch settings first (`retroarch.cfg.urusai-backup`)
- writes `urusai_install.log` to the games SD card

**Important:** run the installer while no game is open. RetroArch reads its settings when a game starts.

## 3. (Optional) Use a different button

Select + Y is already set up. To change it, start a game and open the RetroArch menu (**Select + X**). Go to *Settings → Input → Hotkeys → AI Service* and press the new button, then *Main Menu → Configuration File → Save Current Configuration*. dArkOS doesn't save menu changes by itself, so this last step matters.

## 4. Try it

1. Go to any text box in the game, for example talking to someone.
2. Hold **Select** and press **Y**. The game pauses and the text is read aloud in Japanese.
3. Press **Select + Y** again to continue.

What it reads:

| On screen | It says |
|---|---|
| A text box at the bottom | the whole text box |
| A menu with ▶ (battle, items, Pokémon) | any message, then the option the ▶ points at |
| Anything else (e.g. the Pokédex) | all the text on screen |

## If it doesn't talk

Put the games SD card in your PC and check these files:

| File | What it tells us |
|---|---|
| `urusai_install.log` | Whether the installer finished. It should end with **Done!**; an **ERROR** line says what went wrong. |
| `urusai_captures/STATUS.txt` | Whether the reader is running. It's rewritten at every boot. |
| `urusai_captures/*.png` + `.txt` | One pair per button press: what RetroArch sent and what was read. |

- **No `STATUS.txt`:** the reader isn't running. Send `urusai_install.log`.
- **`STATUS.txt` exists, but no `.png` after pressing Select + Y:** RetroArch isn't calling the reader. In the RetroArch menu, check *Settings → AI Service*:
  - AI Service is **ON**
  - Output is **Speech Mode**
  - the URL is `http://127.0.0.1:4404/`

  Also check that *Settings → Input → Hotkeys → AI Service* shows **Y**.
- **A `.png` appears but you hear nothing, or it reads the wrong thing:** send the `.png` and `.txt` files.
- **A word is skipped:** a symbol the reader hasn't learned yet (some numbers, ♂/♀, ×). Send the captures and it'll be added.

## Updating

Copy the new `PokemonUrusai` folder and `.sh` over the old ones in `ports`, then run **Install Pokemon Urusai** again. The button is set back to Select + Y.

## Uninstalling

Over SSH, run `sudo /opt/urusai/install/darkos/uninstall.sh`. It removes the reader and puts your AI Service settings back. The `urusai_captures` folder is kept.
