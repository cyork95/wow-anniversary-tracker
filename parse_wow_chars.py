#!/usr/bin/env python3
"""
WoW Classic Character Tracker
Parses addon SavedVariables Lua files and generates a self-contained HTML dashboard.
Run any time your WoW character data changes:  python parse_wow_chars.py
"""

import re, json
from pathlib import Path
from datetime import datetime

# ─── Config ────────────────────────────────────────────────────────────────────
WOW_SAVED_VARS  = Path(r"C:\Program Files (x86)\World of Warcraft\_anniversary_\WTF\Account\383258958#1\SavedVariables")
WOW_ACCOUNT_DIR = WOW_SAVED_VARS.parent
OUTPUT_HTML     = Path(__file__).parent / "index.html"

CLASS_COLORS = {
    "WARRIOR":     "#C79C6E",
    "PALADIN":     "#F58CBA",
    "HUNTER":      "#ABD473",
    "ROGUE":       "#FFF569",
    "PRIEST":      "#FFFFFF",
    "DEATHKNIGHT": "#C41F3B",
    "SHAMAN":      "#0070DE",
    "MAGE":        "#69CCF0",
    "WARLOCK":     "#9482C9",
    "MONK":        "#00FF96",
    "DRUID":       "#FF7D0A",
    "DEMONHUNTER": "#A330C9",
    "EVOKER":      "#33937F",
}

CLASS_NAMES = {
    "WARRIOR": "Warrior",     "PALADIN": "Paladin",      "HUNTER": "Hunter",
    "ROGUE": "Rogue",         "PRIEST": "Priest",        "DEATHKNIGHT": "Death Knight",
    "SHAMAN": "Shaman",       "MAGE": "Mage",            "WARLOCK": "Warlock",
    "MONK": "Monk",           "DRUID": "Druid",          "DEMONHUNTER": "Demon Hunter",
    "EVOKER": "Evoker",
}

RACE_NAMES = {
    "Human": "Human",        "Dwarf": "Dwarf",         "NightElf": "Night Elf",
    "Gnome": "Gnome",        "Draenei": "Draenei",     "Worgen": "Worgen",
    "Orc": "Orc",            "Troll": "Troll",         "Undead": "Undead",
    "Tauren": "Tauren",      "BloodElf": "Blood Elf",  "Goblin": "Goblin",
    "Pandaren": "Pandaren",  "VoidElf": "Void Elf",    "LightforgedDraenei": "Lightforged Draenei",
    "DarkIronDwarf": "Dark Iron Dwarf", "KulTiran": "Kul Tiran",
    "Mechagnome": "Mechagnome", "Vulpera": "Vulpera",
    "HighmountainTauren": "Highmountain Tauren", "Nightborne": "Nightborne",
    "ZandalariTroll": "Zandalari Troll", "MagharOrc": "Mag'har Orc",
    "DracthyrA": "Dracthyr", "DracthyrH": "Dracthyr",
}

MAX_LEVEL = 60  # Classic Anniversary


