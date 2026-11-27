# Install, update and move Overmark

Overmark moves to another Windows PC the way any app in the toolbox does: clone it and run one `setup.bat`. An update is a pull plus a restart. Neither resets or overwrites what a PC has configured.

## What you need

- Windows 10 or 11, Git, and Python 3.12 or newer (the `py` launcher, or `python` on `PATH`).
- Only for recording: [ffmpeg](https://ffmpeg.org/download.html) on `PATH`, or its location in `recording.ffmpeg_path`.
- Only for `tray.bat --restart`: the shared tray helper that `fleet-config`'s `install.ps1` puts in your user profile. Starting and quitting work without it.

## Fresh PC

```powershell
git clone <repository URL> overmark
cd overmark
.\setup.bat
.\tray.bat
```

`setup.bat` runs `src/installer.py`, which:

1. creates `.venv` when it is missing;
2. installs `requirements.txt`, and later reinstalls only when that file changed (its hash is kept inside `.venv`);
3. creates `config.json` from `config.sample.json` when it is missing;
4. ends with two lists: the required items, each `ok`, `missing` or `unknown`, and the optional features, each `available`, `off` or `unknown` with what it unlocks. Setup has succeeded when it ends with `Setup complete` and exits 0; an optional feature that is `off` never changes that.

On a fresh PC these optional features may read `off`:

- **ffmpeg**, for recording (`off` until ffmpeg is installed; everything but recording works without it).
- **Restart helper** (`off` without `fleet-config`; then restart by quitting from the tray menu and running `.\tray.bat`).

`.\setup.bat -WhatIf` lists every change it would make, makes none, and prints the same checklist.

**Start at log on** is not registered by `setup.bat` (`-Startup` only reports that). Put a shortcut to `tray.bat` in the Startup folder (`Win+R`, `shell:startup`), or register the folder in the app launcher.

## Update

```powershell
git pull --ff-only
.\tray.bat --restart
```

Nothing else is needed. Overmark rewrites no tracked file while it runs (`config.json` and its temporary and backup files are gitignored; the log and recordings are written outside the folder by default), so the pull fast-forwards on a checkout you have not edited.

Without the restart helper, quit Overmark from its tray menu and run `.\tray.bat` instead.

Run `.\setup.bat` between the two commands in one case, and whenever you like otherwise:

- **The pull changed `requirements.txt`:** `setup.bat` installs the new requirements.
- **A new setting arrived and you want to see it in `config.json`:** the app already uses its default; `setup.bat` writes the key into the file. An existing value is never changed. Before adding a key it copies the file to `config.json.bak-<YYYYmmdd-HHMMSS>`, and it prints the names of the keys it added, never values. A `config.json` that does not parse is left alone and reported, and the run exits 1. A second run reports `unchanged` and writes nothing.

## Migrate from an existing install

Use this on a PC that already runs an older copy of Overmark: one that may not be a git clone, and may live at another path. The old folder stays as it is until the new copy is verified, and it is deleted only when you say so.

1. **Clone fresh beside it.** `git clone <repository URL> <new folder>`, next to the old folder; never clone over the old one.
2. **Copy this PC's own file across.** From the old folder into the new one, at the same relative path:
   - `config.json` (the root of the folder): hotkeys, presets, sizes, key map, keep-awake and recording settings.

   That is the whole list. Overmark keeps no database, certificate or secret, and reads no `.env`. Do not copy `.venv`, `__pycache__`, `config.json.tmp` or anything tracked by git.
3. **Check two settings in that file.** `recording.folder` and `recording.ffmpeg_path` are usually empty. A value that is a relative path, or points inside the old folder, resolves to the wrong place from the new one: move the recordings or ffmpeg out of the old folder and set the new location.
4. **Top it up.** In the new folder run `.\setup.bat -WhatIf`, read what it would change, then `.\setup.bat`. `config.json` gains only the keys it lacks.
5. **Stop the old copy.** Quit it from its tray menu. Only one Overmark runs at a time, so the new one exits at once while the old one is still up. Then remove or repoint whatever starts the old copy: the shortcut in `shell:startup`, or its entry in the app launcher.
6. **Start the new one.** `.\tray.bat`, and set up start at log on as under "Fresh PC" if you want it.
7. **Verify it.**
   - The running build is the new clone: the `git_sha` from `Invoke-RestMethod http://127.0.0.1:8467/api/version` equals `git rev-parse HEAD` in the new folder. It can take a few seconds to answer after the start.
   - `Ctrl+Alt+D` (or your own hotkey) draws, Settings shows your values, and, if you record, a short recording lands where you expect.

   If anything is wrong, quit the new copy from its tray menu and start the old one again: it is untouched.
8. **Retire the old folder, only after you confirm.** Nothing here or in `setup.bat` deletes the old copy. Rename it first (for example `<old folder>.retired`), run on the new copy for a while, and delete it yourself once you are sure. An agent working through this playbook asks you before it deletes anything.

These live outside the app folder, so a migration on the same PC leaves them where they are:

- the log, `%LOCALAPPDATA%\Overmark\Overmark\overmark.log`;
- recordings, by default in the `Overmark` folder under your Videos folder, including the segments of an interrupted recording.

## Uninstall

1. Quit Overmark from its tray menu.
2. Remove what you added to start it: the shortcut in `shell:startup`, or the app launcher entry. Overmark registers no autostart, scheduled task or service of its own.
3. Delete the folder. Keep a copy of `config.json` first if you may want your settings back.
4. Optional: delete `%LOCALAPPDATA%\Overmark` (the log). Your recordings are yours; delete them only if you mean to.
