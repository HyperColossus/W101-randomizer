"""Opt-in curation from SpiralDB references to *candidate* game-ready records.

Curation is not a substitute for client testing. It refuses unknown provenance,
requires an exact SpiralDB fingerprint and records human verification claims.
No game-server mutations occur here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .core import RandomizerError

_KEYS = {"spiraldb_sha256", "client_build", "imlight_revision", "spells",
         "reward_items", "quest_rewards", "npc_visuals", "portal_triggers"}


def _unique(rows: list, key: str, description: str) -> None:
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RandomizerError(f"{description} entries must be objects")
        value = str(row.get(key, ""))
        if not value or value in seen:
            raise RandomizerError(f"missing/duplicate {description} {key}: {value}")
        seen.add(value)


def _approved(row: dict, *fields: str) -> None:
    for field in fields:
        if row.get(field) is not True:
            raise RandomizerError(f"{field}=true required for {row.get('id', row.get('slot', 'entry'))}")


def _positive_id(value: Any, kind: str) -> str:
    text = str(value)
    if not text.isdecimal() or int(text) <= 0:
        raise RandomizerError(f"{kind} must be a positive decimal template ID: {text}")
    return str(int(text))


def curate_spiraldb(catalog: dict, approvals: dict) -> tuple[dict, dict]:
    """Transform source-derived catalog with pinned, explicitly-reviewed overlays.

    The original SpiralDB index is retained; module flags are still set by the
    ordinary seed settings, and a live Imlight adapter is still required.
    """
    if not isinstance(approvals, dict) or set(approvals) - _KEYS:
        raise RandomizerError("curation file must be an object with known keys")
    meta = catalog.get("source_metadata") or {}
    if meta.get("origin") != "https://github.com/Revive101/spiraldb":
        raise RandomizerError("curation requires a SpiralDB-imported catalog")
    sha = meta.get("source_sha256")
    if not sha or approvals.get("spiraldb_sha256") != sha:
        raise RandomizerError("curation source fingerprint differs from SpiralDB checkout")
    for field in ("client_build", "imlight_revision"):
        if not isinstance(approvals.get(field), str) or not approvals[field].strip():
            raise RandomizerError(f"curation requires a pinned {field}")
    result = deepcopy(catalog)
    index = result.get("source_index") or {}
    report: dict[str, Any] = {"source_sha256": sha, "reviewer_asserted": True,
                              "live_game_verified_by_this_tool": False, "counts": {}}
    for key in _KEYS - {"spiraldb_sha256", "client_build", "imlight_revision"}:
        if not isinstance(approvals.get(key, []), list):
            raise RandomizerError(f"{key} must be an array")

    # Spells need a concrete source ID AND manual client/level/pip verification.
    ids = set(map(str, index.get("trainer_spell_template_ids", [])))
    ids.update(str(s) for values in index.get("creature_decks", {}).values() for s in values)
    from .spiraldb import _curated_spells
    spells = []
    _unique(approvals.get("spells", []), "id", "spells")
    _unique(approvals.get("npc_visuals", []), "slot", "npc_visuals")
    _unique(approvals.get("portal_triggers", []), "id", "portal_triggers")
    for spell in approvals.get("spells", []):
        sid = _positive_id(spell.get("id"), "spell")
        if sid not in ids:
            raise RandomizerError(f"spell {sid} absent from SpiralDB trainer/deck references")
        _approved(spell, "client_verified", "cast_verified")
        spells.append({"id": sid, "school": spell.get("school"), "pips": spell.get("pips"),
                       "min_level": spell.get("min_level"), "tags": spell.get("tags"),
                       "supported": True})
    if spells:
        result["spells"] = _curated_spells(spells)
    report["counts"]["approved_spells"] = len(spells)

    # Extracted drop table presence does not prove an item is valid or equipable.
    item_to_tables: dict[str, set[str]] = {}
    for table, record in index.get("drop_tables", {}).items():
        for ident in record.get("items", []):
            item_to_tables.setdefault(str(ident), set()).add(table)
    reward_items = []
    for row in approvals.get("reward_items", []):
        iid = _positive_id(row.get("id"), "item")
        if iid not in item_to_tables:
            raise RandomizerError(f"item {iid} absent from SpiralDB drop tables")
        _approved(row, "client_verified", "grant_verified")
        pool = row.get("pool")
        if not isinstance(pool, str) or not pool:
            raise RandomizerError(f"item {iid} requires a pool")
        try:
            min_level = int(row["min_level"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RandomizerError(f"item {iid} requires valid min_level") from exc
        if min_level < 1:
            raise RandomizerError(f"item {iid} invalid min_level")
        reward_items.append({"id": iid, "pool": pool, "min_level": min_level, "supported": True})
    _unique(reward_items, "id", "reward_items")
    good_items = {r["id"]: r for r in reward_items}
    rewards = []
    for row in approvals.get("quest_rewards", []):
        quest_name = str(row.get("quest", ""))
        quest = index.get("quests", {}).get(quest_name)
        if not quest:
            raise RandomizerError(f"unrecognized SpiralDB quest {quest_name}")
        iid = _positive_id(row.get("item"), "quest item")
        if iid not in good_items:
            raise RandomizerError(f"quest reward {iid} must be an approved item")
        if not any(t in item_to_tables[iid] for t in quest.get("drop_tables", [])):
            raise RandomizerError(f"item {iid} not present in quest {quest_name}'s linked drop table")
        _approved(row, "quest_grant_verified")
        rewards.append({"id": f"quest:{quest_name}", "kind": "quest", "item": iid,
                        "pool": good_items[iid]["pool"], "level": max(1, int(quest.get("level", 1))),
                        "source_quest": quest_name})
    _unique(rewards, "id", "quest_rewards")
    result["reward_pool"] = reward_items
    result["reward_checks"] = rewards
    report["counts"]["approved_items"] = len(reward_items)
    report["counts"]["approved_quest_rewards"] = len(rewards)

    # Critical protection separation: visual swaps must never authorize role
    # or location swaps as a side effect.
    npc_by_slot = {n["slot"]: n for n in result["npcs"]}
    identities = {i["id"]: i for i in result["identities"]}
    for row in approvals.get("npc_visuals", []):
        slot = str(row.get("slot", ""))
        if slot not in npc_by_slot:
            raise RandomizerError(f"unknown SpiralDB quest persona slot: {slot}")
        _approved(row, "spawn_verified", "client_verified", "services_verified")
        template = _positive_id(row.get("template_id"), "NPC visual")
        group = row.get("group")
        if not isinstance(group, str) or not group:
            raise RandomizerError("NPC visual requires compatibility group")
        ident = f"npcvisual:{template}"
        if ident in identities and identities[ident]["group"] != group:
            raise RandomizerError(f"NPC visual {template} has conflicting groups")
        identities[ident] = {"id": ident, "group": group, "visual_supported": True,
                             "behavior_compatible": True, "template_id": template}
        npc = npc_by_slot[slot]
        npc.update({"identity": ident, "appearance_group": group,
                    "protected": False, "identity_protected": False,
                    "roles_protected": True, "location_protected": True})
    result["identities"] = sorted(identities.values(), key=lambda i: i["id"])
    report["counts"]["approved_npc_visuals"] = len(approvals.get("npc_visuals", []))

    # The importer's zones may be missing scripted connections. Approval alone
    # cannot solve full gameplay reachability; the manifest validator is a gate.
    portal_index = {p["id"]: p for p in result["portals"]}
    for row in approvals.get("portal_triggers", []):
        pid = str(row.get("id", ""))
        if pid not in portal_index:
            raise RandomizerError(f"portal {pid} absent from SpiralDB transfer data")
        _approved(row, "transition_verified", "return_path_verified")
        portal_index[pid]["protected"] = False
    report["counts"]["approved_portals"] = len(approvals.get("portal_triggers", []))

    result["source_metadata"] = {**meta, "curation_sha256": __import__("hashlib").sha256(
        __import__("json").dumps(approvals, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "client_build": approvals["client_build"], "imlight_revision": approvals["imlight_revision"],
        "manually_reviewed": True, "game_integration_verified": False}
    report["warnings"] = ["Approvals are human assertions, not live gameplay test results.",
                          "Imlight still needs an authoritative event/zone adapter."]
    return result, report