# ─── Lua parser ────────────────────────────────────────────────────────────────
class LuaParser:
    """Minimal recursive descent parser for WoW SavedVariable Lua table files."""

    def __init__(self, s: str):
        self.s = s
        self.p = 0
        self.n = len(s)

    def _skip(self):
        while self.p < self.n:
            if self.s[self.p] in " \t\n\r":
                self.p += 1
            elif self.s[self.p:self.p + 2] == "--":
                while self.p < self.n and self.s[self.p] != "\n":
                    self.p += 1
            else:
                break

    def _ch(self):
        return self.s[self.p] if self.p < self.n else ""

    def _eat(self, tok: str):
        self._skip()
        assert self.s[self.p:self.p + len(tok)] == tok, \
            f"Expected {tok!r} at {self.p}, got {self.s[self.p:self.p+8]!r}"
        self.p += len(tok)

    def _str(self) -> str:
        self.p += 1  # opening "
        buf = []
        while self.p < self.n and self.s[self.p] != '"':
            if self.s[self.p] == "\\":
                self.p += 1
                buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(self.s[self.p], self.s[self.p]))
            else:
                buf.append(self.s[self.p])
            self.p += 1
        self.p += 1  # closing "
        return "".join(buf)

    def _num(self):
        i = self.p
        if self._ch() == "-":
            self.p += 1
        while self.p < self.n and (self.s[self.p].isdigit() or self.s[self.p] == "."):
            self.p += 1
        t = self.s[i:self.p]
        return float(t) if "." in t else int(t)

    def _val(self):
        self._skip()
        if self.p >= self.n:
            return None
        c = self._ch()
        if c == "{":
            return self._tbl()
        if c == '"':
            return self._str()
        if c == "-" or c.isdigit():
            return self._num()
        for kw, v in (("true", True), ("false", False), ("nil", None)):
            if self.s[self.p:self.p + len(kw)] == kw:
                self.p += len(kw)
                return v
        # unknown token — skip to next delimiter
        i = self.p
        while self.p < self.n and self.s[self.p] not in ",}\n":
            self.p += 1
        return self.s[i:self.p].strip() or None

    def _tbl(self) -> dict:
        self.p += 1  # {
        result: dict = {}
        auto = 1
        while True:
            self._skip()
            if self.p >= self.n or self.s[self.p] == "}":
                if self.p < self.n:
                    self.p += 1
                break
            if self.s[self.p] == "[":
                self.p += 1
                self._skip()
                key = self._str() if self._ch() == '"' else self._num()
                self._eat("]")
                self._eat("=")
                result[key] = self._val()
            else:
                result[auto] = self._val()
                auto += 1
            self._skip()
            if self.p < self.n and self.s[self.p] == ",":
                self.p += 1
        return result

    def parse(self) -> dict:
        """Parse 'VarName = { ... }' and return the table."""
        self._skip()
        while self.p < self.n and self.s[self.p] != "=":
            self.p += 1
        if self.p >= self.n:
            return {}
        self.p += 1
        self._skip()
        return self._tbl() if self._ch() == "{" else {}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return LuaParser(path.read_text(encoding="utf-8", errors="replace")).parse() or {}
    except Exception as e:
        print(f"  WARN {path.name}: {e}")
        return {}


def _skillet_who(path: Path) -> dict:
    """Extract SkilletWho via regex — faster than full parse for this small block."""
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"SkilletWho\s*=\s*\{([^}]+)\}", txt, re.DOTALL)
    if not m:
        return {}
    return {k: v for k, v in re.findall(r'\["(\w+)"\]\s*=\s*"([^"]*)"', m.group(1))}


