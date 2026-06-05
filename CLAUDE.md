# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

`parse_wow_chars.py` reads WoW Classic SavedVariables Lua files and generates `index.html` — a fully self-contained, no-server HTML dashboard deployed to GitHub Pages at [yorkdevelops.com/wow-anniversary-tracker](http://yorkdevelops.com/wow-anniversary-tracker/).

## Running the script

```
python parse_wow_chars.py
```

This is the only command. It reads Lua files, builds the full character dataset, substitutes `__CHARS__` / `__CLASS_COLORS__` / `__MAX_LEVEL__` / `__GEN_TIME__` placeholders in the embedded HTML template, and writes `index.html`. No build step, no dependencies beyond stdlib.

To deploy: `git add index.html parse_wow_chars.py && git push` — GitHub Pages serves from the `master` branch root.

## Architecture

Everything lives in a single Python file. The HTML/CSS/JS dashboard is embedded as `HTML = r"""..."""` at the bottom of the script and contains placeholder tokens that `main()` substitutes with `json.dumps()` of the character data.

**Data pipeline** (`gather()` function, ~400 lines):
1. Account-level DataStore addons (`WOW_SAVED_VARS`) → rich data for Dreamscythe characters
2. `DataStore_Containers.lua` → bag/bank inventory
3. Per-realm character folders (`WOW_ACCOUNT_DIR/<Realm>/<CharName>/SavedVariables/`) → AutoBiographer events, Skillet class/race identity, AnniversaryAchievements
4. `profileKeys` fallback → catches characters registered with DataStore but never synced

**Data sources and what they provide:**

| Source | Data |
|---|---|
| `DataStore_Characters.lua` | Level, class, race, money, XP, played time, zone, guild, last login |
| `DataStore_Crafts.lua` | Professions with rank/max (riding skills filtered out) |
| `DataStore_Inventory.lua` | Average equipped item level |
| `DataStore_Quests.lua` | Active quest titles |
| `DataStore_Containers.lua` | Bag/bank contents (item names + counts + quality) |
| `AutoBiographer.lua` (per-char) | Event timeline, zones explored, played time |
| `Skillet-Classic.lua` (per-char) | Name, class, race, faction for non-DataStore chars |
| `AnniversaryAchievements.lua` (per-char) | Completed achievements with timestamps |
| Folder name fallback | Name + realm when no addon data exists |

**Lua parsing:**
- `LuaParser` — recursive descent parser for single-variable files (`_load()`)
- `_parse_all_vars()` — parses all `VarName = { ... }` assignments from one file (used for multi-variable files like `AutoBiographer.lua`)
- `_skillet_who()` — regex shortcut for the small `SkilletWho = { ... }` block

**Character key format:** `"Realm|CharName"` (e.g. `"Dreamscythe|Eluninis"`) used as the internal dict key throughout `gather()`.

**Data source priority:** DataStore (`source="DataStore"`) > Skillet (`source="Skillet"`) > folder name (`source="FolderName"`) > profileKey orphan (`source="ProfileKey"`). AutoBiographer enriches all sources.

**Level derivation for non-DataStore chars:** max `LevelNum` from AutoBiographer `levelup` events.

## WoW file paths (hardcoded config block at top of script)

```python
WOW_SAVED_VARS  = ...\_anniversary_\WTF\Account\383258958#1\SavedVariables
WOW_ACCOUNT_DIR = ...\_anniversary_\WTF\Account\383258958#1
WOW_ADDONS_DIR  = ...\_anniversary_\Interface\AddOns
```

Realm subfolders sit directly under `WOW_ACCOUNT_DIR` (e.g. `Dreamscythe\`, `Defias Pillager\`, `Doomhowl\`). The script auto-discovers all of them — no hardcoded realm list.

## HTML dashboard structure

The embedded template has:
- **Card grid** — one card per character, class-colored, click to open detail modal
- **Modal with tabs:** Overview · Timeline · Zones · Achievements · Inventory
- **Timeline** — AutoBiographer events filtered/deduplicated, filterable by type in the UI
- **Inventory** — Bag0-4 (equipped bags) + Bag100 (bank), item quality color-coded

The template uses `__CHARS__` (JSON array), `__CLASS_COLORS__` (JSON object), `__MAX_LEVEL__` (int), `__GEN_TIME__` (string) as substitution tokens. Do not use triple-quotes inside the template.

## Extending to Retail WoW

Change `WOW_SAVED_VARS` to point at `_retail_\WTF\Account\...\SavedVariables`. The DataStore addon format is identical. Adjust `MAX_LEVEL = 80` (or current retail cap).

## Known data gaps

- **Journalator** — archive data is compressed, not parseable
- `AN_` achievement entries — intentional blank stubs in the addon itself
- Characters with only a folder name have no class/level/race data until they log in with Skillet installed
