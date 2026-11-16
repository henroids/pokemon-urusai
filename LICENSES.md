# Third-party components

| Component | Where | License |
|---|---|---|
| Open JTalk 1.11 (Nagoya Institute of Technology) | `bin/open_jtalk-aarch64` | Modified BSD |
| HTS Engine API 1.10 | statically linked into the above | Modified BSD |
| NAIST Japanese Dictionary (open-jtalk build) | `dic/` | BSD (NAIST) |
| HTS voice "tohoku-f01" (`tohoku`, `tohoku_happy`) | `voice/` | CC BY 4.0, © 2015 Intelligent Communication Network (Ito-Nose) Laboratory, Tohoku University |
| HTS voice "Mei" (`mei`, `mei_happy`, `mei_bashful`) | `voice/` | CC BY 3.0, © 2009-2013 Nagoya Institute of Technology (MMDAgent Project Team) |
| HTS voice "NIT ATR503 M001" (`nitech`) | `voice/` | CC BY 3.0, © Nagoya Institute of Technology |
| FontStructions "Pokémon Red (JP) (GB)" and "Pokémon Silver (JP) (GBC)" by Patrick H. Lauke (fontstruct.com/fontstructions/show/2623292, …/2623568); their letter shapes are part of `font/gb_jp.json` | `font/sources/` | CC BY 3.0 |

The voices' original copyright notices are in `voice/COPYRIGHT/`.

No game data, audio or text from Pokémon is included. The Game Boy tile table is built from the user's own screen captures and the two FontStructions above (each kept with its own licence and readme).

`font/gba_jp.json` holds no letter pictures: for each letter of the GBA games' fonts it stores a one-way fingerprint (hash) of its ink plus its position in the cell, which is enough to recognise text on screen but not to draw it. `tools/build_gba_font.py` computes these from the font sheets in the pret decompilation projects (pokeemerald, pokefirered, pokeruby), which are not part of this repository. `tests/gba/*.png` are made-up test screens drawn by `tools/gba_synth.py`.