# ─── Data aggregation ──────────────────────────────────────────────────────────
def gather() -> list[dict]:
    chars: dict[str, dict] = {}

    # ── DataStore_Characters (core stats) ─────────────────────────────────────
    print("  DataStore_Characters…")
    db = _load(WOW_SAVED_VARS / "DataStore_Characters.lua")
    for key, info in ((db.get("global") or {}).get("Characters") or {}).items():
        if not isinstance(info, dict):
            continue
        p = key.split(".", 2)
        if len(p) < 3:
            continue
        realm, name = p[1], p[2]
        ck = f"{realm}|{name}"
        chars[ck] = {
            "name": name,
            "realm": realm,
            "level": info.get("level", 1),
            "class": info.get("englishClass", "").upper(),
            "class_display": CLASS_NAMES.get(info.get("englishClass", "").upper(), info.get("class", "")),
            "race": RACE_NAMES.get(info.get("englishRace", ""), info.get("race", "")),
            "faction": info.get("faction", "Alliance"),
            "money": int(info.get("money", 0) or 0),
            "played": int(info.get("played", 0) or 0),
            "zone": info.get("zone", ""),
            "sub_zone": info.get("subZone", ""),
            "guild": info.get("guildName", ""),
            "guild_rank": info.get("guildRankName", ""),
            "xp": int(info.get("XP", 0) or 0),
            "xp_max": int(info.get("XPMax", 1) or 1),
            "rest_xp": int(info.get("RestXP", 0) or 0),
            "last_login": int(info.get("lastLogoutTimestamp", 0) or 0),
            "bind": info.get("bindLocation", ""),
            "professions": {},
            "avg_ilvl": 0.0,
            "active_quests": [],
            "source": "DataStore",
        }

    # ── DataStore_Crafts (professions) ────────────────────────────────────────
    print("  DataStore_Crafts…")
    db = _load(WOW_SAVED_VARS / "DataStore_Crafts.lua")
    for key, info in ((db.get("global") or {}).get("Characters") or {}).items():
        if not isinstance(info, dict):
            continue
        p = key.split(".", 2)
        if len(p) < 3:
            continue
        ck = f"{p[1]}|{p[2]}"
        if ck not in chars:
            continue
        for pname, pdata in (info.get("Professions") or {}).items():
            if not isinstance(pdata, dict):
                continue
            # Skip riding skills — stored as professions in Classic but not real crafting profs
            if "Riding" in pname:
                continue
            chars[ck]["professions"][pname] = {
                "rank": int(pdata.get("Rank", 0) or 0),
                "max": int(pdata.get("MaxRank", 300) or 300),
                "primary": bool(pdata.get("isPrimary")),
                "secondary": bool(pdata.get("isSecondary")),
            }

    # ── DataStore_Inventory (average item level) ──────────────────────────────
    print("  DataStore_Inventory…")
    db = _load(WOW_SAVED_VARS / "DataStore_Inventory.lua")
    for key, info in ((db.get("global") or {}).get("Characters") or {}).items():
        if not isinstance(info, dict):
            continue
        p = key.split(".", 2)
        if len(p) < 3:
            continue
        ck = f"{p[1]}|{p[2]}"
        if ck in chars:
            ilvl = info.get("overallAIL") or info.get("averageItemLvl") or 0
            chars[ck]["avg_ilvl"] = round(float(ilvl), 1)

    # ── DataStore_Quests (active quests) ──────────────────────────────────────
    print("  DataStore_Quests…")
    db = _load(WOW_SAVED_VARS / "DataStore_Quests.lua")
    for key, info in ((db.get("global") or {}).get("Characters") or {}).items():
        if not isinstance(info, dict):
            continue
        p = key.split(".", 2)
        if len(p) < 3:
            continue
        ck = f"{p[1]}|{p[2]}"
        if ck not in chars:
            continue
        titles = info.get("QuestTitles") or {}
        tags   = info.get("QuestTags")   or {}
        active = []
        for idx, title in sorted(
            titles.items() if isinstance(titles, dict) else {},
            key=lambda x: x[0] if isinstance(x[0], int) else 0,
        ):
            tag = tags.get(idx) if isinstance(tags, dict) else None
            if tag != "COMPLETED" and title:
                active.append(str(title))
        chars[ck]["active_quests"] = active

    # ── Per-realm character folders (Dreamscythe\, Defias Pillager\, Doomhowl\, …) ─
    # The WTF structure has a subfolder per realm under the account directory.
    # Each realm folder contains per-character subfolders with their own SavedVariables.
    # We scan every realm subfolder dynamically so new realms are picked up automatically.
    print("  Scanning per-realm character folders…")
    for realm_dir in sorted(WOW_ACCOUNT_DIR.iterdir()):
        if not realm_dir.is_dir() or realm_dir.name == "SavedVariables":
            continue
        realm = realm_dir.name
        for cdir in sorted(realm_dir.iterdir()):
            if not cdir.is_dir():
                continue
            # Try Skillet first for class/race/faction detail
            who = _skillet_who(cdir / "SavedVariables" / "Skillet-Classic.lua")
            name = who.get("player", "") or cdir.name  # fall back to folder name
            ck = f"{realm}|{name}"
            if ck in chars:
                continue  # already captured by DataStore — richer data wins
            cls = who.get("classFile", "").upper()
            source = "Skillet" if who.get("player") else "FolderName"
            chars[ck] = {
                "name": name,
                "realm": realm,
                "level": 1,
                "class": cls,
                "class_display": CLASS_NAMES.get(cls, ""),
                "race": RACE_NAMES.get(who.get("raceFile", ""), who.get("raceFile", "")),
                "faction": who.get("faction", "Alliance"),
                "money": 0,
                "played": 0,
                "zone": "",
                "sub_zone": "",
                "guild": "",
                "guild_rank": "",
                "xp": 0,
                "xp_max": 1,
                "rest_xp": 0,
                "last_login": 0,
                "bind": "",
                "professions": {},
                "avg_ilvl": 0.0,
                "active_quests": [],
                "source": source,
            }

    # ── DataStore profileKeys fallback (catches chars with no Characters data) ─
    # A character can appear in profileKeys but have no entry in global.Characters
    # if DataStore registered them but never completed a sync (e.g. Zephyraan).
    print("  Checking for profileKeys-only characters…")
    keys_db = _load(WOW_SAVED_VARS / "DataStore_Characters.lua")
    for pk in (keys_db.get("profileKeys") or {}).keys():
        # profileKey format: "CharName - Realm"
        if " - " not in pk:
            continue
        name, realm = pk.rsplit(" - ", 1)
        ck = f"{realm}|{name}"
        if ck not in chars:
            chars[ck] = {
                "name": name,
                "realm": realm,
                "level": 1,
                "class": "",
                "class_display": "",
                "race": "",
                "faction": "Alliance",
                "money": 0,
                "played": 0,
                "zone": "",
                "sub_zone": "",
                "guild": "",
                "guild_rank": "",
                "xp": 0,
                "xp_max": 1,
                "rest_xp": 0,
                "last_login": 0,
                "bind": "",
                "professions": {},
                "avg_ilvl": 0.0,
                "active_quests": [],
                "source": "ProfileKey",
            }
            print(f"    Found orphaned profileKey: {name} ({realm})")

    return sorted(chars.values(), key=lambda c: (-c["level"], c["realm"], c["name"]))


