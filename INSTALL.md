# Installing Pokémon Urusai on the RGB20 Pro (dArkOS)

This takes about 10 minutes, once. After that, the reader starts by itself every time the handheld boots. It needs no Wi-Fi and no PC.

## What you need

- The release zip, e.g. `PokemonUrusai-0.2.0.zip`. The zip on the GitHub page isn't enough, because it doesn't include the 103 MB dictionary.
- The RGB20 Pro's games SD card and a card reader. Or use any other way you normally copy ROMs over.
- Your Pokémon game (Game Boy) running in **RetroArch**. On dArkOS, Game Boy games use RetroArch by default.

## 1. Copy the files to the SD card

1. Unzip `PokemonUrusai-0.2.0.zip` on your PC. You get two things:
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
- backs up your RetroArch settings first (`retroarch.cfg.urusai-backup`)

## 3. Pick the "read aloud" button (once, in RetroArch)

1. Start Pokémon.
2. Open the RetroArch menu. On dArkOS this is usually **Select + X**.
3. Press B (back) until you reach the **Main Menu**, then go to *Settings → Input → Hotkeys*.
4. Choose **AI Service** and press the button you want to use. Something your son won't press by accident works best, like **R3** (press in the right stick) if your RGB20 Pro has it. Otherwise use a spare shoulder button.
   - If dArkOS uses a "hotkey enable" button (usually **Select**), hotkeys only work while that button is held. In that case the combo is **Select + your button**.
5. Go back to the Main Menu, then *Configuration File → Save Current Configuration*.
6. Close the menu.

## 4. Try it

1. Go to any text box in the game, for example talking to someone.
2. Press your AI Service button. The game pauses and the text is read aloud in Japanese.
3. Press the button again to continue.

What it reads:

| On screen | It says |
|---|---|
| A text box at the bottom | the whole text box |
| A menu with ▶ (battle, items, Pokémon) | any message, then the option the ▶ points at |
| Anything else (e.g. the Pokédex) | all the text on screen |

## If it doesn't talk

- **Check the AI Service settings.** In the RetroArch menu, open *Settings → AI Service* and make sure:
  - AI Service is **ON**
  - Output is **Speech Mode**
  - the URL is `http://127.0.0.1:4404/`
  - Pause is **ON**
- **Check that the reader got the screen.** Look in the `urusai_captures` folder on the games SD card.
  - **Files appear after each press:** the reader is working. If it was silent or read something wrong, send those files (each `.png` comes with a `.txt` of what it read).
  - **No files appear:** RetroArch isn't reaching the reader. Re-check the settings above, then restart the handheld.
- **A word is skipped:** a symbol the reader hasn't learned yet (some numbers, ♂/♀, ×). Send the captures and it'll be added.

## Updating

Copy the new `PokemonUrusai` folder and `.sh` over the old ones in `ports`, then run **Install Pokemon Urusai** again. Your RetroArch button stays as it is.

## Uninstalling

Over SSH, run `sudo /opt/urusai/install/darkos/uninstall.sh`. It removes the reader and puts your AI Service settings back. The `urusai_captures` folder is kept.
