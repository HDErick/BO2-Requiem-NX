# BO2 Requiem Compressor

**https://hderick.github.io/BO2-Requiem-NX/**

Installs Black Ops II Zombies and Multiplayer from your own PC copy, for **Android** or the
**Nintendo Switch**, with optional compression. It runs entirely in your browser: your game files
are read on your device and never uploaded.

1. **Choose game folder**: the PC folder that holds `zone` and `sound` (the one with `t6zm.exe`).
2. Pick the game modes. The page shows which of Zombies, Multiplayer and Campaign your copy has,
   and how big each one is. Only the checked modes are installed.
   * Zombies and Multiplayer are checked when found.
   * Campaign starts unchecked: BO2 Requiem doesn't play it yet, and it is about 9 GB.
   * At least one of Zombies or Multiplayer is needed.
3. Pick the platform:
   * **Android** (the default): the game files in a `BO2` folder.
   * **Nintendo Switch**: the game in `switch/t6game/`, with the latest release's `t6zm.nro`,
     `t6mp.nro` and `t6game.nro`.
4. Pick the compression:

   | Level | What changes | Retail game (23.6 GB) | Without the campaign (14.4 GB) |
   |---|---|---|---|
   | **Lossless** | nothing: image packs and loaded sound banks are stored compressed | 22.0 GB | 13.1 GB |
   | **Medium** | textures at most 512 px; sound up to 12 kHz, 14 bits | 16.9 GB | 9.5 GB |
   | **Maximum** | textures at most 256 px; sound up to 8 kHz, 12 bits, mono | 10.7 GB | 5.5 GB |

5. **Install to folder** (desktop Chrome or Edge: the SD card, your device's storage or a staging
   folder), or **Save as ZIP** (any current desktop browser).
   * Switch: extract the ZIP to the SD card's root, then open t6game from hbmenu in application
     mode.
   * Android: the ZIP holds the `BO2` folder.

Installing again to the same folder continues a cancelled install, and keeps the files that are
already done.

## Run it locally

```
python installer/serve.py
```

Then open http://127.0.0.1:8070/ in Chrome or Edge. Before serving, it puts the latest release's
Switch executables next to the page (it needs the GitHub CLI signed in); `--no-release` skips that,
and then the page offers Android only.

## How it is published

`.github/workflows/installer-pages.yml` deploys `installer/web` to GitHub Pages:
* on every push that changes the installer;
* whenever a release is published or edited (so the page always carries the newest executables);
* by hand.

`installer/fetch_release.py` takes the `.nro` files from the latest release: its `.nro` assets,
or those inside its `.zip` assets. The page itself is static; `web/generated/t6pack.wasm` (the
packer) is built from the port's sources.