# ─── Formatting helpers ────────────────────────────────────────────────────────
def fmt_money(copper: int) -> dict:
    return {"g": copper // 10000, "s": (copper % 10000) // 100, "c": copper % 100}


def fmt_played(secs: int) -> str:
    d = secs // 86400
    h = (secs % 86400) // 3600
    m = (secs % 3600) // 60
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def fmt_date(ts: int) -> str:
    if not ts:
        return "Never"
    try:
        return datetime.fromtimestamp(ts).strftime("%b %d, %Y")
    except Exception:
        return "?"


# ─── HTML template ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WoW Classic — Character Tracker</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0c10;--surface:#111420;--surface2:#191e2e;
  --border:#252b42;--gold:#c9a227;--gold-dim:#7a6015;
  --text:#d4cbb0;--dim:#6e6a58;
  --font:'Segoe UI',system-ui,sans-serif;
}
html{font-size:15px}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh}

/* header */
.site-header{
  background:linear-gradient(180deg,#060810 0%,#0e1220 100%);
  border-bottom:2px solid var(--gold-dim);
  padding:1.1rem 1.5rem;display:flex;align-items:center;gap:1rem
}
.site-header h1{
  font-size:1.45rem;font-weight:700;letter-spacing:.04em;
  color:var(--gold);text-shadow:0 0 18px #c9a22740
}
.site-header .sub{color:var(--dim);font-size:.8rem;margin-top:.2rem}
.logo{font-size:1.9rem;line-height:1}

/* controls */
.controls{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:.65rem 1.5rem;display:flex;gap:.65rem;flex-wrap:wrap;align-items:center
}
.controls label{color:var(--dim);font-size:.78rem;white-space:nowrap}
.controls select,.controls input[type=text]{
  background:var(--surface2);border:1px solid var(--border);
  color:var(--text);padding:.28rem .55rem;border-radius:4px;font-size:.82rem;cursor:pointer
}
.controls select:focus,.controls input:focus{outline:1px solid var(--gold-dim)}
.flex-sep{flex:1}

/* summary bar */
.summary{
  background:var(--surface2);border-bottom:1px solid var(--border);
  padding:.55rem 1.5rem;display:flex;gap:2.5rem;flex-wrap:wrap;align-items:center
}
.sp .v{font-size:1rem;font-weight:700;color:var(--gold)}
.sp .l{font-size:.68rem;color:var(--dim);text-transform:uppercase;letter-spacing:.07em}

/* grid */
.grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(275px,1fr));
  gap:.9rem;padding:1.1rem 1.5rem
}
.realm-hdr{
  grid-column:1/-1;font-size:.72rem;text-transform:uppercase;letter-spacing:.1em;
  color:var(--dim);padding:.5rem 0 .15rem;border-bottom:1px solid var(--border)
}
.realm-hdr b{color:var(--text);font-weight:600}

