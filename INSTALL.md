# Installing Pokémon Urusai on the RGB20 Pro (dArkOS)

*On an RG35XXSP or another Knulli handheld? See [Knulli](#knulli-rg35xxsp) below: same zip, different steps.*

**The text is read aloud automatically** as it appears: dialogue, and menu choices as the cursor moves. **Tap L2** to hear it again; press **Select + L2** (or double-tap L2) to switch the reader off or on. The game keeps running while it talks.

The install takes about 10 minutes, once. After that, the reader starts by itself every time the handheld boots. It needs no Wi-Fi and no PC.

## What you need

- The release zip, e.g. `PokemonUrusai-0.6.2.zip`. The zip on the GitHub page isn't enough, because it doesn't include the 103 MB dictionary.
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
| A new text box | the box **in one go, lines back to back**, as soon as it has printed (line 1's speech is made while line 2 prints); after a scroll, **only the new line** |
| A menu or question opens | the question (if not read yet), a rising "pop" sound, then every option in the **menu voice**, with a short "pip" right after the selected one (none for はい/いいえ) |
| The cursor moves | just the newly selected option (はい/いいえ with their sound; a low "tok" on the first or last option of other menus) |
| The menu closes | a falling "pop" sound |
| A big grid (name entry) | just the selected letter |
| You press any game button (A, B, Start, D-pad) while it's talking | it **stops at once**, whatever it was saying. If the screen stays the same it stays quiet; when something new appears, only the new part is read. |
| **Tap L2** | the whole screen again, once (e.g. the Pokédex page or a full menu) |
| **Select + L2** (or **double-tap L2**) | The reader off/on. 「よみあげ オフ」 / 「よみあげ オン」 is said and shown in a box on screen. While it's off it says nothing and presses no keys. |

If nothing is read after starting a game, press **L2** once (or **Select + Y**). **Select + Y** also switches the reader off and on.

## 4. Settings (volume, voice, button)

Open `urusai_settings.txt` on the games SD card with any text editor. Changes apply on the next button press, with no restart needed.

| Setting | Default | What it does |
|---|---|---|
| `auto_read` | `on` | Read new text and menu choices automatically. `off` = only when you press the button. |
| `autostart` | `on` | Switch the reader on by itself when a game starts |
| `button` | `L2` | Tap = say it again, double tap = reader off/on: `L1 R1 L2 R2 L3 R3 SELECT START`, or `off` |
| `toggle_combo` | `SELECT+L2` | Press both together to switch the reader off/on (said and shown on screen), or `off`. The installer turns off any RetroArch hotkey on Select + L2 (and puts it back on uninstall). |
| `sound_cues` | `on` | Sounds when a menu opens or closes and at the first/last option (the selection sounds are always on) |
| `menu_position` | `off` | Say the position after the selected option, e.g. 「2ばんめ」 |
| `menu_voice` | `tohoku-4` | Voice for menu options (Tohoku, 4 semitones lower) |
| `interrupt` | `on` | Stop talking whenever you press a game button |
| `volume` | `200` | Voice volume in %. `100` is natural; higher is louder over the music. All voices are levelled to the same loudness, and it's limited so it never crackles. |
| `voice` | `tsukuyomi` | Dialogue voice: `tsukuyomi` (natural, see "Natural voice") or a standard one: `tohoku`, `tohoku_happy`, `mei`, `mei_happy`, `mei_bashful`, `nitech`. Add `+N`/`-N` semitones. |
| `speed` | `0.95` | `1.0` is normal; `0.85` is slower |
| `option_pause` | `300` | Pause between menu options and choices, in milliseconds. Text itself is read in one flow, without pauses. |
| `captures_keep` | `50` | How many recently read screens to keep in `urusai_captures` (each is about 2 KB). `0` saves none. |
| `gba_learn` | `on` | GBA games: also keep a screen now and then when nothing could be read (see "GBA games") |

**Numbers:** counters are read the Japanese way (1こ いっこ, 3びき さんびき, 8ほん はっぽん, 6かい ろっかい), HP/PP 15/20 as 「20のうち15」, Pokédex No.007 as 「7ばん」, 9.0kg as 「9キログラム」, ×3 as 「3こ」, play time 12:34 as 「12じかん34ぷん」.

**Speed:** speech is kept in a cache in `/opt/urusai/cache` (up to 150 MB; the oldest is removed first), and common menu words are made when the handheld starts. Most things play at once, even after a restart.

**About captures:** each time something is read, the screen and the text are saved. Only the newest `captures_keep` are kept and older ones are deleted automatically, so the folder can't fill up: 50 captures is about 100 KB. They're only useful for fixing misreads. Set it to `0` if you don't need them.

If the voice is still hard to hear, you can also lower the game's own volume. Open the RetroArch menu (**Select + X**), go to *Settings → Audio → Volume*, then *Main Menu → Configuration File → Save Current Configuration*.

## Natural voice (this version: experimental)

Dialogue can be read in a much more natural voice, つくよみちゃん, made by [piper-plus](https://github.com/ayutaz/piper-plus). It works offline like everything else, but it is slow: making a new line takes a few seconds on the handheld. So:

- the **first time** a line comes up, it is said at once in the standard voice, as before;
- meanwhile the natural version is made in the background and saved;
- **every time after that**, the line is said in the natural voice. Menu words, battle messages and anything else that repeats soon always sound natural.

**Getting the voice (once, about 40 MB):**

- Easiest: connect the handheld to Wi-Fi and run the installer. It downloads the voice by itself and says "Natural voice: ready".
- Without Wi-Fi: on a computer, open <https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan>, download `tsukuyomi-chan-6lang-fp16.onnx` and `config.json`, put both in a folder called `tsukuyomi` on the SD card (next to your game folders), and run the installer.

If the voice isn't there, the standard voice is used and nothing else changes. To switch the natural voice off, set `voice = tohoku` in the settings file. `urusai_captures/STATUS.txt` says whether it's in use.

If the game stutters while a natural line is being made, tell me: it's limited to three of the four processor cores at low priority, but this hasn't been measured on the handheld yet.

## Knulli (RG35XXSP)

New in 0.10.0 and **not yet tried on a real RG35XXSP**, so send the files listed under "If it doesn't work" if anything's off.

**What you need:** the same release zip, Wi-Fi not needed. Game Boy and GBA games must run in RetroArch, which is Knulli's default for them.

1. **Copy the files.** Unzip the release on your PC. Copy the `PokemonUrusai` folder **and** `Install Pokemon Urusai.sh` into the `ports` folder of the `roms` folder, the same one your `gb` folder is in.
   - SD card in your PC: open the partition that has the `roms` folder. If your PC can't open it, use the network instead: turn on Wi-Fi on the handheld and open `\\KNULLI\share` (Windows) or `smb://knulli` (Mac), then `roms/ports`.
2. **Show it in Ports.** On the handheld, close any game, press **Start → Game Settings → Update Gamelists**.
3. **Run the installer.** Open **Ports → Install Pokemon Urusai**. The screen stays dark for about a minute; when it's done, the handheld says 「インストール できました」. If it says 「インストール できませんでした」 instead, see "If it doesn't work".
4. **Play.** Start your Pokémon game. The reader starts by itself a few seconds after the game does.

**Buttons on the RG35XXSP:**

| Button | What it does |
|---|---|
| **L2** | Say it again |
| **Select + L2** (or double-tap L2) | Reader off/on, with 「よみあげ オフ／オン」 |
| **MENU + R1** | Knulli's own AI Service hotkey: starts or stops the reader by hand, if it hasn't started by itself |

Any other button cuts off the speech, as on dArkOS.

**Where things are:** settings in `roms/urusai_settings.txt` (the same options as above), captures and `STATUS.txt` in `roms/urusai_captures`, the install log in `roms/urusai_install.log`. The reader itself is in `/userdata/system/urusai` and starts as a Knulli service: you can see it, and switch it off, under **System Settings → Services → urusai**.

**What the installer changes:** it adds six lines starting with `global.retroarch.` to `/userdata/system/batocera.conf` (Knulli rewrites RetroArch's own settings at every game start, so they have to go there), and keeps a copy of the file as `batocera.conf.urusai-backup`. If you had Knulli's own **AI Game Translation** switched on, the reader's lines take over from it.

**If it doesn't work:** send `roms/urusai_install.log`, `roms/urusai_captures/STATUS.txt` and `/userdata/system/logs/urusai.log`. STATUS.txt's `button:` line says whether L2 was found; the RG35XXSP's buttons send unusual codes, so the reader reads Knulli's own button map to find them.

**Updating:** copy the new release over the old one in `ports` and run the installer again. **Uninstalling:** **Ports → Uninstall Pokemon Urusai** (Update Gamelists first if it isn't listed).

The natural voice (つくよみちゃん) is installed on dArkOS only for now; on Knulli the standard voice is used.

## GBA games (new, experimental)

ルビー・サファイア・エメラルド・ファイアレッド・リーフグリーン (Japanese) are read the same way as the Game Boy games: messages, menus with the ▶ cursor, L2 to hear the screen again. This part has only been tested on made-up screens so far, so expect gaps.

To help fix them: just play. While `gba_learn = on` (the default), the reader also keeps a screen every 10 seconds or so when it couldn't read anything, next to the normal captures in `urusai_captures` (same limit, so the folder can't grow). Send that folder and the gaps can be closed. Set `gba_learn = off` once it reads well.

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

## If the game pauses by itself

Fixed in 0.6.5. Earlier versions could press RetroArch's hotkey button
(the same as holding **Select**) while a game button was still down, so
RetroArch saw a hotkey such as **Select+A** (pause) or **Select+D-pad up**
(frame advance, which freezes the picture). The reader now waits until
every button is released, and holds the gamepad for that split second.

To un-pause: press **Select+A** (the pause toggle on ArkOS-based systems).
**Start** alone doesn't work, because the game itself is paused, not the
Pokémon menu. If Select+A doesn't do it, press **Select+X** to open the
RetroArch menu, choose **Resume**, and check which button is set under
*Settings → Input → Hotkeys → Pause*.

## Updating

Copy the new `PokemonUrusai` folder and `.sh` over the old ones in `ports`, then run **Install Pokemon Urusai** again. Your `urusai_settings.txt` is kept.

## Uninstalling

Over SSH, run `sudo /opt/urusai/install/darkos/uninstall.sh`. It removes the reader and puts your RetroArch settings back. `urusai_captures` and `urusai_settings.txt` are kept.
