# Todo Companion

Todo Companion is a Windows-first, local-first floating quest card. It keeps a
small grouped checklist above normal desktop windows and stores everything in a
readable JSON file. No account, network connection, or backend is required.

## Features

- Frameless, always-on-top, transparent Qt tool window
- Cream paper, purple ink, mustard footer, and pixel-trim styling
- Header-only dragging with visible minimize and exit controls
- Ordered categories and keyboard-accessible quest checkboxes
- Progress, next-quest hint, scrolling, and struck-through completed quests
- Automatic atomic JSON persistence
- Add, complete/reopen, edit, and delete quests
- Drag quests to reorder them or move them between categories
- Add, rename, recolor, and delete categories with safe confirmations
- Mark all complete/incomplete and delete all completed quests
- Pixel-art orange cat with five sprite-sheet states: idle, sleeping, a
  one-shot wake-up stretch, celebrating completions, and reacting to drags
- Minimize to the Windows system tray and restore from its icon/menu
- Rename the card, reset with backup, open the data folder, and exit
- Saved window position clamped to a visible monitor on startup
- Confirmation-based recovery for malformed data; the original is never
  silently overwritten

The card has a fixed logical size of `380x680`. The `_` button minimizes to the
Windows tray when available; the `X` button exits the app completely.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer

Python 3.11 was used for the verified development environment.

## PowerShell Setup

```powershell
cd <path-to>\todo-companion
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python -m todo_companion
```

If script activation is disabled, use the venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m todo_companion
```

## Git Bash Setup

```bash
cd /c/<path-to>/todo-companion
py -3.11 -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest -q
python -m todo_companion
```

## Using The Card

- Drag the project-title header to move the window.
- Select a checkbox with the mouse, or use Tab and Space/Enter.
- Drag a quest row using its `::` grip or text area to move it up/down. Drop it
  under another category to move it there. The new order saves immediately.
- Use the `...` beside a quest to edit or delete that quest.
- Use the `...` beside a category to rename it, choose its color, or delete it
  and its contained quests.
- Use the header `...` menu to add quests/categories, rename the card, mark all
  quests complete/incomplete, or delete all completed quests.
- Select `_` to minimize. Click/double-click the tray icon, or choose
  `Show Todo Companion` from its menu, to restore the card.
- `Reset sample data...` asks for confirmation and preserves the prior JSON as
  `tasks.backup-YYYYMMDD-HHMMSS.json`.
- `X` and `Exit` both close the application completely.

The orange cat falls asleep after 20 seconds without activity, stretches awake
on input (a one-shot `WAKE_UP` transition), celebrates a completed quest, and
gets angry while the header is being dragged. All five states play from
sprite sheets in `asset/cat_animation/` (six 64x64 frames each, hard-edged
transparent pixel art drawn with no smoothing). A state whose sheet is missing
or invalid falls back to the original Qt-painted cat.

Sheets are regenerated from the raw renders in `asset/cat_animation/_source/`
with `python tools/build_cat_sheet.py <NAME>`. The per-state commands, the
sheet format contract, and how to add a new state are documented in
`asset/cat_animation/README.md`; the tool needs `pip install -e ".[tools]"`.

## Local Data

The default data file is:

```text
%LOCALAPPDATA%\TodoCompanion\tasks.json
```

The file is created on the first mutation, not merely by opening the app. Saves
write and flush a temporary file in the same directory before using atomic
replacement. To use a development or portable data file, set:

```powershell
$env:TODO_COMPANION_DATA_PATH = "C:\temp\todo-companion\tasks.json"
python -m todo_companion
```

The JSON has schema version 1 and can be edited while the app is closed. IDs
must remain unique and completion timestamps must be timezone-aware ISO-8601
values. A malformed or incompatible file produces a recovery prompt. Canceling
leaves it untouched; confirming recovery first creates a timestamped backup.

## Tests

Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Qt tests set the offscreen platform automatically. Tests inject temporary or
in-memory repositories and never read or write the real task data file.

Coverage includes model validation and round trips, category colors, UTC
completion semantics, path overrides, missing/corrupt data, atomic persistence,
backups, service mutations, task movement and drop targeting, progress ordering,
Qt window flags, checkbox signaling, cat state transitions, UI refresh, position
clamping, and Microsoft Graph mapping contracts.

## Packaging

After development launch and tests succeed, an unsigned local Windows build can
be produced with PyInstaller:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[package]"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed `
  --name TodoCompanion --paths src `
  --add-data "asset;asset" `
  src\todo_companion\__main__.py
```

The `--add-data "asset;asset"` flag bundles the cat sprite sheets; without it
the packaged cat falls back to the Qt-painted version.

The executable is written to `dist\TodoCompanion\TodoCompanion.exe`. Windows
SmartScreen can warn about an unsigned executable; code signing is outside this
local MVP.

## Microsoft To Do

Microsoft To Do sync is a documented phase-2 option and is disabled in this
MVP. The base app does not import MSAL, request credentials, or make network
calls. `integrations/microsoft_todo.py` defines the gateway boundary and tested
Graph task/status mapping so future sync does not enter UI or model code.

Any implementation must use Microsoft Graph rather than desktop UI automation
or private local files. It should:

1. Register a public/native Microsoft Entra application with a matching
   loopback redirect URI.
2. Read client/tenant/redirect values from the environment; `.env.example`
   lists names and `.env` is ignored.
3. Use delegated interactive OAuth with least-privilege `Tasks.ReadWrite` and
   any identity scopes currently required by MSAL. Never use or ship a client
   secret in this desktop app.
4. Keep tokens in Windows-protected storage, never logs, and provide an
   explicit disconnect action.
5. Sync one explicitly selected list, initially using one-way import plus local
   completion push. Map Graph IDs to `remote_id` and prefer surfaced remote
   state when conflicts cannot be resolved safely.
6. Run authentication and Graph HTTP requests in a Qt thread pool/worker, then
   return results to the GUI thread through signals.

Optional dependencies are isolated from the local app:

```powershell
python -m pip install -e ".[graph]"
```

Relevant endpoints are `GET /me/todo/lists`, list task/delta queries, `POST` to
create tasks, and `PATCH` to update completion. Verify current API behavior and
permissions against the Microsoft Graph To Do documentation before enabling
the feature.

## Structure

```text
src/todo_companion/
  app.py                 QApplication wiring, recovery, Ctrl+C handling
  models.py              validated dataclasses and serialization
  repository.py          atomic JSON persistence and backups
  service.py             behavior-oriented task mutations
  sample_data.py         first-run/reset defaults
  paths.py               AppData and environment override resolution
  ui/                    painted card and standard Qt controls
  integrations/          optional provider contracts
asset/cat_animation/      sprite sheets per cat state (_source/ holds raw renders)
tools/build_cat_sheet.py  regenerates a sprite sheet from a raw render
tests/                    domain, persistence, integration, and Qt tests
```
