"""Import *verified source identifiers* from a local SpiralDB checkout.

This is an extraction and curation layer, NOT proof that client-side objects,
spells, animations, spawn slots, or quest dialogue work in an Imlight build.
Unknown records are deliberately protected/unsupported in generated catalogs.
No network or non-stdlib dependencies are required.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from .core import RandomizerError

DIRS = (
    "QuestTemplates", "QuestMetadatas", "ZoneTransfer", "DropTables",
    "NpcInventory", "NpcSpellInventory", "CreatureSpellbook",
)
MAX_SOURCE_FILE_BYTES = 20 * 1024 * 1024


def _sha256_files(root: Path, records: dict[str, list[tuple[str, dict]]]) -> str:
    digest = hashlib.sha256()
    for dirname in sorted(records):
        for name, _ in records[dirname]:
            relpath = f"{dirname}/{name}"
            data = (root / relpath).read_bytes()
            digest.update(len(relpath.encode()).to_bytes(4, "big"))
            digest.update(relpath.encode())
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
    return digest.hexdigest()


def _read_sources(root: Path) -> dict[str, list[tuple[str, dict]]]:
    if not root.is_dir():
        raise RandomizerError(f"SpiralDB directory does not exist: {root}")
    output = {}
    for dirname in DIRS:
        folder = root / dirname
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        output[dirname] = []
        for path in files:
            if path.is_symlink() or path.stat().st_size > MAX_SOURCE_FILE_BYTES:
                raise RandomizerError(f"unsafe SpiralDB source file: {path}")
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeError, ValueError, OSError) as exc:
                raise RandomizerError(f"invalid SpiralDB JSON {path}: {exc}") from exc
            if not isinstance(document, dict):
                raise RandomizerError(f"SpiralDB JSON must be an object: {path}")
            output[dirname].append((path.name, document))
    if not output["QuestTemplates"] or not output["ZoneTransfer"]:
        raise RandomizerError("need a SpiralDB checkout with QuestTemplates/ and ZoneTransfer/ JSON files")
    return output


def _git_revision(root: Path) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=5, check=True)
        value = p.stdout.strip()
        return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else None
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _typed_goal_type(goal: dict) -> str:
    value = str(goal.get("m_goalType") or goal.get("$type") or "")
    return value.rsplit(".", 1)[-1].split(",", 1)[0]


def _unpack_ids(records: list[tuple[str, dict]], key: str, array: str) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = defaultdict(list)
    for filename, doc in records:
        if doc.get(key) is None:
            continue
        idx = str(doc[key])
        for entry in doc.get(array) or []:
            if isinstance(entry, (int, str)):
                results[idx].append({"id": str(entry), "file": filename})
            elif isinstance(entry, dict):
                eid = entry.get("TemplateID")
                if eid is not None:
                    results[idx].append({"id": str(eid), "level": entry.get("Level"),
                                         "required_spell_id": entry.get("RequiredSpellID"), "file": filename})
    return dict(sorted(results.items()))


def _curated_spells(entries: list[dict]) -> list[dict]:
    ids = set()
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RandomizerError("spell overlay entries must be JSON objects")
        try:
            spell_id = str(entry["id"])
            pips = int(entry["pips"])
            level = int(entry["min_level"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RandomizerError("each curated spell needs id, pips and min_level") from exc
        if not spell_id.isdecimal() or int(spell_id) <= 0 or spell_id in ids:
            raise RandomizerError(f"spell overlay must use unique positive numeric game template IDs: {spell_id}")
        if pips < 0 or level < 1 or pips > 20:
            raise RandomizerError(f"invalid pip/level in spell overlay: {spell_id}")
        if not isinstance(entry.get("school"), str) or not entry["school"].strip():
            raise RandomizerError(f"missing school in curated spell: {spell_id}")
        if not isinstance(entry.get("tags"), list) or not all(isinstance(t, str) for t in entry["tags"]):
            raise RandomizerError(f"invalid tags in curated spell: {spell_id}")
        if entry.get("supported") is not True:
            raise RandomizerError(f"curated spell not explicitly verified as supported: {spell_id}")
        ids.add(spell_id)
        result.append({"id": spell_id, "school": entry["school"], "pips": pips,
                       "min_level": level, "tags": sorted(set(entry["tags"])), "supported": True})
    return sorted(result, key=lambda s: s["id"])


def import_spiraldb(root: str | Path, *, quest_prefix: str = "WC-",
                    start_zone: str = "WizardCity/WC_Hub",
                    spell_overlay: list[dict] | None = None) -> tuple[dict, dict]:
    """Build a cautious catalog + audit report from pinned local SpiralDB JSON.

    Quest persona names, zone names, trigger indices, drop-table items and trainer
    spell template IDs are real source values. They are NOT proof of valid NPC
    spawn instance IDs, renderable visual templates or castable spell templates.
    Those features stay protected/unsupported until reviewed in the target build.
    """
    base = Path(root).expanduser().resolve()
    records = _read_sources(base)
    revision = _git_revision(base)
    source_hash = _sha256_files(base, records)

    zones: set[str] = set()
    portals: list[dict] = []
    for name, zone_doc in records["ZoneTransfer"]:
        zone_name = zone_doc.get("ZoneName")
        if not isinstance(zone_name, str) or not zone_name.startswith("WizardCity/"):
            continue
        zones.add(zone_name)
        for index, entry in enumerate(zone_doc.get("Teleports") or []):
            if not isinstance(entry, dict):
                continue
            destination = (entry.get("Teleport") or {}).get("m_destinationZone")
            if not isinstance(destination, str) or not destination.startswith("WizardCity/"):
                continue
            zones.add(destination)
            portals.append({"id": f"zone-transfer:{zone_name}:{name}:{index}", "source": zone_name,
                            "destination": destination, "trigger": str(entry.get("TriggerName", "")),
                            "source_file": name, "protected": True})
    if not zones:
        raise RandomizerError("SpiralDB ZoneTransfer has no WizardCity zones")
    if start_zone not in zones:
        raise RandomizerError(f"requested start zone not present in SpiralDB transfer data: {start_zone}")

    quests = {}
    personas: dict[tuple[str, str], set[str]] = defaultdict(set)
    unplaced = []
    for filename, quest in records["QuestTemplates"]:
        name = quest.get("m_questName")
        if not isinstance(name, str) or not name.startswith(quest_prefix):
            continue
        if name in quests:
            raise RandomizerError(f"duplicate SpiralDB quest name: {name}")
        goals = []
        for goal in quest.get("m_goals") or []:
            if not isinstance(goal, dict):
                continue
            persona = goal.get("m_personaName")
            dest = goal.get("m_destinationZone")
            kind = _typed_goal_type(goal)
            item = {"id": str(goal.get("m_goalName") or ""), "type": kind,
                    "destination_zone": dest if isinstance(dest, str) else None}
            if isinstance(persona, str) and persona:
                item["persona"] = persona
                if isinstance(dest, str) and dest in zones:
                    personas[(persona, dest)].add(name)
                else:
                    unplaced.append({"quest": name, "goal": item["id"], "persona": persona,
                                     "destination_zone": dest})
            goals.append(item)
        raw_end = (quest.get("m_endResults") or {}).get("m_results") or []
        drop_tables = sorted({str(x.get("m_tableName")) for x in raw_end
                              if isinstance(x, dict) and "ResDropTable" in str(x.get("$type", ""))
                              and x.get("m_tableName")})
        quests[name] = {"title_key": str(quest.get("m_questTitle") or ""),
                        "level": int(quest.get("m_questLevel") or 1),
                        "mainline": bool(quest.get("m_mainline", False)),
                        "goals": goals, "start_goals": [str(x) for x in (quest.get("m_startGoals") or [])],
                        "goal_logic": [
                            {"and": list(x.get("m_goalsAND") or []),
                             "or": list(x.get("m_goalsOR") or []),
                             "add": list(x.get("m_goalsToAdd") or []),
                             "complete": bool(x.get("m_completeQuest"))}
                            for x in (quest.get("m_goalLogic") or []) if isinstance(x, dict)],
                        "drop_tables": drop_tables, "file": filename}

    identities = []
    npcs = []
    for (persona, zone), quest_names in sorted(personas.items()):
        logical_id = f"quest-persona:{persona}"
        slot = f"quest-persona-slot:{zone}:{persona}"
        # The quest's persona name is NOT a client NPC template ID.
        if not any(x["id"] == logical_id for x in identities):
            identities.append({"id": logical_id, "group": "unverified", "visual_supported": False,
                               "behavior_compatible": False, "kind": "quest-persona-reference"})
        npcs.append({"slot": slot, "zone": zone, "identity": logical_id,
                     "roles": ["quest_goal"], "protected": True,
                     "appearance_group": "unverified", "quest_names": sorted(quest_names),
                     "location": slot, "unverified_spawn": True})

    # A shop owner's numeric template ID is authoritative for inventory lookup,
    # but not by itself a world spawn slot or compatible visual replacement.
    shops = _unpack_ids(records["NpcInventory"], "TemplateID", "Inventory")
    trainer_spells = _unpack_ids(records["NpcSpellInventory"], "TemplateID", "Spells")
    decks = {str(doc["DeckName"]): [str(x) for x in (doc.get("SpellTemplateIds") or [])]
             for _, doc in records["CreatureSpellbook"] if doc.get("DeckName")}
    tables = {}
    item_sources = defaultdict(set)
    for filename, doc in records["DropTables"]:
        table_name = doc.get("Name")
        if not isinstance(table_name, str) or not table_name:
            continue
        if table_name in tables:
            raise RandomizerError(f"duplicate drop table: {table_name}")
        ids = []
        for item in doc.get("Items") or []:
            if not isinstance(item, dict):
                continue
            ident = item.get("ItemId")
            if ident is None:
                continue
            iid = str(ident)
            ids.append(iid)
            item_sources[iid].add(table_name)
        tables[table_name] = {"items": sorted(set(ids)), "file": filename}

    spells = _curated_spells(spell_overlay or [])
    candidates = sorted({str(spell["id"]) for spells in trainer_spells.values() for spell in spells})
    metadata = {"origin": "https://github.com/Revive101/spiraldb",
                "git_revision": revision, "source_sha256": source_hash,
                "quest_prefix": quest_prefix, "client_assets_verified": False,
                "spawn_templates_verified": False, "npc_appearances_verified": False,
                "spell_curated_count": len(spells)}
    catalog = {
        "catalog_note": "SpiralDB-derived source references. NPCs/portals protected; item pools unsupported; spells need explicit client-tested overlay.",
        "source_metadata": metadata,
        "zones": sorted(zones), "start_zone": start_zone,
        "required_zones": [start_zone], "require_return_paths": True,
        "spells": spells,
        "npcs": npcs, "identities": identities, "npc_locations": [],
        "creature_spawns": [], "creature_pool": [], "boss_spawns": [], "boss_pool": [],
        "reward_checks": [],
        "reward_pool": [{"id": iid, "pool": "unverified", "supported": False,
                         "source_table_count": len(names)} for iid, names in sorted(item_sources.items())],
        "portals": sorted(portals, key=lambda p: p["id"]),
        "source_index": {
            "quests": dict(sorted(quests.items())), "unplaced_persona_goals": unplaced,
            "npc_shops": shops, "trainer_spells": trainer_spells,
            "trainer_spell_template_ids": candidates,
            "creature_decks": dict(sorted(decks.items())),
            "drop_tables": dict(sorted(tables.items())),
        }
    }
    report = {
        "source_metadata": metadata,
        "file_counts": {k: len(v) for k, v in records.items()},
        "import_counts": {"wizard_city_zones": len(zones), "portal_triggers": len(portals),
                          "quests": len(quests), "quest_persona_slots": len(npcs),
                          "unplaced_persona_goals": len(unplaced),
                          "trainer_spells": len(candidates), "curated_spells": len(spells),
                          "drop_tables": len(tables), "item_templates": len(item_sources),
                          "creature_decks": len(decks), "shop_inventory_npcs": len(shops)},
        "safe_to_generate_manifest": any("attack" in s["tags"] and s["pips"] <= 2
                                         and s["min_level"] == 1 for s in spells),
        "not_implemented": [
            "NPC game spawn IDs / appearance compatibility", "NPC quest-role service rebinding",
            "creature/boss spawn ID and level classification", "real combat spell school/pip/tag validation",
            "per-item compatibility and quest reward claims", "complete story dependency graph",
            "safe random portal destinations and return paths", "live Imlight integration"],
    }
    return catalog, report
