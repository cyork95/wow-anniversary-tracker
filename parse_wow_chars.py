#!/usr/bin/env python3
"""
WoW Classic Character Tracker
Parses addon SavedVariables Lua files and generates a self-contained HTML dashboard.
Run any time your WoW character data changes:  python parse_wow_chars.py
"""

import re, json
from pathlib import Path
from datetime import datetime

# --- Config -------------------------------------------------------------------
WOW_SAVED_VARS  = Path(r"C:\Program Files (x86)\World of Warcraft\_anniversary_\WTF\Account\383258958#1\SavedVariables")
WOW_ACCOUNT_DIR = WOW_SAVED_VARS.parent
WOW_ADDONS_DIR  = Path(r"C:\Program Files (x86)\World of Warcraft\_anniversary_\Interface\AddOns")
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

QUALITY_COLORS = {
    "9d9d9d": "poor",
    "ffffff": "common",
    "1eff00": "uncommon",
    "0070dd": "rare",
    "a335ee": "epic",
    "ff8000": "legendary",
}


# --- Lua parser ---------------------------------------------------------------
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
        # unknown token -- skip to next delimiter
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

    @classmethod
    def parse_table_at(cls, text: str, pos: int) -> dict:
        """Parse a Lua table starting at pos (must point at '{')."""
        inst = cls.__new__(cls)
        inst.s, inst.p, inst.n = text, pos, len(text)
        return inst._tbl()


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return LuaParser(path.read_text(encoding="utf-8", errors="replace")).parse() or {}
    except Exception as e:
        print(f"  WARN {path.name}: {e}")
        return {}


def _skillet_who(path: Path) -> dict:
    """Extract SkilletWho via regex -- faster than full parse for this small block."""
    if not path.exists():
        return {}
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"SkilletWho\s*=\s*\{([^}]+)\}", txt, re.DOTALL)
    if not m:
        return {}
    return {k: v for k, v in re.findall(r'\["(\w+)"\]\s*=\s*"([^"]*)"', m.group(1))}


