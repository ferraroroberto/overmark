# Install, update and migrate Overmark

Overmark installs, updates and migrates the way any app in the toolbox does: clone it and run one `setup.bat`. An update is a pull plus a restart. A migration, onto a fresh clone on the same PC, is one `setup.bat` call. None of them ever resets or overwrites what a PC has configured.

## Install

You need Windows 10 or 11, `git`, and Python 3.12 or newer (the `py` launcher, or `python` on `PATH`). Only for recording: [ffmpeg](https://ffmpeg.org/download.html) on `PATH`, or its location in `recording.ffmpeg_path`. Only for `tray.bat --restart`: the shared tray helper that `fleet-config`'s `install.ps1` puts in your user profile; starting and quitting work without it.

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
4. ends with two lists: the required items, each `ok`, `missing` or `unknown`, and the optional features, each `available`, `off` or `unknown` with what it unlocks.

Setup has succeeded when it ends with `Setup complete` and exits 0; an optional feature that is `off` never changes that. The optional features:

- **git**, for updates and the restart's build check.
- **ffmpeg**, for recording (`off` until ffmpeg is installed; everything but recording works without it).
- **Restart helper** (`off` without `fleet-config`; then restart by quitting from the tray menu and running `.\tray.bat`).

`.\setup.bat -WhatIf` lists every change it would make, makes none, and prints the same checklist.

**Start at log on** is not registered by `setup.bat` (`-Startup` only reports that). Put a shortcut to `tray.bat` in the Startup folder (`Win+R`, `shell:startup`), or register the folder in the app launcher.

### Uninstall

1. Quit Overmark from its tray menu.
2. Remove what you added to start it: the shortcut in `shell:startup`, or the app launcher entry. Overmark registers no autostart, scheduled task or service of its own.
3. Delete the folder. Keep a copy of `config.json` first if you may want your settings back.
4. Optional: delete `%LOCALAPPDATA%\Overmark` (the log). Your recordings are yours; delete them only if you mean to.

## Update

```powershell
git pull --ff-only
.\setup.bat
.\tray.bat --restart
```

Without the restart helper, quit Overmark from its tray menu and run `.\tray.bat` instead of the last line.

Overmark rewrites no tracked file while it runs (`config.json` and its temporary and backup files are gitignored; the log and recordings are written outside the folder by default), so the pull fast-forwards on a checkout you have not edited.

`setup.bat` on a configured PC is safe, and it is how a changed `requirements.txt` is installed and a new setting reaches `config.json`:

- An existing value is never changed. A key the sample has and the file lacks is added, after a timestamped backup beside it (`config.json.bak-<YYYYmmdd-HHMMSS>`), and the added key names are printed, never values. The app already uses that key's default, so adding it changes nothing you see.
- A `config.json` that does not parse is left alone and reported, and the run exits 1.
- A second run reports `unchanged` and writes nothing.

## Migrate

What moves is declared in `[install.migrate]` of `.fleet.toml`, and it is one file: `config.json` (hotkeys, presets, sizes, key map, keep-awake, recording and toolbar settings). Overmark keeps no database, certificate or secret, reads no `.env` and shares no runtime-data folder. The installer does the whole move; nothing here or in `setup.bat` deletes the old copy.

**Reinstall in the same folder (the usual case).** It works whatever version the installed copy is, because it runs from a fresh clone and never runs the old copy's code. The installed folder must be a git clone. Run these in order from `<root>`, the folder that holds the app's folder (`overmark` below):

```powershell
cd <root>
git clone <repository URL> overmark.incoming          # git -C overmark remote get-url origin prints the URL; run nothing in the clone yet
.\overmark.incoming\setup.bat -Replace overmark -WhatIf   # read the backup name and every step; nothing changes
.\overmark.incoming\setup.bat -Replace overmark
```

It stops Overmark, renames `overmark` to `overmark.bak-YYYYMMDD-N` (uncommitted edits stay there), moves `overmark.incoming` to `overmark`, copies `config.json`, installs, starts the tray and passes only when the build probe on port 8467 serves the new clone's commit from a process in that clone. The path is unchanged, so a Startup shortcut or an app launcher entry needs no edit. On a copy whose `setup.bat` already has `-InPlace`, `.\overmark\setup.bat -InPlace` does the same and makes the clone itself.

**Beside it (another folder, or an old copy that is not a git clone):**

```powershell
git clone <repository URL> <new folder>
cd <new folder>
.\setup.bat -MigrateFrom <old folder> -StopOld
```

`-StopOld` is needed on the same PC: only one Overmark runs at a time. Add `-WhatIf` to see every step without any change.

Only you can do these steps:

- **Check two settings** in `config.json`: `recording.folder` and `recording.ffmpeg_path` are usually empty. The installer rewrites a value that starts with the old folder, but a relative path now resolves from the new one, and recordings or an ffmpeg you kept inside the old folder stay behind: move them out and set the new location.
- **Repoint** whatever stores the old path, after a `-MigrateFrom` into another folder (the shortcut in `shell:startup`, the app launcher entry): the run lists what still points at it.
- **Verify by eye:** `Ctrl+Alt+D` (or your own hotkey) draws, Settings shows your values, and, if you record, a short recording lands where you expect.
- **Fall back** if verify fails (the report names the step): quit the new copy from its tray menu, rename the new folder away and the backup to the original name (after `-MigrateFrom`, the old folder is where it was), and run its `tray.bat`; it is untouched.
- **Retire the old copy** once you are sure the new one works, by deleting it yourself. An agent working through this playbook asks you before it deletes anything.

The log (`%LOCALAPPDATA%\Overmark\Overmark\overmark.log`) and your recordings (by default the `Overmark` folder under your Videos folder) live outside the app folder, so a migration on the same PC leaves them where they are.