/* card */
.card{
  background:var(--surface);border:1px solid var(--border);border-radius:7px;
  overflow:hidden;transition:transform .14s,box-shadow .14s
}
.card:hover{transform:translateY(-2px);box-shadow:0 8px 28px #00000055}
.card-bar{height:4px}
.card-head{
  padding:.8rem 1rem .6rem;border-bottom:1px solid var(--border);
}
.card-lvl{float:right;font-size:1.25rem;font-weight:800;line-height:1.15}
.card-name{font-size:1.05rem;font-weight:700;letter-spacing:.025em}
.card-sub{font-size:.75rem;color:var(--dim);margin-top:.15rem}
.card-body{padding:.7rem 1rem;display:flex;flex-direction:column;gap:.5rem}

/* xp bar */
.xp-wrap{position:relative;height:13px;background:#141822;border-radius:3px;overflow:hidden}
.xp-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#2a4f1a,#5db832)}
.xp-rest{position:absolute;top:0;height:100%;background:rgba(90,50,200,.3);border-radius:0 3px 3px 0}
.xp-txt{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:.62rem;color:#ffffffaa;font-weight:600
}

/* info rows */
.ir{display:flex;gap:.45rem;align-items:flex-start;font-size:.8rem}
.ir .ico{width:1.1em;text-align:center;flex-shrink:0;margin-top:.05em}
.ir .v{flex:1;line-height:1.35}
.gg{color:#ffd700;font-weight:600}
.gs{color:#c8c8c8}
.gc{color:#b06830}

/* professions */
.profs-lbl{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin-bottom:.35rem}
.prof-row{margin-bottom:.32rem}
.prof-top{font-size:.76rem;display:flex;justify-content:space-between;align-items:baseline}
.prof-rk{font-size:.68rem;color:var(--dim)}
.prof-bar-bg{height:5px;background:#141822;border-radius:3px;overflow:hidden;margin-top:2px}
.pbar-pri{height:100%;border-radius:3px;background:linear-gradient(90deg,#8a4010,#c97830)}
.pbar-sec{height:100%;border-radius:3px;background:linear-gradient(90deg,#10405a,#207090)}

/* quests */
.quests details{margin-top:0}
.quests summary{font-size:.77rem;color:var(--dim);cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:.3rem}
.quests summary::before{content:'▸';font-size:.6rem;transition:transform .15s}
details[open] summary::before{content:'▾'}
.quest-list{margin:.3rem 0 0 1.1rem;list-style:disc}
.quest-list li{font-size:.73rem;padding:.08rem 0}

/* badges */
.badge{
  display:inline-block;font-size:.63rem;padding:.12rem .38rem;border-radius:3px;
  text-transform:uppercase;letter-spacing:.05em
}
.badge-limited{color:#a07020;border:1px solid #5a3b0c;background:#1e1608}
.badge-ds{color:#3a7a4a;border:1px solid #1a4025;background:#0e1a12}

.no-res{grid-column:1/-1;text-align:center;padding:3rem;color:var(--dim);font-size:.95rem}
</style>
</head>
<body>

<header class="site-header">
  <div class="logo">⚔️</div>
  <div>
    <h1>WoW Classic — Character Tracker</h1>
    <div class="sub" id="gen-time"></div>
  </div>
</header>

<div class="controls">
  <label>Realm</label>
  <select id="fRealm" onchange="render()">
    <option value="">All Realms</option>
  </select>
  <label>Class</label>
  <select id="fClass" onchange="render()">
    <option value="">All Classes</option>
  </select>
  <label>Sort</label>
  <select id="sSort" onchange="render()">
    <option value="level">Level ↓</option>
    <option value="name">Name A→Z</option>
    <option value="realm">Realm</option>
    <option value="played">Played Time</option>
    <option value="money">Wealth</option>
    <option value="last_login">Last Login</option>
  </select>
  <div class="flex-sep"></div>
  <label>🔍</label>
  <input type="text" id="sSearch" placeholder="Search name…" oninput="render()" style="width:140px">
</div>

<div class="summary" id="summary"></div>
<div class="grid"   id="grid"></div>

<script>
const CHARS = __CHARS__;
const CC    = __CLASS_COLORS__;
const MAX_LEVEL = __MAX_LEVEL__;

/* init filters */
(function initFilters(){
  document.getElementById('gen-time').textContent = 'Generated __GEN_TIME__';
  const realms  = [...new Set(CHARS.map(c=>c.realm))].sort();
  const classes = [...new Set(CHARS.map(c=>c.class).filter(Boolean))].sort();
  const rs = document.getElementById('fRealm');
  realms.forEach(r=>{const o=document.createElement('option');o.value=r;o.textContent=r;rs.appendChild(o)});
  const cs = document.getElementById('fClass');
  classes.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c.charAt(0)+c.slice(1).toLowerCase();cs.appendChild(o)});
  render();
})();

function render(){
  const rf = document.getElementById('fRealm').value;
  const cf = document.getElementById('fClass').value;
  const sf = document.getElementById('sSort').value;
  const q  = document.getElementById('sSearch').value.toLowerCase();

  let list = CHARS.filter(c=>{
    if(rf && c.realm!==rf) return false;
    if(cf && c.class!==cf) return false;
    if(q  && !c.name.toLowerCase().includes(q)) return false;
    return true;
  });

  list.sort((a,b)=>{
    switch(sf){
      case 'level':      return b.level-a.level || a.name.localeCompare(b.name);
      case 'name':       return a.name.localeCompare(b.name);
      case 'realm':      return a.realm.localeCompare(b.realm)||a.name.localeCompare(b.name);
      case 'played':     return b.played-a.played;
      case 'money':      return b.money-a.money;
      case 'last_login': return b.last_login-a.last_login;
    }
    return 0;
  });

  /* summary */
  const totalCopper = CHARS.reduce((s,c)=>s+c.money,0);
  const totalGold   = Math.floor(totalCopper/10000);
  const maxLvl      = Math.max(...CHARS.map(c=>c.level));
  const most        = CHARS.reduce((a,b)=>a.played>b.played?a:b, CHARS[0]);
  document.getElementById('summary').innerHTML=`
    <div class="sp"><span class="v">${CHARS.length}</span><span class="l">Characters</span></div>
    <div class="sp"><span class="v">${totalGold.toLocaleString()}<span style="font-size:.7em;color:#8a7020">g</span></span><span class="l">Total Gold</span></div>
    <div class="sp"><span class="v">${maxLvl}</span><span class="l">Highest Level</span></div>
    <div class="sp"><span class="v">${most?.name||''}</span><span class="l">Most Played</span></div>
    <div class="sp"><span class="v">${list.length}</span><span class="l">Showing</span></div>
  `;

  const grid = document.getElementById('grid');
  grid.innerHTML='';

  if(!list.length){
    grid.innerHTML='<div class="no-res">No characters match your filters.</div>';
    return;
  }

  let lastRealm=null;
  list.forEach(c=>{
    if(!rf && c.realm!==lastRealm){
      lastRealm=c.realm;
      const cnt=list.filter(x=>x.realm===c.realm).length;
      const h=document.createElement('div');
      h.className='realm-hdr';
      h.innerHTML=`${c.realm} &nbsp;<b>${cnt} character${cnt!==1?'s':''}</b>`;
      grid.appendChild(h);
    }
    grid.appendChild(buildCard(c));
  });
}

function clr(cls){ return CC[cls]||'#aaaaaa'; }

function moneyHtml(m){
  let s='';
  if(m.g) s+=`<span class="gg">${m.g.toLocaleString()}g</span> `;
  if(m.s||m.g) s+=`<span class="gs">${m.s}s</span> `;
  s+=`<span class="gc">${m.c}c</span>`;
  return s.trim()||'<span class="gc">0c</span>';
}

function buildCard(c){
  const cc   = clr(c.class);
  const atMax = c.level >= MAX_LEVEL;
  const xpPct = atMax ? 100 : Math.round(c.xp/c.xp_max*100);
  const rPct  = atMax||!c.rest_xp ? 0 : Math.min(100-xpPct, Math.round(c.rest_xp/c.xp_max*100));

  /* professions */
  const profs = Object.entries(c.professions||{});
  const pri   = profs.filter(([,p])=>p.primary);
  const sec   = profs.filter(([,p])=>p.secondary);
  let profHtml='';
  if(profs.length){
    profHtml='<div><div class="profs-lbl">Professions</div>';
    [...pri,...sec].forEach(([name,p])=>{
      const pct=p.max>0?Math.round(p.rank/p.max*100):0;
      const bcls=p.primary?'pbar-pri':'pbar-sec';
      profHtml+=`<div class="prof-row">
        <div class="prof-top">${name}<span class="prof-rk">${p.rank}/${p.max}</span></div>
        <div class="prof-bar-bg"><div class="${bcls}" style="width:${pct}%"></div></div>
      </div>`;
    });
    profHtml+='</div>';
  }

  /* active quests */
  let questHtml='';
  if(c.active_quests&&c.active_quests.length){
    const ql=c.active_quests.map(q=>`<li>${q}</li>`).join('');
    questHtml=`<div class="quests"><details>
      <summary>📋 ${c.active_quests.length} active quest${c.active_quests.length>1?'s':''}</summary>
      <ul class="quest-list">${ql}</ul>
    </details></div>`;
  }

  const card=document.createElement('div');
  card.className='card';
  card.innerHTML=`
    <div class="card-bar" style="background:${cc}"></div>
    <div class="card-head">
      <span class="card-lvl" style="color:${cc}">${c.level}</span>
      <div class="card-name" style="color:${cc}">${c.name}</div>
      <div class="card-sub">${c.race||''} ${c.class_display||''} &bull; ${c.realm}</div>
    </div>
    <div class="card-body">
      ${!atMax?`<div class="xp-wrap">
        <div class="xp-fill" style="width:${xpPct}%"></div>
        ${rPct?`<div class="xp-rest" style="left:${xpPct}%;width:${rPct}%"></div>`:''}
        <div class="xp-txt">${xpPct}% XP${rPct?` +${rPct}% rested`:''}</div>
      </div>`:''}
      ${c.guild?`<div class="ir"><span class="ico">🏰</span><span class="v">${c.guild}${c.guild_rank?` <span style="color:var(--dim);font-size:.72em">(${c.guild_rank})</span>`:''}</span></div>`:''}
      ${c.zone?`<div class="ir"><span class="ico">📍</span><span class="v">${c.zone}${c.sub_zone?` — ${c.sub_zone}`:''}</span></div>`:''}
      ${c.money?`<div class="ir"><span class="ico">💰</span><span class="v">${moneyHtml(c.money_obj)}</span></div>`:''}
      ${c.played?`<div class="ir"><span class="ico">⏱</span><span class="v">${c.played_fmt} played</span></div>`:''}
      ${c.avg_ilvl>=1?`<div class="ir"><span class="ico">🛡</span><span class="v">Avg Item Level ${c.avg_ilvl}</span></div>`:''}
      ${c.bind?`<div class="ir"><span class="ico">🔒</span><span class="v">Bound: ${c.bind}</span></div>`:''}
      ${c.last_login?`<div class="ir"><span class="ico">🕐</span><span class="v">Last seen ${c.last_login_fmt}</span></div>`:''}
      ${profHtml}
      ${questHtml}
      <div class="ir">
        <span class="ico"></span>
        <span class="badge ${c.source==='DataStore'?'badge-ds':'badge-limited'}">${
          c.source==='DataStore'?'Full data':
          c.source==='Skillet'?'Class known':
          c.source==='FolderName'?'Name only':
          'No addon data'
        }</span>
      </div>
    </div>
  `;
  return card;
}
</script>
</body>
</html>
"""


# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Gathering WoW character data…")
    chars = gather()
    print(f"  -> {len(chars)} characters found")

    for c in chars:
        c["money_obj"]      = fmt_money(c["money"])
        c["played_fmt"]     = fmt_played(c["played"])
        c["last_login_fmt"] = fmt_date(c["last_login"])

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = HTML
    html = html.replace("__CHARS__",        json.dumps(chars, ensure_ascii=False))
    html = html.replace("__CLASS_COLORS__", json.dumps(CLASS_COLORS))
    html = html.replace("__MAX_LEVEL__",    str(MAX_LEVEL))
    html = html.replace("__GEN_TIME__",     gen_time)

    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nDone! Dashboard written to: {OUTPUT_HTML}")
    print("Open wow_tracker.html in any browser.")
    print("Re-run this script after logging in with new characters.")


if __name__ == "__main__":
    main()