def _parse_all_vars(text: str) -> dict:
    """Parse every top-level  VARNAME = { ... }  assignment in a Lua file."""
    result = {}
    for m in re.finditer(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\{)', text, re.MULTILINE):
        varname = m.group(1)
        try:
            result[varname] = LuaParser.parse_table_at(text, m.start(2))
        except Exception:
            pass
    return result


# AutoBiographer event type/subtype -> human label ----------------------------
_AB_TYPES = {
    (2,  6):  "levelup",
    (12, 8):  "quest",
    (7,  0):  "boss",
    (4,  3):  "guild_join",
    (4,  4):  "guild_leave",
    (4,  5):  "guild_rank",
    (8,  12): "zone",
    (13, 9):  "skill",
    (18, 13): "rep",
    (0,  14): "bg_enter",
    (0,  15): "bg_end",
    (14, 10): "spell",
}


def _parse_autobiographer(path: Path) -> dict | None:
    """Extract timeline events, zones, and character info from AutoBiographer.lua."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    vars_ = _parse_all_vars(text)
    result: dict = {}

    # -- INFO_CHAR -------------------------------------------------------------
    info = vars_.get("AUTOBIOGRAPHER_INFO_CHAR") or {}
    if isinstance(info, dict):
        result["zone"]       = info.get("CurrentZone", "")
        result["sub_zone"]   = info.get("CurrentSubZone", "")
        result["guild"]      = info.get("GuildName", "")
        result["guild_rank"] = info.get("GuildRankName", "")
        result["played"]     = int(info.get("LastTotalTimePlayed", 0) or 0)

    # -- CATALOGS_CHAR -- zones explored, boss kills, pvp kills ----------------
    catalogs = vars_.get("AUTOBIOGRAPHER_CATALOGS_CHAR") or {}
    if isinstance(catalogs, dict):
        # Zones explored
        sz_cat = catalogs.get("SubZoneCatalog") or {}
        if isinstance(sz_cat, dict):
            zones_map: dict[str, list[str]] = {}
            for sz_name, sz_data in sz_cat.items():
                if isinstance(sz_data, dict) and sz_data.get("HasEntered") and isinstance(sz_name, str):
                    zone = str(sz_data.get("ZoneName", "Unknown"))
                    zones_map.setdefault(zone, []).append(sz_name)
            result["zones_visited"] = {z: sorted(subzones) for z, subzones in sorted(zones_map.items())}

        # Boss kills (BossCatalog — all entries are killed bosses)
        boss_cat = catalogs.get("BossCatalog") or {}
        if isinstance(boss_cat, dict):
            boss_kills = []
            for _, bdata in boss_cat.items():
                if isinstance(bdata, dict):
                    name = str(bdata.get("Name", "")).strip()
                    if name and bdata.get("Killed"):
                        boss_kills.append(name)
            if boss_kills:
                result["boss_kills"] = sorted(boss_kills)

        # PvP kills (UnitCatalog — UType=2 player kills with Killed=true)
        unit_cat = catalogs.get("UnitCatalog") or {}
        if isinstance(unit_cat, dict):
            pvp_kills = []
            for _, udata in unit_cat.items():
                if not isinstance(udata, dict):
                    continue
                if not udata.get("Killed"):
                    continue
                utype = udata.get("UType")
                name  = str(udata.get("Name", "")).strip()
                if not name:
                    continue
                if utype == 2:  # player
                    pvp_kills.append({
                        "name":  name,
                        "race":  str(udata.get("Race",  "")),
                        "class": str(udata.get("Class", "")),
                    })
                # utype==1 are pets — skip
            if pvp_kills:
                pvp_kills.sort(key=lambda x: x["name"].lower())
                result["pvp_kills"] = pvp_kills

    # -- EVENTS_CHAR -- timeline -----------------------------------------------
    events_tbl = vars_.get("AUTOBIOGRAPHER_EVENTS_CHAR") or {}
    if isinstance(events_tbl, dict):
        timeline = []
        last_zone = None
        for _, ev in sorted(events_tbl.items(), key=lambda x: x[0] if isinstance(x[0], int) else 0):
            if not isinstance(ev, dict):
                continue
            t  = ev.get("Type")
            st = ev.get("SubType")
            ts = int(ev.get("Timestamp", 0) or 0)
            ek = _AB_TYPES.get((t, st))
            if not ek:
                continue

            # Skip consecutive duplicate zone entries
            if ek == "zone":
                zone_name = ev.get("ZoneName", "")
                if zone_name == last_zone:
                    continue
                last_zone = zone_name
            else:
                last_zone = None

            entry: dict = {"k": ek, "ts": ts}
            if ek == "levelup":
                entry["lvl"] = int(ev.get("LevelNum", 0) or 0)
            elif ek == "quest":
                entry["title"] = str(ev.get("QuestTitle", ""))
                entry["xp"]    = int(ev.get("XpGained", 0) or 0)
                entry["gold"]  = int(ev.get("MoneyGained", 0) or 0)
            elif ek == "boss":
                entry["boss"] = str(ev.get("BossName", ""))
            elif ek in ("guild_join", "guild_leave"):
                entry["guild"] = str(ev.get("GuildName", ""))
            elif ek == "guild_rank":
                entry["rank"] = str(ev.get("GuildRankName", ""))
            elif ek == "zone":
                entry["zone"] = str(ev.get("ZoneName", ""))
            elif ek == "skill":
                entry["skill"] = str(ev.get("SkillName", ""))
                entry["lvl"]   = int(ev.get("SkillLevel", 0) or 0)
            elif ek == "rep":
                entry["faction"]  = str(ev.get("Faction", ""))
                entry["standing"] = str(ev.get("ReputationLevel", ""))
            elif ek == "spell":
                entry["spell_id"] = int(ev.get("SpellId", 0) or 0)

            timeline.append(entry)

        result["events"]       = timeline
        result["event_count"]  = len(events_tbl)

    return result or None


# --- Achievement parsing ------------------------------------------------------
def _load_achievement_names(char_class: str = "", char_faction: str = "Alliance") -> dict:
    """
    Build {achievement_id: display_name} by simulating the AnniversaryAchievements
    addon's exact registration order.  Achievements without an explicit 6th-argument
    ID get sequential auto-IDs starting at 1; those with an explicit ID are stored
    at that index directly.
    """
    en_lua = WOW_ADDONS_DIR / "AnniversaryAchievements" / "localization" / "en.lua"
    en: dict[str, str] = {}
    if en_lua.exists():
        try:
            txt = en_lua.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(\w+)\s*=\s*'((?:[^'\\]|\\.)*)'", txt):
                en[m.group(1)] = m.group(2).replace("\\'", "'")
        except Exception:
            pass

    def L(key: str, *args) -> str:
        s = en.get(key, key)
        if args:
            try:
                return s % args
            except Exception:
                return s
        return s

    names: dict[int, str] = {}
    _auto = [0]

    def reg(name: str, explicit: int | None = None) -> int:
        if explicit is not None:
            names[explicit] = name
            return explicit
        _auto[0] += 1
        names[_auto[0]] = name
        return _auto[0]

    cls  = char_class.upper()
    is_h = char_faction == "Horde"
    fl   = "H" if is_h else "A"  # faction letter for PvP ranks

    # ── GENERAL ──────────────────────────────────────────────────────────────
    for i in range(1, 8):                           # Level 10 … 70
        reg(L("AN_LVL", i * 10))
    reg(L("AN_BANK"))
    for i in range(1, 8):                           # mob kills ×7
        reg(L(f"AN_MOB_KILLS_{i}"))
    reg(L("AN_UNARMED_SKILL"))
    reg(L("AN_UNCOMMON_GEAR"))
    reg(L("AN_RARE_GEAR"))
    reg(L("AN_EPIC_GEAR"))
    for sp in (75, 150, 225, 300):
        reg(L(f"AN_RIDING_{sp}"))
    for tier in ("T1", "T2", "T3"):                 # class-specific tier sets
        key = f"AN_{cls}_{tier}"
        reg(en.get(key, f"{cls or 'Class'} Tier {tier[1]}"))
    reg(L("AN_DOLCE"))

    # ── QUESTS ───────────────────────────────────────────────────────────────
    for c in (50, 100, 250, 500, 750, 1000, 1500, 2000):
        reg(L("AN_QUESTS", c))
    # daily quests: explicit IDs 567-574
    for i, c in enumerate((5, 50, 200, 500, 1000, 2500, 5000, 10000)):
        reg(L("AN_DAILY_QUESTS", c), 567 + i)
    # quest gold: auto-IDs
    for c in (5, 10, 25, 50, 100, 250, 500):
        reg(L(f"AN_QUEST_GOLD{c}"))
    reg(L("AN_SKELETON_KEY"))

    # Wisdom Keeper Kalimdor then 12 zone quests
    reg(L("AN_WISDOM_KEEPER_KALIMDOR"))
    for z in ("DUROTAR", "BARRENS", "STONETALON", "DESOLACE", "THOUSAND_NEEDLES",
              "DUSTWALLOW", "FELWOOD", "TANARIS", "UNGORO", "AZSHARA",
              "WINTERSPRING", "SILITHUS"):
        reg(L("AN_QUESTS_ZONE", en.get(f"{z}_2", z.replace("_", " ").title())))

    # Wisdom Keeper Eastern Kingdoms then 8 zone quests
    reg(L("AN_WISDOM_KEEPER_EASTERN_KINGDOMS"))
    for z in ("ARATHI", "STRANGLETHORN_VALLEY", "BADLANDS", "SEARING_GORGE",
              "BLASTED_LANDS", "WESTERN_PLAGUELANDS", "EASTERN_PLAGUELANDS", "BLACK_ROCK"):
        reg(L("AN_QUESTS_ZONE", en.get(f"{z}_2", z.replace("_", " ").title())))

    reg(L("AN_WISDOM_KEEPER_AZEROTH"))
    reg(L("AN_NESINGWARY"))

    # TBC outland quest zones (6 faction pairs + netherstorm + shadowmoon)
    for z in ("HELLFIRE_PENINSULA", "HELLFIRE_PENINSULA",   # Horde / Alliance
              "ZANGARMASH",         "ZANGARMASH",
              "TERROKAR",           "TERROKAR",
              "NAGRAND",            "NAGRAND",
              "BLADES_EDGE_MTNS",   "BLADES_EDGE_MTNS",
              "NETHERSTORM",        "SHADOWMOON"):
        name_key = f"AN_QUESTS_{z}"
        reg(en.get(name_key, z.replace("_", " ").title()))

    reg(L("AN_WISDOM_KEEPER_OUTLAND"))  # Horde
    reg(L("AN_WISDOM_KEEPER_OUTLAND"))  # Alliance
    reg(L("AN_WISDOM_KEEPER"))          # Horde
    reg(L("AN_WISDOM_KEEPER"))          # Alliance
    reg(L("AN_HEMET_QUESTS_NAGRAND"))
    for att in ("AN_ATTUNE_SHATTERED_HALLS", "AN_ATTUNE_ARCATRAZ",
                "AN_ATTUNE_KARAZHAN", "AN_ATTUNE_NIGHT_BANE",
                "AN_ATTUNE_SSC", "AN_ATTUNE_EYE",
                "AN_ATTUNE_HYJAL", "AN_ATTUNE_BLACK_TEMPLE"):
        reg(L(att))

    # ── EXPLORATION ──────────────────────────────────────────────────────────
    reg(L("AN_EXPLORE_AZEROTH"))
    reg(L("AN_EXPLORE_KALIMDOR"))
    for a in ("Ashenvale", "Azshara", "Darkshore", "Desolace", "Durotar",
              "Dustwallow Marsh", "Felwood", "Feralas", "Mulgore", "Silithus",
              "Stonetalon Mountains", "Tanaris", "Teldrassil", "The Barrens",
              "Thousand Needles", "Un'Goro Crater", "Winterspring",
              "Azuremyst Isle", "Bloodmyst Isle"):
        reg(L("AN_EXPLORE", a))
    reg(L("AN_EXPLORE_EASTERN_KINGDOMS"))
    for a in ("Alterac Mountains", "Arathi Highlands", "Badlands", "Blasted Lands",
              "Burning Steppes", "Deadwind Pass", "Dun Morogh", "Duskwood",
              "Eastern Plaguelands", "Elwynn Forest", "Hillsbrad Foothills",
              "Loch Modan", "Redridge Mountains", "Searing Gorge", "Silverpine Forest",
              "Stranglethorn Vale", "Swamp of Sorrows", "The Hinterlands",
              "Tirisfal Glades", "Western Plaguelands", "Westfall", "Wetlands",
              "Eversong Woods", "Ghostlands", "Isle of Quel'Danas"):
        reg(L("AN_EXPLORE", a))
    reg(L("AN_LOVE"))
    reg(L("AN_EXPLORE_OUTLAND"))
    for a in ("Hellfire Peninsula", "Zangarmarsh", "Terokkar Forest", "Nagrand",
              "Blade's Edge Mountains", "Netherstorm", "Shadowmoon Valley"):
        reg(L("AN_EXPLORE", a))
    reg(L("AN_MIDDLE_RARE"))
    reg(L("AN_BLOODY_RARE"))

    # ── PVP ──────────────────────────────────────────────────────────────────
    for i in range(1, 15):          # 14 PvP rank feats (featsOfStrength, auto-IDs)
        reg(L(f"AN_PVP_RANK_{fl}{i}"))
    reg(L("AN_PVP_FIRST_KILL"))
    for c in (10, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000):
        reg(L("AN_PVP_KILLS", c))
    # BG faction reps
    reg(L("AN_DEFILERS")); reg(L("AN_FROSTWOLF_CLAN")); reg(L("AN_WARSONG_OUTRIDERS"))
    reg(L("AN_HORDE_PVP_FRACTIONS"))
    reg(L("AN_LEAGUE_OF_ARATHOR")); reg(L("AN_STORMSPIKE_GUARD")); reg(L("AN_SILVERWING_SENTINELS"))
    reg(L("AN_ALLIANCE_PVP_FRACTIONS"))
    # Leader slayers
    reg(L("AN_BOLVAR_SLAYER")); reg(L("AN_MAGNI_SLAYER")); reg(L("AN_TYRANDE_SLAYER")); reg(L("AN_VELEN_SLAYER"))
    reg(L("AN_ALLIANCE_KINGS_SLAYER"))
    reg(L("AN_THRALL_SLAYER")); reg(L("AN_SYLVANAS_SLAYER")); reg(L("AN_CAIRNE_SLAYER")); reg(L("AN_LORTHEMAR_SLAYER"))
    reg(L("AN_HORDE_KINGS_SLAYER"))
    reg(L("AN_RACES_KILLER")); reg(L("AN_RACES_KILLER")); reg(L("AN_CLASSES_KILLER"))

    # BG wins: 5 amounts × 4 BGs
    for bg in ("ALTERAC", "WARSONG", "ARATHI", "EYE"):
        for n in (1, 5, 10, 25, 50):
            key = f"AN_{bg}_WIN" if n == 1 else f"AN_{bg}_WINS"
            reg(en.get(key, f"{bg.title()} Victory"))

    # Alterac stat achievements
    for counts, typ in (
        ((5, 10, 25, 40),    "KILLING_BLOWS"),
        ((1, 2, 3, 4),       "GRAVEYARD_ASSAULT"),
        ((1, 2, 3, 4),       "GRAVEYARD_DEFEND"),
        ((1, 2, 3, 4),       "TOWER_ASSAULT"),
        ((1, 2, 3, 4),       "TOWER_DEFEND"),
        ((1, 2, 3, 4),       "MINE_CAPTURE"),
    ):
        for n in counts:
            base = f"ALTERAC_{typ}"
            key  = base if n == 1 and f"AN_{base}" in en else f"{base}S"
            if n == 1 and f"AN_{base}" in en:
                reg(en[f"AN_{base}"])
            else:
                reg(en.get(f"AN_{key}", f"Alterac {typ.replace('_',' ').title()}"))
    reg(L("AN_ALTERAC_FAST_WIN"))
    # Warsong
    for n in (10, 25, 50, 75): reg(L("AN_WARSONG_KILLS"))
    for n in (1, 2, 3): reg(en.get("AN_WARSONG_FLAG_CAPTURE" if n == 1 else "AN_WARSONG_FLAG_CAPTURES", "Flag Capture"))
    for n in (1, 2, 3): reg(en.get("AN_WARSONG_FLAG_RETURN"  if n == 1 else "AN_WARSONG_FLAG_RETURNS",  "Flag Return"))
    reg(L("AN_WARSONG_FAST_WIN"))
    # Arathi
    for n in (1, 2, 3, 4): reg(en.get("AN_ARATHI_BASE_ASSAULT" if n == 1 else "AN_ARATHI_BASE_ASSAULTS", "Base Assault"))
    for n in (1, 2, 3, 4): reg(en.get("AN_ARATHI_BASE_DEFEND"  if n == 1 else "AN_ARATHI_BASE_DEFENDS",  "Base Defend"))
    reg(L("AN_ARATHI_CATS"))
    reg(L("AN_ARATHI_FAST_WIN"))
    # Career totals (add() function using inner counter)
    reg(L("AN_ALTERAC_TOWER_DEFEND_TOTAL"))
    reg(L("AN_ALTERAC_GRAVEYARD_ASSAULT_TOTAL"))
    reg(L("AN_WARSONG_FLAG_CAPTURE_TOTAL"))
    reg(L("AN_WARSONG_FLAG_RETURN_TOTAL"))
    reg(L("AN_ARATHI_BASE_ASSAULT_TOTAL"))
    reg(L("AN_ARATHI_BASE_DEFEND_TOTAL"))
    # Explicit IDs
    reg(L("AN_ARATHI_CLOSE"),   578)
    reg(L("AN_ARATHI_PERFECT"), 579)
    # Mounts
    reg(L("AN_ALTERAC_MOUNT_HORDE"))    # Frostwolf Howler
    reg(L("AN_ALTERAC_MOUNT_ALLIANCE")) # Stormpike Battle Charger
    # Eye of the Storm
    for n in (1, 2, 3): reg(en.get("AN_EYE_CAPTURE" if n == 1 else "AN_EYE_CAPTURES", "Storm Capper"))
    reg(L("AN_EYE_GLORY")); reg(L("AN_EYE_BERSERK")); reg(L("AN_EYE_IDEAL_VICTORY")); reg(L("AN_EYE_FAST_WIN"))
    # Explicit
    reg(L("AN_ALTERAC_AUTOGRAPH"), 577)
    # Boss / meta
    reg(L("AN_ALTERAC_BOSS")); reg(L("AN_WARSONG_BOSS")); reg(L("AN_ARATHI_BOSS")); reg(L("AN_EYE_BOSS"))
    reg(L("AN_BATTLEMASTER"))
    for n in (10, 25, 50): reg(L("AN_PARTICIPATE_IN_BGS"))
    for _ in (100, 250, 500, 750, 1000): reg(L("AN_BGS_KILLING_BLOWS"))
    for _ in (100, 250, 500, 750, 1000): reg(L("AN_BGS_KILLS"))
    reg(L("AN_GURUBASHI_1")); reg(L("AN_GURUBASHI_2"))
    reg(L("AN_DUEL"))
    reg(L("AN_DUELS_10")); reg(L("AN_DUELS_25")); reg(L("AN_DUELS_100"))
    # Arena: all explicit IDs (580-604)
    reg(L("AN_ARENA_GLADIATOR"), 580); reg(L("AN_ARENA_DUELIST"),    581)
    reg(L("AN_ARENA_RIVAL"),     582); reg(L("AN_ARENA_CHALLENGER"), 583)
    reg(L("AN_ARENA_FIRST_WIN"), 584)
    for i, _ in enumerate((100, 200, 300), 1):
        reg(L(f"AN_ARENA_WIN{i}"), 584 + i)
    reg(L("AN_ARENA_MAPS"),      588); reg(L("AN_ARENA_STREAK"),     589)
    _aid = 590
    for bracket in (2, 3, 5):
        for rating in (1550, 1750, 2000, 2200):
            reg(L(f"AN_ARENA_{bracket}_{rating}"), _aid); _aid += 1
    reg(L("AN_ARENA_HOTSTREAK"), 602); reg(L("AN_ARENA_LASTMAN"),    603)
    reg(L("AN_ARENA_MASTER"),    604)

    # ── PVE ──────────────────────────────────────────────────────────────────
    # Classic dungeons
    for key in ("AN_RAGEFIRE_CHASM", "AN_WAILING_CAVERNS", "AN_DEAD_MINES",
                "AN_SHADOWFANG_KEEP", "AN_BLACKFATHOM_DEEPS", "AN_JAIL",
                "AN_GNOMREGAN", "AN_RAZORFEN_KRAUL", "AN_SCARLET_MONASTERY",
                "AN_RAZORFEN_DOWNS", "AN_ULDAMAN", "AN_ZULFARRAK",
                "AN_MARAUDON", "AN_SUNKEN_TEMPLE"):
        reg(L(key))
    reg(L("AN_NEW_EMPEROR")); reg(L("AN_BLACKROCK_DEPTHS")); reg(L("AN_BLACKROCK_PARTY"))
    reg(L("AN_ARMOR_SWORD")); reg(L("AN_BLACKROCK_DEPTHS_FULL"))
    reg(L("AN_BLACKROCK_SPIRE_BOTTOM")); reg(L("AN_BLACKROCK_SPIRE_UPPER")); reg(L("AN_BLACKROCK_SPIRE"))
    reg(L("AN_DIRE_MAUL")); reg(L("AN_STRATHOLME")); reg(L("AN_SCHOLOMANCE"))
    reg(L("AN_YOUNG_DEFENDER")); reg(L("AN_DEFENDER"))
    # Classic raids
    for key in ("AN_ONYXIA", "AN_AQ20", "AN_ZULGURUB", "AN_RAGNAROS",
                "AN_BLACK_WING_LAIR", "AN_AQ40",
                "AN_NAXXRAMAS_SPIDERS", "AN_NAXXRAMAS_PLAGUE",
                "AN_NAXXRAMAS_MILITARY", "AN_NAXXRAMAS_CONSTRUCT", "AN_NAXXRAMAS_LAIR"):
        reg(L(key))
    reg(L("AN_NAXXRAMAS_SAPPHIRON"), 540)
    reg(L("AN_NAXXRAMAS"))
    reg(L("AN_YOUNG_HERO")); reg(L("AN_BLACKROCK_MASTER")); reg(L("AN_HERO")); reg(L("AN_GREAT_HERO"))
    # World bosses
    reg(L("AN_WB_AZUREGOS")); reg(L("AN_WB_KAZZAK"))
    reg(L("AN_WB_YSONDRE")); reg(L("AN_WB_LETHON")); reg(L("AN_WB_EMERISS")); reg(L("AN_WB_TAERAR"))
    reg(L("AN_WB_EMERALD_DRAGONS"))
    # Naxx challenges
    reg(L("AN_LEEROY")); reg(L("AN_BWL_DUO"))
    reg(L("AN_ANUBREKHAN_WITHOUT_MOBS")); reg(L("AN_FAERLINA_WITHOUT_MOBS"))
    reg(L("AN_ARACHNOPHOBIA")); reg(L("AN_FOUR_TOGETHER")); reg(L("AN_SAPPHIRONE_WITH_ALL_ALIVE"))
    reg(L("AN_HEIGAN_DANCE"),            562)
    reg(L("AN_PATCHWERK"),               563)
    reg(L("AN_KELTHUZAD_ABOMINATIONS"),  565)
    # TBC dungeons: 16 zones × 2 (normal then heroic), builders registered after
    _tbc = ("hellfire_ramparts", "blood_furnace", "slave_pens", "underbog",
            "mana_tombs", "auchenai_crypts", "old_hillsbrad", "sethekk_halls",
            "steamvault", "shadow_labyrinth", "shattered_halls", "black_morass",
            "botanica", "mechanar", "arcatraz", "magisters_terrace")
    for z in _tbc:
        base = L(f"AN_{z.upper()}")
        reg(base)
        reg(L("HEROIC_NAME_PATTERN", base))
    reg(L("AN_TBC_DUNGEONS")); reg(L("AN_TBC_DUNGEONS_HERO"))
    # TBC world bosses / raids
    reg(L("AN_RAVEN_LORD"))
    reg(L("AN_WB_KAZZAK_OUTLAND")); reg(L("AN_WB_DOOMWALKER"))
    reg(L("AN_KARAZHAN")); reg(L("AN_GRUUL")); reg(L("AN_MAGTHERIDON"))
    reg(L("AN_TBC_PHASE_1"))
    reg(L("AN_SSC")); reg(L("AN_TK")); reg(L("AN_TBC_PHASE_2"))
    reg(L("AN_HYJAL"))
    reg(L("AN_BT_ENTRANCE")); reg(L("AN_BT_SECOND_WING")); reg(L("AN_BT_LAST_WING"))
    reg(L("AN_BLACK_TEMPLE")); reg(L("AN_TBC_PHASE_3"))
    reg(L("AN_ZULAMAN")); reg(L("AN_TBC_PHASE_4"))
    reg(L("AN_SUNWELL")); reg(L("AN_TBC_PHASE_5"))
    reg(L("AN_OUTLAND_HERO"),       631)
    reg(L("AN_OUTLAND_GREAT_HERO"), 632)

    # ── PROFESSIONS ──────────────────────────────────────────────────────────
    for key in ("AN_PROFS_JOURNEYMAN", "AN_PROFS_EXPERT", "AN_PROFS_ARTISAN",
                "AN_PROFS_ONE", "AN_PROFS_ONE_OUTLAND"):
        reg(L(key))
    reg(L("AN_PROFS_TWO")); reg(L("AN_PROFS_TWO_OUTLAND"))
    for prof in ("FIRST_AID", "FISHING", "COOKING"):
        for lvl in ("JOURNEYMAN", "EXPERT", "ARTISAN", "MASTER"):
            reg(L(f"AN_{prof}_{lvl}"))
    reg(L("AN_PROFS_SECONDARY")); reg(L("AN_PROFS_SECONDARY_OUTLAND"))
    for prof in ("FIRST_AID", "FISHING", "COOKING"):
        reg(L(f"AN_{prof}_OUTLAND_MASTER"))
    reg(L("AN_PROFS_FIVE")); reg(L("AN_PROFS_FIVE_OUTLAND"))
    reg(L("AN_STOCKING_UP")); reg(L("AN_STOCKING_UP_2"))
    reg(L("AN_STOCKING_UP_OUTLAND")); reg(L("AN_STOCKING_UP_2_OUTLAND"))
    reg(L("AN_BOOTY_BAY_CONTEST")); reg(L("AN_BOOTY_BAY_FISH"))
    for key in ("AN_FISHING_COLLECTION", "AN_FISHING_WATER", "AN_FISHING_RUM",
                "AN_FISHING_RING", "AN_FISHING_SKULL"):
        reg(L(key))
    for key in ("AN_FISHING_SNAPPER", "AN_FISHING_SEA_BASS", "AN_FISHING_SALMON", "AN_FISHING_LOBSTER"):
        reg(L(key))
    reg(L("AN_FISHING_BIG_SIZE"))
    for c in (25, 50, 100, 250, 500, 1000):
        reg(L("AN_FISHING_COUNT", c), 516 + (25, 50, 100, 250, 500, 1000).index(c))
    reg(L("AN_MR_PINCHY"))
    reg(L("AN_FISHING_OUTLAND_COLLECTION"), 547)
    reg(L("AN_FISHING_BOOK"),        548)
    reg(L("AN_TBC_DAILY_FISH"),      549)
    reg(L("AN_OLD_IRONJAW"),         550)
    reg(L("AN_OLD_CRAFTY"),          551)
    reg(L("AN_FISHING_DIPLOMAT"),    552)
    reg(L("AN_ACCOMPLISHED_ANGLER"), 554)
    reg(L("AN_SECOND_RING"),         624)
    for c in (5, 10, 25, 50, 75):
        reg(L(f"AN_COOKING_RECIPES_{c}"))
    for key in ("AN_COOKING_SOUP", "AN_COOKING_DESSERT", "AN_COOKING_SQUID", "AN_COOKING_DUMPLINGS"):
        reg(L(key))
    reg(L("AN_COOKING_BIG_TABLE"))
    reg(L("AN_COOKING_CAKE"))
    reg(L("AN_CAPTAIN_RUMSEY"),    555)
    reg(L("AN_TBC_DAILY_COOKING"), 556)
    reg(L("AN_TBC_COOKING_RECIPES"), 557)
    reg(L("AN_HAIL_CHEF"),         558)

    # ── WORLD EVENTS ─────────────────────────────────────────────────────────
    reg(L("AN_HALLOWSEND"), 531)
    if is_h:
        reg(L("AN_HALLOWSEND_HORDE_QUEST1"),   532)
        reg(L("AN_HALLOWSEND_HORDE_QUEST2"),   533)
    else:
        reg(L("AN_HALLOWSEND_ALLIANCE_QUEST1"), 532)
        reg(L("AN_HALLOWSEND_ALLIANCE_QUEST2"), 533)
    reg(L("AN_HALLOWSEND_TREATS"),         534)
    reg(L("AN_PUMPKIN"),                   535)
    reg(L("AN_HALLOWSEND_INVOCATION_BUFF"), 536)
    reg(L("AN_HALLOWSEND_MASK"),           537)
    reg(L("AN_HALLOWSEND_MASKS"),          538)
    reg(L("AN_HALLOWSEND_TRANSFORM"),      539)
    reg(L("AN_WINTERVEIL"),                541)
    reg(L("AN_WINTERVEIL_METZEN"),         542)
    reg(L("AN_WINTERVEIL_SMOKEYWOOD"),     543)
    reg(L("AN_WINTERVEIL_GOURMET"),        544)
    reg(L("AN_WINTERVEIL_PRESENTS"),       545)
    if is_h:
        reg(L("AN_WINTERVEIL_SNOWBALL_HORDE"),    546)
    else:
        reg(L("AN_WINTERVEIL_SNOWBALL_ALLIANCE"), 546)
    reg(L("AN_WINTERVEIL_PVP"),            566)
    reg(L("AN_VALENTINES"),                605)
    reg(L("AN_VALENTINES_ROSES"),          606)
    reg(L("AN_VALENTINES_QUEST"),          607)
    reg(L("AN_VALENTINES_CHOCOLATES"),     608)
    reg(L("AN_VALENTINES_DRESS"),          609)
    reg(L("AN_VALENTINES_PIDO"),           610)
    reg(L("AN_LUNAR"),                     611)
    reg(L("AN_LUNAR_COIN"),                612)
    for i, c in enumerate((5, 10, 25, 50)):
        reg(L("AN_LUNAR_COINS", c), 613 + i)
    reg(L("AN_LUNAR_QUEST"),   617)
    reg(L("AN_LUNAR_CLOTHES"), 618)
    reg(L("AN_LUNAR_ELDERS_DUNGEONS"),          619)
    if is_h:
        reg(L("AN_LUNAR_ELDERS_HORDE"),         620)
    else:
        reg(L("AN_LUNAR_ELDERS_ALLIANCE"),       620)
    reg(L("AN_LUNAR_ELDERS_EASTERN_KINGDOMS"),  621)
    reg(L("AN_LUNAR_ELDERS_KALIMDOR"),          622)
    reg(L("AN_NOBLEGARDEN_CLOTHES"), 625)
    reg(L("AN_NOBLEGARDEN_DRESS"),   626)
    reg(L("AN_DOLCE"),               627)    # second dolce entry (item-based)
    reg(L("AN_CHILDREN"),            628)
    reg(L("AN_CHILDREN_PET"),        629)
    reg(L("AN_CHILDREN_PETS"),       630)
    if is_h:
        reg(L("AN_MIDSUMMER"), 633)
        reg(L("AN_MIDSUMMER_QUEST1"),                           634)
        reg(L("AN_MIDSUMMER_DESECRATION_HORDE_KALIMDOR"),       635)
        reg(L("AN_MIDSUMMER_DESECRATION_HORDE_OUTLAND"),        636)
        reg(L("AN_MIDSUMMER_DESECRATION_HORDE_EASTERN_KINGDOMS"), 637)
        reg(L("AN_MIDSUMMER_DESECRATION_HORDE"),                638)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_HORDE_KALIMDOR"),      639)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_HORDE_OUTLAND"),       640)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_HORDE_EASTERN_KINGDOMS"), 641)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_HORDE"),               642)
    else:
        reg(L("AN_MIDSUMMER"), 633)
        reg(L("AN_MIDSUMMER_QUEST1"),                             634)
        reg(L("AN_MIDSUMMER_DESECRATION_ALLIANCE_KALIMDOR"),      635)
        reg(L("AN_MIDSUMMER_DESECRATION_ALLIANCE_OUTLAND"),       636)
        reg(L("AN_MIDSUMMER_DESECRATION_ALLIANCE_EASTERN_KINGDOMS"), 637)
        reg(L("AN_MIDSUMMER_DESECRATION_ALLIANCE"),               638)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_ALLIANCE_KALIMDOR"),     639)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_ALLIANCE_OUTLAND"),      640)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_ALLIANCE_EASTERN_KINGDOMS"), 641)
        reg(L("AN_MIDSUMMER_FLAME_KEEPER_ALLIANCE"),              642)
    reg(L("AN_MIDSUMMER_AHUNE"), 643)

    # ── REPUTATION ───────────────────────────────────────────────────────────
    for i, c in enumerate((1, 5, 10, 15, 20, 25, 30)):
        name = L("AN_REPS_1") if c == 1 else f"{c}{L('AN_REPS_X')}"
        reg(name)
    if is_h:
        reg(L("AN_HORDE_REPS"))
    else:
        reg(L("AN_ALLIANCE_REPS"))
    for key in ("AN_HYDRAXIANS", "AN_ZANDALAR_TRIBE", "AN_BROOD_OF_NOZDORMU",
                "AN_ARGENT_DAWN", "AN_TIMBERMAW_HOLD", "AN_DARKMOON_FAIRE",
                "AN_THORIUM", "AN_SHENDRALAR"):
        reg(L(key))
    reg(L("AN_CENARION"), 576)
    reg(L("AN_TBC_DUNGEON_REPUTATIONS"))  # Horde
    reg(L("AN_TBC_DUNGEON_REPUTATIONS"))  # Alliance
    reg(L("AN_SHATTRATH_REP"))
    reg(L("AN_CENARION_CIRCLE"))
    for key in ("AN_OGRILA", "AN_SPOREGGAR", "AN_CONSORTIUM"):
        reg(L(key))
    if is_h:
        reg(L("AN_MAGHAR"))
    else:
        reg(L("AN_KURENAI"))
    reg(L("AN_NETHERWINGS"))
    reg(L("AN_SKYSHATTERED"))
    for key in ("AN_AMETHYST_EYE", "AN_SCALE_OF_THE_SANDS",
                "AN_ASHTONGUE_DEATHSWORN", "AN_SHATTERED_SUN"):
        reg(L(key))
    reg(L("AN_SKYGUARD"),    559)
    reg(L("AN_HIPPOGRYPH"),  560)
    reg(L("AN_DIPLOMAT"),    564)

    # ── FEATS OF STRENGTH ────────────────────────────────────────────────────
    for key in ("AN_SULFURAS", "AN_THUNDER_FURY", "AN_BLACK_SCARAB", "AN_RED_SCARAB",
                "AN_ATIESH", "AN_TIGER_MOUNT", "AN_RAPTOR_MOUNT",
                "AN_BARON_MOUNT", "AN_SABER_MOUNT"):
        reg(L(key))
    reg(L("AN_PIRATES_HAT"),     523)
    reg(L("AN_WARLOCK_MOUNT"),   524)
    reg(L("AN_PALADIN_MOUNT"),   525)
    reg(L("AN_ARGENT_DAWN_TABARD"), 561)
    reg(L("AN_PREPATCH_QUEST"))
    reg(L("AN_AZZINOTH"))
    reg(L("AN_THORIDAL"))
    reg(L("AN_BEAR_MOUNT"))
    reg(L("AN_HAWK_MOUNT"))
    reg(L("AN_ALAR_MOUNT"))
    reg(L("AN_P3_FIRST_WEEK"))
    reg(L("AN_FLIGHFORM"),       522)
    reg(L("AN_HORSEMAN_MOUNT"),  527)
    reg(L("AN_HERO_SHATTRATH"),  528)
    reg(L("AN_CHAMPION_NAARU"),  529)
    reg(L("AN_HAND_ADAL"),       530)
    reg(L("AN_KRUUL"),           575)
    reg(L("AN_ATTUMEN_MOUNT"),   623)

    # Remove any placeholder 0-ID entries that may have leaked in
    names.pop(0, None)
    return names


def _parse_achievements(path: Path, ach_names: dict, char_class: str = "") -> dict | None:
    """
    Parse AnniversaryAchievements.lua per-character saved vars.
    CA_LocalData: {achievement_id: {1: bool_completed, 2: timestamp, 3: criteria}}
    Returns {"completed": [{"name": str, "ts": int}, ...], "total": int}
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    vars_ = _parse_all_vars(text)
    local_data = vars_.get("CA_LocalData")
    if not isinstance(local_data, dict):
        return None

    completed = []
    total = sum(1 for v in ach_names.values() if v and not v.startswith("AN_"))

    for idx, entry in local_data.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get(1):
            continue
        ts   = int(entry.get(2, 0) or 0)
        name = ach_names.get(idx, f"Achievement #{idx}")
        completed.append({"name": name, "ts": ts})

    completed.sort(key=lambda x: x["ts"], reverse=True)
    return {"completed": completed, "total": total}


# --- Container/inventory parsing ----------------------------------------------
def _parse_containers(path: Path) -> dict | None:
    """
    Parse DataStore_Containers.lua and extract bag + bank contents.
    Returns {
      "bags": [{"name": "Bag N", "items": [{"name": str, "count": int, "quality": str}], "size": int, "free": int}],
      "bank": {"items": [...], "size": int, "free": int}
    }
    """
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    vars_ = _parse_all_vars(text)
    db = vars_.get("DataStore_ContainersDB")
    if not isinstance(db, dict):
        return None

    global_data = db.get("global") or {}
    if not isinstance(global_data, dict):
        return None

    # We return the raw per-character containers map; caller matches to chars
    return global_data.get("Characters") or {}


def _extract_bag_contents(bag_data: dict) -> dict:
    """
    Extract items from a single bag entry.
    bag_data has: links (dict), counts (dict), size (int), freeslots (int)
    Returns {"items": [...], "size": int, "free": int}
    """
    if not isinstance(bag_data, dict):
        return {"items": [], "size": 0, "free": 0}

    links  = bag_data.get("links")  or {}
    counts = bag_data.get("counts") or {}
    size   = int(bag_data.get("size", 0) or 0)
    free   = int(bag_data.get("freeslots", 0) or 0)

    items = []
    if isinstance(links, dict):
        for slot_key, link in links.items():
            if not link or not isinstance(link, str):
                continue
            # Extract item name from link: |cffXXXXXX|Hitem:...|h[Item Name]|h|r
            name_m = re.search(r'\[([^\]]+)\]', link)
            if not name_m:
                continue
            item_name = name_m.group(1)

            # Extract quality color
            quality = "common"
            color_m = re.search(r'\|cff([0-9a-fA-F]{6})', link)
            if color_m:
                color_hex = color_m.group(1).lower()
                quality = QUALITY_COLORS.get(color_hex, "common")

            count = 1
            if isinstance(counts, dict):
                cnt = counts.get(slot_key)
                if cnt is not None:
                    count = int(cnt or 1)

            items.append({"name": item_name, "count": count, "quality": quality})

    return {"items": items, "size": size, "free": free}


def _build_char_containers(containers_entry: dict) -> dict:
    """
    Given a single character's Containers dict from DataStore_Containers,
    build the structured bags + bank result.
    """
    if not isinstance(containers_entry, dict):
        return {}

    raw_containers = containers_entry.get("Containers") or {}
    if not isinstance(raw_containers, dict):
        return {}

    bags = []
    # Bags 0-4: character bags (0=backpack, 1-4=bag slots)
    for bag_num in range(5):
        bag_key = f"Bag{bag_num}"
        bag_data = raw_containers.get(bag_key)
        if bag_data is None:
            continue
        contents = _extract_bag_contents(bag_data)
        bag_label = "Backpack" if bag_num == 0 else f"Bag {bag_num}"
        bags.append({
            "name": bag_label,
            "items": contents["items"],
            "size": contents["size"],
            "free": contents["free"],
        })

    # Bag100: bank
    bank_data = raw_containers.get("Bag100")
    bank = None
    if bank_data is not None:
        contents = _extract_bag_contents(bank_data)
        bank = {
            "items": contents["items"],
            "size": contents["size"],
            "free": contents["free"],
        }

    result: dict = {}
    if bags:
        result["bags"] = bags
    if bank:
        result["bank"] = bank

    return result if result else {}


# --- Mailbox parsing ----------------------------------------------------------
def _parse_mails(path: Path) -> dict | None:
    """
    Parse DataStore_Mails.lua and return per-character pending mail.
    Returns {key: [{"sender": str, "item": str, "count": int, "days": int}, ...]}
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    vars_ = _parse_all_vars(text)
    db = vars_.get("DataStore_MailsDB")
    if not isinstance(db, dict):
        return None
    chars_data = (db.get("global") or {}).get("Characters") or {}
    result: dict = {}
    for key, info in chars_data.items():
        if not isinstance(info, dict):
            continue
        mails = info.get("Mails")
        if isinstance(mails, list):
            mails_iter = enumerate(mails)
        elif isinstance(mails, dict):
            mails_iter = mails.items()
        else:
            continue
        items = []
        for _, mail in mails_iter:
            if not isinstance(mail, dict):
                continue
            link  = mail.get("link", "")
            name_m  = re.search(r'\[([^\]]+)\]', link) if link else None
            color_m = re.search(r'\|cff([0-9a-fA-F]{6})', link) if link else None
            item_name = name_m.group(1) if name_m else ""
            quality = QUALITY_COLORS.get((color_m.group(1).lower() if color_m else ""), "common")
            items.append({
                "sender":       str(mail.get("sender", "")),
                "item":         item_name,
                "item_quality": quality,
                "count":        int(mail.get("count", 1) or 1),
                "days":         int(mail.get("daysLeft", 0) or 0),
            })
        if items:
            result[key] = items
    return result or None


# --- Data aggregation ---------------------------------------------------------
_ach_names_cache: dict[tuple, dict] = {}

def _get_ach_names(cls: str, faction: str) -> dict:
    key = (cls.upper(), faction)
    if key not in _ach_names_cache:
        _ach_names_cache[key] = _load_achievement_names(cls, faction)
    return _ach_names_cache[key]


def gather() -> list[dict]:
    chars: dict[str, dict] = {}

    print("  Loading achievement name table...")

    # -- DataStore_Characters (core stats) ------------------------------------
    print("  DataStore_Characters...")
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

    # -- DataStore_Crafts (professions) ----------------------------------------
    print("  DataStore_Crafts...")
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
            # Skip riding skills -- stored as professions in Classic but not real crafting profs
            if "Riding" in pname:
                continue
            chars[ck]["professions"][pname] = {
                "rank": int(pdata.get("Rank", 0) or 0),
                "max": int(pdata.get("MaxRank", 300) or 300),
                "primary": bool(pdata.get("isPrimary")),
                "secondary": bool(pdata.get("isSecondary")),
            }

    # -- DataStore_Inventory (average item level) ------------------------------
    print("  DataStore_Inventory...")
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

    # -- DataStore_Quests (active quests) --------------------------------------
    print("  DataStore_Quests...")
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

    # -- DataStore_Containers (bags + bank) ------------------------------------
    print("  DataStore_Containers...")
    containers_path = WOW_SAVED_VARS / "DataStore_Containers.lua"
    raw_containers_map = _parse_containers(containers_path)
    # raw_containers_map is {key: char_entry} where key = "Default.Realm.Name"
    if raw_containers_map:
        for key, char_entry in raw_containers_map.items():
            p = key.split(".", 2)
            if len(p) < 3:
                continue
            ck = f"{p[1]}|{p[2]}"
            if ck not in chars:
                continue
            built = _build_char_containers(char_entry)
            if built:
                chars[ck]["containers"] = built

    # -- DataStore_Mails (pending mailbox items) --------------------------------
    print("  DataStore_Mails...")
    mails_map = _parse_mails(WOW_SAVED_VARS / "DataStore_Mails.lua")
    if mails_map:
        for key, items in mails_map.items():
            p = key.split(".", 2)
            if len(p) < 3:
                continue
            ck = f"{p[1]}|{p[2]}"
            if ck in chars and items:
                chars[ck]["mail"] = items

    # -- Per-realm character folders -------------------------------------------
    # The WTF structure has a subfolder per realm under the account directory.
    # Each realm folder contains per-character subfolders with their own SavedVariables.
    # We scan every realm subfolder dynamically so new realms are picked up automatically.
    # Even for DataStore characters we still enrich with AutoBiographer event data.
    print("  Scanning per-realm character folders...")
    for realm_dir in sorted(WOW_ACCOUNT_DIR.iterdir()):
        if not realm_dir.is_dir() or realm_dir.name == "SavedVariables":
            continue
        realm = realm_dir.name
        for cdir in sorted(realm_dir.iterdir()):
            if not cdir.is_dir():
                continue
            sv_dir = cdir / "SavedVariables"
            # Try Skillet first for class/race/faction detail
            who = _skillet_who(sv_dir / "Skillet-Classic.lua")
            name = who.get("player", "") or cdir.name  # fall back to folder name
            ck = f"{realm}|{name}"

            # Add stub only if not already captured by DataStore
            if ck not in chars:
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

            # Always enrich with AutoBiographer (available for ALL chars regardless of DataStore)
            ab = _parse_autobiographer(sv_dir / "AutoBiographer.lua")
            if ab:
                chars[ck]["auto_bio"] = ab
                # Hoist kill lists to top-level for easy JS access
                if ab.get("boss_kills"):
                    chars[ck]["boss_kills"] = ab["boss_kills"]
                if ab.get("pvp_kills"):
                    chars[ck]["pvp_kills"] = ab["pvp_kills"]
                # Fill in zone/guild/played from AB if DataStore didn't have them
                if not chars[ck].get("zone") and ab.get("zone"):
                    chars[ck]["zone"] = ab["zone"]
                if not chars[ck].get("guild") and ab.get("guild"):
                    chars[ck]["guild"]      = ab["guild"]
                    chars[ck]["guild_rank"] = ab.get("guild_rank", "")
                if not chars[ck].get("played") and ab.get("played"):
                    chars[ck]["played"] = ab["played"]

                # Fix level for non-DataStore characters at level 1 using levelup events
                if chars[ck].get("source") != "DataStore" and chars[ck].get("level", 1) == 1:
                    levelup_events = [e for e in (ab.get("events") or []) if e.get("k") == "levelup"]
                    if levelup_events:
                        max_lvl = max(e.get("lvl", 1) for e in levelup_events)
                        if max_lvl > 1:
                            chars[ck]["level"] = max_lvl

            # Parse achievements (names depend on class + faction)
            char_cls     = chars[ck].get("class", "")
            char_faction = chars[ck].get("faction", "Alliance")
            ach_names    = _get_ach_names(char_cls, char_faction)
            ach = _parse_achievements(sv_dir / "AnniversaryAchievements.lua", ach_names)
            if ach:
                chars[ck]["achievements"] = ach

    # -- DataStore profileKeys fallback (catches chars with no Characters data) -
    # A character can appear in profileKeys but have no entry in global.Characters
    # if DataStore registered them but never completed a sync (e.g. Zephyraan).
    print("  Checking for profileKeys-only characters...")
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


# --- Formatting helpers -------------------------------------------------------
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


# --- HTML template ------------------------------------------------------------
HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WoW Classic -- Character Tracker</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%230a0c10'/%3E%3Cg stroke='%23c9a227' stroke-linecap='round' stroke-linejoin='round' fill='none'%3E%3Cline x1='8' y1='8' x2='24' y2='24' stroke-width='3'/%3E%3Cline x1='24' y1='8' x2='8' y2='24' stroke-width='3'/%3E%3Ccircle cx='16' cy='16' r='3.5' stroke-width='2' fill='%23c9a227'/%3E%3Cpolygon points='8,5 10,8 8,11 6,8' fill='%23c9a227' stroke='none'/%3E%3Cpolygon points='24,5 26,8 24,11 22,8' fill='%23c9a227' stroke='none'/%3E%3Cpolygon points='8,21 10,24 8,27 6,24' fill='%23c9a227' stroke='none'/%3E%3Cpolygon points='24,21 26,24 24,27 22,24' fill='%23c9a227' stroke='none'/%3E%3C/g%3E%3C/svg%3E">
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

/* -- header -- */
.site-header{
  background:linear-gradient(180deg,#060810 0%,#0e1220 100%);
  border-bottom:2px solid var(--gold-dim);
  padding:1.1rem 1.5rem;display:flex;align-items:center;gap:1rem
}
.site-header h1{font-size:1.45rem;font-weight:700;letter-spacing:.04em;color:var(--gold);text-shadow:0 0 18px #c9a22740}
.site-header .sub{color:var(--dim);font-size:.8rem;margin-top:.2rem}
.logo{font-size:1.9rem;line-height:1}

/* -- controls -- */
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

/* -- summary bar -- */
.summary{
  background:var(--surface2);border-bottom:1px solid var(--border);
  padding:.55rem 1.5rem;display:flex;gap:2.5rem;flex-wrap:wrap;align-items:center
}
.sp .v{font-size:1rem;font-weight:700;color:var(--gold)}
.sp .l{font-size:.68rem;color:var(--dim);text-transform:uppercase;letter-spacing:.07em}
.summary-stat{font-size:.8rem;border-left:1px solid var(--border);padding-left:2rem}

/* -- grid -- */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(275px,1fr));gap:.9rem;padding:1.1rem 1.5rem}
.realm-hdr{grid-column:1/-1;font-size:.72rem;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);padding:.5rem 0 .15rem;border-bottom:1px solid var(--border)}
.realm-hdr b{color:var(--text);font-weight:600}

/* -- card -- */
.card{background:var(--surface);border:1px solid var(--border);border-radius:7px;overflow:hidden;transition:transform .14s,box-shadow .14s;cursor:pointer}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 28px #00000060}
.card-bar{height:4px}
.card-head{padding:.8rem 1rem .6rem;border-bottom:1px solid var(--border)}
.card-lvl{float:right;font-size:1.25rem;font-weight:800;line-height:1.15}
.card-name{font-size:1.05rem;font-weight:700;letter-spacing:.025em}
.card-sub{font-size:.75rem;color:var(--dim);margin-top:.15rem}
.card-body{padding:.7rem 1rem;display:flex;flex-direction:column;gap:.5rem}
.xp-wrap{position:relative;height:13px;background:#141822;border-radius:3px;overflow:hidden}
.xp-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#2a4f1a,#5db832)}
.xp-rest{position:absolute;top:0;height:100%;background:rgba(90,50,200,.3);border-radius:0 3px 3px 0}
.xp-txt{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:.62rem;color:#ffffffaa;font-weight:600}
.ir{display:flex;gap:.45rem;align-items:flex-start;font-size:.8rem}
.ir .ico{width:1.1em;text-align:center;flex-shrink:0;margin-top:.05em}
.ir .v{flex:1;line-height:1.35}
.gg{color:#ffd700;font-weight:600}.gs{color:#c8c8c8}.gc{color:#b06830}
.profs-lbl{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin-bottom:.35rem}
.prof-row{margin-bottom:.32rem}
.prof-top{font-size:.76rem;display:flex;justify-content:space-between;align-items:baseline}
.prof-rk{font-size:.68rem;color:var(--dim)}
.prof-bar-bg{height:5px;background:#141822;border-radius:3px;overflow:hidden;margin-top:2px}
.pbar-pri{height:100%;border-radius:3px;background:linear-gradient(90deg,#8a4010,#c97830)}
.pbar-sec{height:100%;border-radius:3px;background:linear-gradient(90deg,#10405a,#207090)}
.quests details{margin-top:0}
.quests summary{font-size:.77rem;color:var(--dim);cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:.3rem}
.quests summary::before{content:'\25B8';font-size:.6rem;transition:transform .15s}
details[open] summary::before{content:'\25BE'}
.quest-list{margin:.3rem 0 0 1.1rem;list-style:disc}
.quest-list li{font-size:.73rem;padding:.08rem 0}
.badge{display:inline-block;font-size:.63rem;padding:.12rem .38rem;border-radius:3px;text-transform:uppercase;letter-spacing:.05em}
.badge-limited{color:#a07020;border:1px solid #5a3b0c;background:#1e1608}
.badge-ds{color:#3a7a4a;border:1px solid #1a4025;background:#0e1a12}
.click-hint{font-size:.68rem;color:var(--dim);text-align:center;padding:.3rem 0 0}
.no-res{grid-column:1/-1;text-align:center;padding:3rem;color:var(--dim);font-size:.95rem}

/* -- modal overlay -- */
#overlay{
  position:fixed;inset:0;background:#000000b0;z-index:500;
  display:none;align-items:flex-start;justify-content:center;
  padding:2vh 1rem;overflow-y:auto;
}
#overlay.open{display:flex}
#modal{
  background:var(--surface);border:1px solid var(--gold-dim);border-radius:10px;
  width:100%;max-width:920px;min-height:200px;
  box-shadow:0 20px 60px #00000090;margin:auto;
  display:flex;flex-direction:column;
}
.modal-hdr{
  padding:.85rem 1.1rem;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:.8rem;flex-shrink:0;position:sticky;top:0;
  background:var(--surface);border-radius:10px 10px 0 0;z-index:1;
}
.modal-hdr-bar{width:6px;height:42px;border-radius:3px;flex-shrink:0}
.modal-hdr-info{flex:1}
.modal-hdr-name{font-size:1.25rem;font-weight:700}
.modal-hdr-sub{font-size:.8rem;color:var(--dim);margin-top:.1rem}
.modal-close{background:none;border:1px solid var(--border);color:var(--dim);padding:.2rem .65rem;border-radius:5px;cursor:pointer;font-size:1.1rem;line-height:1}
.modal-close:hover{color:var(--text);border-color:var(--text)}

/* modal tabs */
.modal-tabs{display:flex;border-bottom:1px solid var(--border);padding:0 1.1rem;background:var(--surface2);overflow-x:auto}
.tab-btn{padding:.55rem .9rem;font-size:.8rem;color:var(--dim);cursor:pointer;border-bottom:2px solid transparent;background:none;border-left:none;border-right:none;border-top:none;white-space:nowrap}
.tab-btn.active{color:var(--gold);border-bottom-color:var(--gold)}
.tab-btn:hover:not(.active){color:var(--text)}

/* modal panels */
.modal-body{padding:1rem 1.1rem;flex:1}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* overview panel */
.ov-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
@media(max-width:540px){.ov-grid{grid-template-columns:1fr}}
.ov-section{background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:.7rem .9rem}
.ov-title{font-size:.68rem;text-transform:uppercase;letter-spacing:.09em;color:var(--dim);margin-bottom:.5rem}
.ov-row{display:flex;justify-content:space-between;font-size:.8rem;padding:.15rem 0;border-bottom:1px solid #1a1e2c}
.ov-row:last-child{border:none}
.ov-lbl{color:var(--dim)}
.ov-val{font-weight:600;text-align:right;max-width:60%}

/* timeline panel */
.tl-wrap{max-height:55vh;overflow-y:auto;display:flex;flex-direction:column;gap:.3rem;padding-right:.2rem}
.tl-item{display:flex;gap:.55rem;align-items:flex-start;padding:.35rem .5rem;border-radius:5px;background:var(--surface2);border:1px solid transparent}
.tl-item.tl-levelup{border-color:#2a4a1a;background:#0e1a0a}
.tl-item.tl-boss{border-color:#4a1a1a;background:#1a0a0a}
.tl-item.tl-guild{border-color:#1a2a4a;background:#0a0e1a}
.tl-ico{width:1.4em;text-align:center;flex-shrink:0;margin-top:.05em;font-size:.95rem}
.tl-main{flex:1}
.tl-text{font-size:.8rem;line-height:1.35}
.tl-meta{font-size:.67rem;color:var(--dim);margin-top:.1rem}
.tl-xp{font-size:.7rem;color:#5db832}
.tl-filter{display:flex;gap:.4rem;flex-wrap:wrap;padding:.5rem 0;border-bottom:1px solid var(--border);margin-bottom:.6rem}
.tf-btn{font-size:.72rem;padding:.18rem .5rem;border-radius:4px;border:1px solid var(--border);background:var(--surface2);color:var(--dim);cursor:pointer}
.tf-btn.on{background:#1a2040;border-color:#3a5090;color:#9ab0f0}
.tl-count{font-size:.72rem;color:var(--dim);margin-bottom:.5rem}

/* zones panel */
.zones-wrap{columns:2;column-gap:1rem}
@media(max-width:500px){.zones-wrap{columns:1}}
.zone-block{break-inside:avoid;margin-bottom:.7rem}
.zone-hdr{font-size:.78rem;font-weight:700;color:var(--gold);padding:.2rem 0;border-bottom:1px solid var(--border);margin-bottom:.25rem}
.sz-item{font-size:.72rem;color:var(--dim);padding:.1rem 0 .1rem .6rem;border-left:2px solid #252b42}
.sz-item::before{content:'• '}

/* achievements panel */
.ach-summary{font-size:.78rem;color:var(--dim);margin-bottom:.75rem}
.ach-summary b{color:var(--gold)}
.ach-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.45rem}
.ach-item{background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:.45rem .65rem}
.ach-name{font-size:.78rem;font-weight:600;color:var(--text)}
.ach-date{font-size:.67rem;color:var(--dim);margin-top:.15rem}

/* inventory panel */
.inv-section-title{font-size:.78rem;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:.07em;margin:.75rem 0 .4rem;padding-bottom:.2rem;border-bottom:1px solid var(--border)}
.inv-section-title:first-child{margin-top:0}
.inv-bags-grid{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}
@media(max-width:500px){.inv-bags-grid{grid-template-columns:1fr}}
.inv-bag{background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:.55rem .75rem}
.inv-bag-name{font-size:.72rem;font-weight:700;color:var(--text);margin-bottom:.35rem;display:flex;justify-content:space-between}
.inv-bag-meta{font-size:.65rem;color:var(--dim)}
.inv-item{font-size:.75rem;padding:.12rem 0;border-bottom:1px solid #1a1e2c}
.inv-item:last-child{border:none}
.inv-count{color:var(--dim);font-size:.68rem}
/* quality colors */
.q-poor{color:#9d9d9d}
.q-common{color:#e8e0c8}
.q-uncommon{color:#1eff00}
.q-rare{color:#0070dd}
.q-epic{color:#a335ee}
.q-legendary{color:#ff8000}
</style>
</head>
<body>

<header class="site-header">
  <div class="logo">&#9876;&#65039;</div>
  <div>
    <h1>WoW Classic -- Character Tracker</h1>
    <div class="sub" id="gen-time"></div>
  </div>
</header>

<div class="controls">
  <label>Realm</label>
  <select id="fRealm" onchange="render()"><option value="">All Realms</option></select>
  <label>Class</label>
  <select id="fClass" onchange="render()"><option value="">All Classes</option></select>
  <label>Sort</label>
  <select id="sSort" onchange="render()">
    <option value="level">Level (High to Low)</option>
    <option value="name">Name A to Z</option>
    <option value="realm">Realm</option>
    <option value="played">Played Time</option>
    <option value="money">Wealth</option>
    <option value="last_login">Last Login</option>
  </select>
  <div class="flex-sep"></div>
  <label>Search</label>
  <input type="text" id="sSearch" placeholder="Name or item..." oninput="render();searchItems()" style="width:160px">
</div>
<div id="item-search-results" style="display:none"></div>

<div class="summary" id="summary"></div>
<div class="grid"   id="grid"></div>

<!-- Detail modal -->
<div id="overlay" onclick="if(event.target===this)closeModal()">
  <div id="modal">
    <div class="modal-hdr" id="modal-hdr"></div>
    <div class="modal-tabs" id="modal-tabs"></div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const CHARS = __CHARS__;
const CC    = __CLASS_COLORS__;
const MAX_LEVEL = __MAX_LEVEL__;

/* -- init -- */
(function(){
  document.getElementById('gen-time').textContent = 'Generated __GEN_TIME__';
  const realms  = [...new Set(CHARS.map(c=>c.realm))].sort();
  const classes = [...new Set(CHARS.map(c=>c.class).filter(Boolean))].sort();
  const rs = document.getElementById('fRealm');
  realms.forEach(r=>{const o=document.createElement('option');o.value=r;o.textContent=r;rs.appendChild(o)});
  const cs = document.getElementById('fClass');
  classes.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c[0]+c.slice(1).toLowerCase();cs.appendChild(o)});
  render();
})();

/* -- sort key helper -- */
function sortKey(c, sf){
  switch(sf){
    case 'level':      return [-c.level, c.name];
    case 'name':       return [c.name];
    case 'realm':      return [c.realm, c.name];
    case 'played':     return [-c.played];
    case 'money':      return [-c.money];
    case 'last_login': return [-c.last_login];
  }
  return [c.name];
}
function cmpArrays(a, b){
  for(let i=0;i<Math.max(a.length,b.length);i++){
    const av=a[i]??0, bv=b[i]??0;
    if(av<bv)return -1;
    if(av>bv)return 1;
  }
  return 0;
}

/* -- grid render -- */
function render(){
  const rf=document.getElementById('fRealm').value;
  const cf=document.getElementById('fClass').value;
  const sf=document.getElementById('sSort').value;
  const q =document.getElementById('sSearch').value.toLowerCase();
  let list=CHARS.filter(c=>{
    if(rf&&c.realm!==rf)return false;
    if(cf&&c.class!==cf)return false;
    if(q&&!c.name.toLowerCase().includes(q))return false;
    return true;
  });

  // When showing all realms: keep realms grouped, apply chosen sort within each group.
  // When a single realm is selected: just sort by chosen key.
  if(!rf){
    // Sort by (realm, chosen_sort_key) so realms stay contiguous
    list.sort((a,b)=>{
      const rc=a.realm.localeCompare(b.realm);
      if(rc!==0)return rc;
      return cmpArrays(sortKey(a,sf),sortKey(b,sf));
    });
  } else {
    list.sort((a,b)=>cmpArrays(sortKey(a,sf),sortKey(b,sf)));
  }

  const totalCopper=CHARS.reduce((s,c)=>s+c.money,0);
  const most=CHARS.reduce((a,b)=>a.played>b.played?a:b,CHARS[0]);
  document.getElementById('summary').innerHTML=`
    <div class="sp"><span class="v">${CHARS.length}</span><span class="l">Characters</span></div>
    <div class="sp"><span class="v">${Math.floor(totalCopper/10000).toLocaleString()}<span style="font-size:.7em;color:#8a7020">g</span></span><span class="l">Total Gold</span></div>
    <div class="sp"><span class="v">${Math.max(...CHARS.map(c=>c.level))}</span><span class="l">Highest Level</span></div>
    <div class="sp"><span class="v">${most?.name||''}</span><span class="l">Most Played</span></div>
    <div class="sp"><span class="v">${list.length}</span><span class="l">Showing</span></div>`;
  const grid=document.getElementById('grid');
  grid.innerHTML='';
  if(!list.length){grid.innerHTML='<div class="no-res">No characters match.</div>';return;}
  let lastRealm=null;
  list.forEach((c,i)=>{
    const globalIdx=CHARS.indexOf(c);
    if(!rf&&c.realm!==lastRealm){
      lastRealm=c.realm;
      const cnt=list.filter(x=>x.realm===c.realm).length;
      const h=document.createElement('div');h.className='realm-hdr';
      h.innerHTML=`${c.realm} &nbsp;<b>${cnt} character${cnt!==1?'s':''}</b>`;
      grid.appendChild(h);
    }
    grid.appendChild(buildCard(c,globalIdx));
  });
}

function clr(cls){return CC[cls]||'#aaaaaa';}
function moneyHtml(m){
  let s='';
  if(m.g)s+=`<span class="gg">${m.g.toLocaleString()}g</span> `;
  if(m.s||m.g)s+=`<span class="gs">${m.s}s</span> `;
  s+=`<span class="gc">${m.c}c</span>`;
  return s.trim()||'<span class="gc">0c</span>';
}

function buildCard(c,idx){
  const cc=clr(c.class);
  const atMax=c.level>=MAX_LEVEL;
  const xpPct=atMax?100:Math.round(c.xp/c.xp_max*100);
  const rPct=atMax||!c.rest_xp?0:Math.min(100-xpPct,Math.round(c.rest_xp/c.xp_max*100));
  const profs=Object.entries(c.professions||{});
  const pri=profs.filter(([,p])=>p.primary);
  const sec=profs.filter(([,p])=>p.secondary);
  let profHtml='';
  if(profs.length){
    profHtml='<div><div class="profs-lbl">Professions</div>';
    [...pri,...sec].forEach(([name,p])=>{
      const pct=p.max>0?Math.round(p.rank/p.max*100):0;
      profHtml+=`<div class="prof-row">
        <div class="prof-top">${name}<span class="prof-rk">${p.rank}/${p.max}</span></div>
        <div class="prof-bar-bg"><div class="${p.primary?'pbar-pri':'pbar-sec'}" style="width:${pct}%"></div></div>
      </div>`;
    });
    profHtml+='</div>';
  }
  let questHtml='';
  if(c.active_quests&&c.active_quests.length){
    const ql=c.active_quests.map(q=>`<li>${q}</li>`).join('');
    questHtml=`<div class="quests"><details>
      <summary>&#128203; ${c.active_quests.length} active quest${c.active_quests.length>1?'s':''}</summary>
      <ul class="quest-list">${ql}</ul>
    </details></div>`;
  }
  const hasDetail=!!(c.auto_bio&&(c.auto_bio.events||c.auto_bio.zones_visited));
  const card=document.createElement('div');
  card.className='card';
  card.onclick=()=>openModal(idx);
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
      ${c.guild?`<div class="ir"><span class="ico">&#127984;</span><span class="v">${c.guild}${c.guild_rank?` <span style="color:var(--dim);font-size:.72em">(${c.guild_rank})</span>`:''}</span></div>`:''}
      ${c.zone?`<div class="ir"><span class="ico">&#128205;</span><span class="v">${c.zone}</span></div>`:''}
      ${c.money?`<div class="ir"><span class="ico">&#128176;</span><span class="v">${moneyHtml(c.money_obj)}</span></div>`:''}
      ${c.played?`<div class="ir"><span class="ico">&#9201;</span><span class="v">${c.played_fmt} played</span></div>`:''}
      ${c.avg_ilvl>=1?`<div class="ir"><span class="ico">&#128737;</span><span class="v">Avg ilvl ${c.avg_ilvl}</span></div>`:''}
      ${c.last_login?`<div class="ir"><span class="ico">&#128336;</span><span class="v">Last seen ${c.last_login_fmt}</span></div>`:''}
      ${profHtml}
      ${questHtml}
      <div class="click-hint">${hasDetail?'Click for full details':'Click for details'}</div>
    </div>`;
  return card;
}

/* -- modal -- */
let _activeTab='overview';
function openModal(idx){
  const c=CHARS[idx];
  const cc=clr(c.class);
  document.getElementById('modal-hdr').innerHTML=`
    <div class="modal-hdr-bar" style="background:${cc}"></div>
    <div class="modal-hdr-info">
      <div class="modal-hdr-name" style="color:${cc}">${c.name} <span style="color:var(--dim);font-size:.8rem;font-weight:400">Lv ${c.level}</span></div>
      <div class="modal-hdr-sub">${c.race||''} ${c.class_display||''} &bull; ${c.realm}${c.guild?` &bull; ${c.guild}`:''}</div>
    </div>
    <button class="modal-close" onclick="closeModal()">&#x2715;</button>`;
  const ab=c.auto_bio||{};
  const tabs=[
    {id:'overview', label:'Overview'},
    ...(ab.events&&ab.events.length?[{id:'timeline',label:`Timeline (${ab.event_count||ab.events.length})`}]:[]),
    ...(ab.zones_visited&&Object.keys(ab.zones_visited).length?[{id:'zones',label:`Zones (${Object.keys(ab.zones_visited).length})`}]:[]),
    ...(c.achievements&&c.achievements.completed&&c.achievements.completed.length?[{id:'achievements',label:`Achievements (${c.achievements.completed.length})`}]:[]),
    ...(c.containers?[{id:'inventory',label:'Inventory'}]:[]),
    ...(c.mail&&c.mail.length?[{id:'mail',label:`Mail (${c.mail.length})`}]:[]),
    ...((c.boss_kills&&c.boss_kills.length)||(c.pvp_kills&&c.pvp_kills.length)?[{id:'kills',label:`Kills (${(c.boss_kills||[]).length+(c.pvp_kills||[]).length})`}]:[]),
  ];
  // If active tab doesn't exist for this char, reset to overview
  if(!tabs.find(t=>t.id===_activeTab))_activeTab='overview';
  document.getElementById('modal-tabs').innerHTML=tabs.map(t=>
    `<button class="tab-btn${t.id===_activeTab?' active':''}" onclick="switchTab('${t.id}',${idx})" data-tab="${t.id}">${t.label}</button>`
  ).join('');
  renderTabContent(_activeTab,c);
  document.getElementById('overlay').classList.add('open');
  document.body.style.overflow='hidden';
}
function closeModal(){
  document.getElementById('overlay').classList.remove('open');
  document.body.style.overflow='';
}
function switchTab(id,idx){
  _activeTab=id;
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
  renderTabContent(id,CHARS[idx]);
  if(id==='timeline')setTimeout(renderTlList,0);
}
function renderTabContent(tab,c){
  const body=document.getElementById('modal-body');
  if(tab==='overview')       body.innerHTML=buildOverview(c);
  else if(tab==='timeline')  body.innerHTML=buildTimeline(c);
  else if(tab==='zones')     body.innerHTML=buildZones(c);
  else if(tab==='achievements') body.innerHTML=buildAchievements(c);
  else if(tab==='inventory') body.innerHTML=buildInventory(c);
  else if(tab==='mail')      body.innerHTML=buildMail(c);
  else if(tab==='kills')     body.innerHTML=buildKills(c);
}

/* -- Overview tab -- */
function buildOverview(c){
  const profs=Object.entries(c.professions||{});
  const pri=profs.filter(([,p])=>p.primary);
  const sec=profs.filter(([,p])=>p.secondary);
  let profRows='';
  [...pri,...sec].forEach(([name,p])=>{
    const pct=p.max>0?Math.round(p.rank/p.max*100):0;
    profRows+=`<div class="prof-row">
      <div class="prof-top">${name}<span class="prof-rk">${p.rank}/${p.max}</span></div>
      <div class="prof-bar-bg"><div class="${p.primary?'pbar-pri':'pbar-sec'}" style="width:${pct}%"></div></div>
    </div>`;
  });
  const ab=c.auto_bio||{};
  const zoneCount=ab.zones_visited?Object.keys(ab.zones_visited).length:0;
  const subZoneCount=ab.zones_visited?Object.values(ab.zones_visited).reduce((s,a)=>s+a.length,0):0;
  const questCount=(ab.events||[]).filter(e=>e.k==='quest').length;
  const bossCount=(ab.events||[]).filter(e=>e.k==='boss').length;
  const levelsTracked=(ab.events||[]).filter(e=>e.k==='levelup').length;
  return `<div class="ov-grid">
    <div class="ov-section">
      <div class="ov-title">Character</div>
      <div class="ov-row"><span class="ov-lbl">Class</span><span class="ov-val">${c.class_display||'&mdash;'}</span></div>
      <div class="ov-row"><span class="ov-lbl">Race</span><span class="ov-val">${c.race||'&mdash;'}</span></div>
      <div class="ov-row"><span class="ov-lbl">Level</span><span class="ov-val">${c.level}</span></div>
      <div class="ov-row"><span class="ov-lbl">Faction</span><span class="ov-val">${c.faction||'&mdash;'}</span></div>
      <div class="ov-row"><span class="ov-lbl">Realm</span><span class="ov-val">${c.realm}</span></div>
      ${c.guild?`<div class="ov-row"><span class="ov-lbl">Guild</span><span class="ov-val">${c.guild}</span></div>`:''}
      ${c.guild_rank?`<div class="ov-row"><span class="ov-lbl">Rank</span><span class="ov-val">${c.guild_rank}</span></div>`:''}
    </div>
    <div class="ov-section">
      <div class="ov-title">Progress</div>
      ${c.played?`<div class="ov-row"><span class="ov-lbl">Time Played</span><span class="ov-val">${c.played_fmt}</span></div>`:''}
      ${c.zone?`<div class="ov-row"><span class="ov-lbl">Last Zone</span><span class="ov-val">${c.zone}</span></div>`:''}
      ${c.avg_ilvl>=1?`<div class="ov-row"><span class="ov-lbl">Avg Item Level</span><span class="ov-val">${c.avg_ilvl}</span></div>`:''}
      ${c.money?`<div class="ov-row"><span class="ov-lbl">Gold</span><span class="ov-val">${moneyHtml(c.money_obj)}</span></div>`:''}
      ${c.bind?`<div class="ov-row"><span class="ov-lbl">Hearthstone</span><span class="ov-val">${c.bind}</span></div>`:''}
      ${c.last_login?`<div class="ov-row"><span class="ov-lbl">Last Login</span><span class="ov-val">${c.last_login_fmt}</span></div>`:''}
      ${questCount?`<div class="ov-row"><span class="ov-lbl">Quests Completed</span><span class="ov-val">${questCount}</span></div>`:''}
    </div>
    ${questCount||bossCount||zoneCount?`<div class="ov-section">
      <div class="ov-title">Lifetime Stats (AutoBiographer)</div>
      ${questCount?`<div class="ov-row"><span class="ov-lbl">Quests Completed</span><span class="ov-val">${questCount}</span></div>`:''}
      ${bossCount?`<div class="ov-row"><span class="ov-lbl">Bosses Killed</span><span class="ov-val">${bossCount}</span></div>`:''}
      ${zoneCount?`<div class="ov-row"><span class="ov-lbl">Zones Explored</span><span class="ov-val">${zoneCount} zones / ${subZoneCount} areas</span></div>`:''}
      ${levelsTracked?`<div class="ov-row"><span class="ov-lbl">Levels Tracked</span><span class="ov-val">${levelsTracked}</span></div>`:''}
    </div>`:''}
    ${profs.length?`<div class="ov-section">
      <div class="ov-title">Professions</div>
      ${profRows}
    </div>`:''}
    ${c.active_quests&&c.active_quests.length?`<div class="ov-section" style="grid-column:1/-1">
      <div class="ov-title">Active Quests (${c.active_quests.length})</div>
      ${c.active_quests.map(q=>`<div class="ov-row"><span class="ov-val" style="color:var(--text)">${q}</span></div>`).join('')}
    </div>`:''}
  </div>`;
}

/* -- Timeline tab -- */
const TL_FILTERS=['levelup','quest','boss','guild_join','guild_leave','guild_rank','zone','skill','rep','bg_enter'];
const TL_LABELS={
  levelup:'Level Up', quest:'Quests', boss:'Bosses',
  guild_join:'Guild', guild_leave:'Guild', guild_rank:'Guild',
  zone:'Travel', skill:'Skills', rep:'Reputation', bg_enter:'Battleground'
};
const TL_ICO={levelup:'^',quest:'[Q]',boss:'[X]',guild_join:'[G]',guild_leave:'[G]',guild_rank:'[G]',zone:'[Z]',skill:'[S]',rep:'[R]',bg_enter:'[BG]',bg_end:'[BG]',spell:'[*]'};
let _tlFilters=new Set(['levelup','quest','boss','guild_join','guild_leave','guild_rank','zone','skill','rep']);
let _tlCharIdx=null;
function buildTimeline(c){
  _tlCharIdx=CHARS.indexOf(c);
  const filterBtns=TL_FILTERS.map(f=>`<button class="tf-btn${_tlFilters.has(f)?' on':''}" onclick="toggleFilter('${f}')">${TL_LABELS[f]||f}</button>`).join('');
  return `<div class="tl-filter">${filterBtns}</div><div id="tl-list"></div>`;
}
function toggleFilter(f){
  if(_tlFilters.has(f))_tlFilters.delete(f);else _tlFilters.add(f);
  document.querySelectorAll('.tf-btn').forEach(b=>{
    const bf=b.getAttribute('onclick').match(/'(\w+)'/)?.[1];
    if(bf)b.classList.toggle('on',_tlFilters.has(bf));
  });
  renderTlList();
}
function renderTlList(){
  const c=CHARS[_tlCharIdx];
  if(!c||!c.auto_bio?.events)return;
  const events=[...c.auto_bio.events].reverse();
  const filtered=events.filter(e=>_tlFilters.has(e.k));
  const list=document.getElementById('tl-list');
  if(!list)return;
  if(!filtered.length){list.innerHTML='<div style="color:var(--dim);padding:1rem;font-size:.82rem">No events match the active filters.</div>';return;}
  list.innerHTML=`<div class="tl-count">${filtered.length} events</div><div class="tl-wrap">${filtered.map(e=>tlItemHtml(e)).join('')}</div>`;
}
function tlItemHtml(e){
  const ico=TL_ICO[e.k]||'*';
  const ts=e.ts?new Date(e.ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):'';
  let text='', extra='', cls='';
  switch(e.k){
    case 'levelup': text=`<b>Reached Level ${e.lvl}</b>`; cls='tl-levelup'; break;
    case 'quest':   text=e.title||'Quest completed'; extra=`<span class="tl-xp">+${e.xp.toLocaleString()} XP${e.gold?` &nbsp;${Math.floor(e.gold/10000)}g${Math.floor((e.gold%10000)/100)}s`:''}`;break;
    case 'boss':    text=`Killed: <b>${e.boss}</b>`; cls='tl-boss'; break;
    case 'guild_join': text=`Joined guild: <b>${e.guild}</b>`; cls='tl-guild'; break;
    case 'guild_leave': text=`Left guild: <b>${e.guild}</b>`; cls='tl-guild'; break;
    case 'guild_rank': text=`Guild rank: <b>${e.rank}</b>`; cls='tl-guild'; break;
    case 'zone':    text=`Entered: ${e.zone}`; break;
    case 'skill':   text=`${e.skill}: <b>${e.lvl}</b>`; break;
    case 'rep':     text=`${e.faction}: <b>${e.standing}</b>`; break;
    case 'bg_enter': text='Entered Battleground'; break;
    default: text=e.k;
  }
  return `<div class="tl-item ${cls}"><div class="tl-ico">${ico}</div><div class="tl-main"><div class="tl-text">${text}${extra?`<br>${extra}</span>`:''}
  </div>${ts?`<div class="tl-meta">${ts}</div>`:''}</div></div>`;
}

/* -- Zones tab -- */
function buildZones(c){
  const zv=c.auto_bio?.zones_visited||{};
  const zones=Object.entries(zv).sort((a,b)=>a[0].localeCompare(b[0]));
  if(!zones.length)return '<div style="color:var(--dim);padding:1rem">No zone data available.</div>';
  const blocks=zones.map(([zone,subzones])=>`
    <div class="zone-block">
      <div class="zone-hdr">${zone} <span style="color:var(--dim);font-size:.7em">(${subzones.length})</span></div>
      ${subzones.map(s=>`<div class="sz-item">${s}</div>`).join('')}
    </div>`).join('');
  const total=zones.reduce((s,[,a])=>s+a.length,0);
  return `<div style="font-size:.75rem;color:var(--dim);margin-bottom:.75rem">${zones.length} zones &bull; ${total} areas explored</div>
    <div class="zones-wrap">${blocks}</div>`;
}

/* -- Achievements tab -- */
function buildAchievements(c){
  const ach=c.achievements;
  if(!ach||!ach.completed||!ach.completed.length){
    return '<div style="color:var(--dim);padding:1rem">No achievement data available.</div>';
  }
  const totalDef=ach.total||143;
  const done=ach.completed.length;
  const items=ach.completed.map(a=>{
    const ds=a.ts?new Date(a.ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}):'';
    return `<div class="ach-item">
      <div class="ach-name">${a.name}</div>
      ${ds?`<div class="ach-date">${ds}</div>`:''}
    </div>`;
  }).join('');
  return `<div class="ach-summary"><b>${done}</b> / ${totalDef} completed</div>
    <div class="ach-grid">${items}</div>`;
}

/* -- Inventory tab -- */
function buildInventory(c){
  const ct=c.containers;
  if(!ct)return '<div style="color:var(--dim);padding:1rem">No inventory data available.</div>';

  function itemsHtml(items){
    if(!items||!items.length)return '<div style="color:var(--dim);font-size:.72rem">Empty</div>';
    return items.map(it=>`<div class="inv-item q-${it.quality||'common'}">
      ${it.name}${it.count>1?` <span class="inv-count">x${it.count}</span>`:''}
    </div>`).join('');
  }

  let html='';

  // Character bags
  if(ct.bags&&ct.bags.length){
    html+='<div class="inv-section-title">Character Bags</div>';
    html+='<div class="inv-bags-grid">';
    ct.bags.forEach(bag=>{
      const totalSlots=bag.size||0;
      const used=totalSlots-bag.free;
      html+=`<div class="inv-bag">
        <div class="inv-bag-name">${bag.name}<span class="inv-bag-meta">${bag.free}/${totalSlots} free</span></div>
        ${itemsHtml(bag.items)}
      </div>`;
    });
    html+='</div>';
  }

  // Bank
  if(ct.bank){
    html+='<div class="inv-section-title">Bank</div>';
    const b=ct.bank;
    const totalSlots=b.size||0;
    html+=`<div class="inv-bag" style="max-width:100%">
      <div class="inv-bag-name">Bank<span class="inv-bag-meta">${b.free}/${totalSlots} free</span></div>
      ${itemsHtml(b.items)}
    </div>`;
  }

  return html||'<div style="color:var(--dim);padding:1rem">No inventory data found.</div>';
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();hideItemSearch();}});

// Expose openModal globally (allow tab reset logic inline in openModal above)
window.openModal=openModal;
window.switchTab=switchTab;

/* -- Mail tab -- */
function buildMail(c){
  const mails=c.mail||[];
  if(!mails.length) return '<div style="color:var(--dim);padding:1rem">No pending mail.</div>';
  const q={common:'#fff',uncommon:'#1eff00',rare:'#0070dd',epic:'#a335ee',legendary:'#ff8000',poor:'#9d9d9d'};
  const rows=mails.map(m=>{
    const col=q[m.item_quality]||'#fff';
    return `<tr>
      <td style="color:var(--dim)">${m.sender}</td>
      <td style="color:${col}">${m.item||'<em style="color:var(--dim)">letter</em>'}</td>
      <td style="text-align:right">${m.count>1?'x'+m.count:''}</td>
      <td style="text-align:right;color:var(--dim)">${m.days}d left</td>
    </tr>`;
  }).join('');
  return `<table style="width:100%;border-collapse:collapse;font-size:.85rem">
    <thead><tr style="color:var(--dim);border-bottom:1px solid var(--border)">
      <th style="text-align:left;padding:.3rem .4rem">From</th>
      <th style="text-align:left;padding:.3rem .4rem">Item</th>
      <th></th><th style="text-align:right;padding:.3rem .4rem">Expires</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

/* -- Kills tab -- */
function buildKills(c){
  const bosses=c.boss_kills||[];
  const pvp=c.pvp_kills||[];
  if(!bosses.length&&!pvp.length) return '<div style="color:var(--dim);padding:1rem">No kill data recorded.</div>';
  const CLASS_ICON={
    'Warrior':'⚔','Paladin':'✝','Hunter':'🏹','Rogue':'🗡','Priest':'✨',
    'Death Knight':'💀','Shaman':'⚡','Mage':'🔵','Warlock':'🔮','Druid':'🌿',
    'Monk':'👊','Demon Hunter':'🦇','Evoker':'🐉'
  };
  let html='';

  if(bosses.length){
    html+=`<div style="margin-bottom:1.2rem">
      <div style="font-weight:600;color:var(--gold);margin-bottom:.5rem">Boss Kills <span style="color:var(--dim);font-weight:400;font-size:.85rem">(${bosses.length})</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:.3rem .5rem">
        ${bosses.map(b=>`<span style="background:rgba(255,200,50,.1);border:1px solid rgba(255,200,50,.25);border-radius:3px;padding:.15rem .45rem;font-size:.82rem;color:#f8cc1b">${b}</span>`).join('')}
      </div>
    </div>`;
  }

  if(pvp.length){
    const byClass={};
    pvp.forEach(p=>{ (byClass[p.class]=byClass[p.class]||[]).push(p); });
    const classSummary=Object.entries(byClass).sort((a,b)=>b[1].length-a[1].length)
      .map(([cls,kills])=>`<span title="${kills.map(k=>k.name).join(', ')}" style="cursor:help;background:rgba(255,50,50,.1);border:1px solid rgba(255,50,50,.25);border-radius:3px;padding:.15rem .45rem;font-size:.82rem;color:#ff6060">${CLASS_ICON[cls]||'⚔'} ${cls} <strong>${kills.length}</strong></span>`).join('');
    const rows=pvp.map(p=>`<tr>
      <td style="padding:.2rem .4rem">${p.name}</td>
      <td style="padding:.2rem .4rem;color:var(--dim)">${p.race||''}</td>
      <td style="padding:.2rem .4rem;color:var(--dim)">${p.class||''}</td>
    </tr>`).join('');
    html+=`<div>
      <div style="font-weight:600;color:#ff6060;margin-bottom:.5rem">PvP Kills <span style="color:var(--dim);font-weight:400;font-size:.85rem">(${pvp.length})</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:.3rem .5rem;margin-bottom:.8rem">${classSummary}</div>
      <details>
        <summary style="cursor:pointer;color:var(--dim);font-size:.85rem;margin-bottom:.4rem">Show full list</summary>
        <table style="width:100%;border-collapse:collapse;font-size:.82rem;margin-top:.4rem">
          <thead><tr style="color:var(--dim);border-bottom:1px solid var(--border)">
            <th style="text-align:left;padding:.25rem .4rem">Name</th>
            <th style="text-align:left;padding:.25rem .4rem">Race</th>
            <th style="text-align:left;padding:.25rem .4rem">Class</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>
    </div>`;
  }
  return `<div style="padding:.25rem">${html}</div>`;
}

/* -- Account gold total in summary -- */
(function(){
  const totalCopper=CHARS.reduce((s,c)=>s+(c.money||0),0);
  const g=Math.floor(totalCopper/10000);
  const s=Math.floor((totalCopper%10000)/100);
  const c2=totalCopper%100;
  const el=document.getElementById('summary');
  if(el){
    const goldEl=document.createElement('div');
    goldEl.className='summary-stat';
    goldEl.innerHTML=`<span style="color:var(--dim)">Account Gold:</span> <span style="color:#f8cc1b">${g.toLocaleString()}g</span> <span style="color:#c0c0c0">${s}s</span> <span style="color:#cd7f32">${c2}c</span>`;
    el.appendChild(goldEl);
  }
})();

/* -- Cross-character item search -- */
function searchItems(){
  const q=(document.getElementById('sSearch').value||'').trim().toLowerCase();
  const box=document.getElementById('item-search-results');
  if(q.length<2){box.style.display='none';return;}
  const rows=[];
  CHARS.forEach(c=>{
    const bags=[...((c.containers||{}).bags||[]),((c.containers||{}).bank?{name:'Bank',items:c.containers.bank.items}:null)].filter(Boolean);
    bags.forEach(bag=>{
      (bag.items||[]).forEach(item=>{
        if(item.name.toLowerCase().includes(q)){
          rows.push({char:c.name,realm:c.realm,bag:bag.name,item:item.name,count:item.count,quality:item.quality});
        }
      });
    });
  });
  if(!rows.length){box.innerHTML='<div style="padding:.5rem 1rem;color:var(--dim)">No items found.</div>';box.style.display='block';return;}
  const qmap={common:'#fff',uncommon:'#1eff00',rare:'#0070dd',epic:'#a335ee',legendary:'#ff8000',poor:'#9d9d9d'};
  const html=rows.map(r=>`<div style="display:flex;gap:.8rem;padding:.35rem 1rem;border-bottom:1px solid var(--border);align-items:center">
    <span style="color:${qmap[r.quality]||'#fff'};min-width:180px">${r.item}${r.count>1?` <span style="color:var(--dim)">x${r.count}</span>`:''}</span>
    <span style="color:var(--text)">${r.char}</span>
    <span style="color:var(--dim)">${r.realm}</span>
    <span style="color:var(--dim);margin-left:auto">${r.bag}</span>
  </div>`).join('');
  box.innerHTML=`<div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;max-height:300px;overflow-y:auto;font-size:.85rem;margin:0 1rem .5rem">`+
    `<div style="padding:.4rem 1rem;color:var(--dim);border-bottom:1px solid var(--border)">${rows.length} result${rows.length!==1?'s':''} for "${q}"</div>`+
    html+`</div>`;
  box.style.display='block';
}
function hideItemSearch(){document.getElementById('item-search-results').style.display='none';}
</script>
</body>
</html>

"""


# --- Main ---------------------------------------------------------------------
def main():
    print("Gathering WoW character data...")
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
    print("Open index.html in any browser.")
    print("Re-run this script after logging in with new characters.")


if __name__ == "__main__":
    main()
