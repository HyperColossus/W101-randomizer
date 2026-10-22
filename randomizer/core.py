"""Deterministic, data-driven W101 randomizer *planner* (no game-server side effects)."""
from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any

ENGINE_VERSION = "0.1.0"
MANIFEST_SCHEMA = 1


class RandomizerError(ValueError):
    """An unsafe or impossible randomizer configuration."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class SeedRng:
    """SHA-256 counter stream, independent from Python's random implementation."""

    def __init__(self, seed: str, namespace: str):
        self.base = canonical([MANIFEST_SCHEMA, str(seed), namespace])
        self.counter = 0

    def below(self, bound: int) -> int:
        if bound <= 0:
            raise RandomizerError("cannot roll from an empty pool")
        # Rejection sampling eliminates modulo bias even for unusual pool sizes.
        limit = (1 << 256) - ((1 << 256) % bound)
        while True:
            digest = hashlib.sha256(self.base + b":" + str(self.counter).encode()).digest()
            self.counter += 1
            number = int.from_bytes(digest, "big")
            if number < limit:
                return number % bound

    def choice(self, entries: list[Any]) -> Any:
        return entries[self.below(len(entries))]

    def shuffle(self, entries: list[Any]) -> list[Any]:
        result = list(entries)
        for i in range(len(result) - 1, 0, -1):
            j = self.below(i + 1)
            result[i], result[j] = result[j], result[i]
        return result


def _index(entries: list[dict], field: str, description: str) -> dict[str, dict]:
    result = {}
    for entry in entries:
        key = str(entry.get(field, ""))
        if not key:
            raise RandomizerError(f"{description} is missing {field}")
        if key in result:
            raise RandomizerError(f"duplicate {description} {field}: {key}")
        result[key] = entry
    return result


def validate_catalog(catalog: dict) -> None:
    for group, field in [
        ("spells", "id"), ("npcs", "slot"), ("identities", "id"),
        ("npc_locations", "id"), ("creature_spawns", "slot"),
        ("creature_pool", "id"), ("boss_spawns", "slot"),
        ("boss_pool", "id"), ("reward_checks", "id"),
        ("reward_pool", "id"), ("portals", "id"),
    ]:
        _index(catalog.get(group, []), field, group)
    zones = catalog.get("zones", [])
    if not zones or len(zones) != len(set(zones)):
        raise RandomizerError("zones must be a nonempty unique list")
    if catalog.get("start_zone") not in zones:
        raise RandomizerError("start_zone must appear in zones")
    for zone in catalog.get("required_zones", []):
        if zone not in zones:
            raise RandomizerError(f"unknown required zone: {zone}")
    for edge in catalog.get("portals", []):
        if edge.get("source") not in zones or edge.get("destination") not in zones:
            raise RandomizerError(f"invalid portal zones: {edge.get('id')}")
    if not any("attack" in spell.get("tags", []) and int(spell.get("pips", 999)) <= 2 and int(spell.get("min_level", 999)) <= 1
               for spell in catalog.get("spells", [])):
        raise RandomizerError("catalog has no beginner-eligible attack spell")


def _shuffle_bijective(entries: list[dict], key: str, rng: SeedRng) -> dict[str, str]:
    """Permute IDs within explicit compatibility groups; exclude protected entries."""
    mappings: dict[str, str] = {}
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        eid = str(entry[key])
        mappings[eid] = eid
        if entry.get("protected", False):
            continue
        group = str(entry.get("group", "default"))
        groups.setdefault(group, []).append(entry)
    for group in sorted(groups):
        items = sorted(groups[group], key=lambda x: str(x[key]))
        options = rng.shuffle([str(x[key]) for x in items])
        mappings.update({str(item[key]): replacement for item, replacement in zip(items, options)})
    return mappings


def _identity_shuffle(catalog: dict, rng: SeedRng) -> dict[str, str]:
    identity_idx = _index(catalog.get("identities", []), "id", "identities")
    results = {}
    for npc in sorted(catalog.get("npcs", []), key=lambda n: n["slot"]):
        original = npc["identity"]
        if original not in identity_idx:
            raise RandomizerError(f"NPC {npc['slot']} references missing identity {original}")
        if npc.get("protected", False):
            results[npc["slot"]] = original
            continue
        group = npc.get("appearance_group", "default")
        options = sorted(
            [i["id"] for i in identity_idx.values() if i.get("group", "default") == group
             and i.get("visual_supported", False) and i.get("behavior_compatible", True)]
        )
        results[npc["slot"]] = rng.choice(options) if options else original
    return results


def _role_shuffle(catalog: dict, rng: SeedRng) -> dict[str, str]:
    entries = []
    for npc in catalog.get("npcs", []):
        # Transfer only to eligible NPCs within the same zone with identical service signatures.
        roles = sorted(npc.get("roles", []))
        entries.append({"slot": npc["slot"], "group": canonical([npc["zone"], roles]).decode(),
                        "protected": npc.get("protected", False) or not roles})
    return _shuffle_bijective(entries, "slot", rng)


def _npc_location_shuffle(catalog: dict, rng: SeedRng) -> dict[str, str]:
    """Permute approved slots within a zone, without stacking NPCs on one point."""
    approved = {(loc["zone"], loc["id"]) for loc in catalog.get("npc_locations", [])
                if loc.get("approved", False)}
    result: dict[str, str] = {}
    groups: dict[str, list[dict]] = {}
    for npc in catalog.get("npcs", []):
        original = str(npc.get("location", npc["slot"]))
        result[npc["slot"]] = original
        if not npc.get("protected", False) and (npc["zone"], original) in approved:
            groups.setdefault(npc["zone"], []).append(npc)
    for zone in sorted(groups):
        npcs = sorted(groups[zone], key=lambda x: x["slot"])
        starts = [str(n.get("location", n["slot"])) for n in npcs]
        if len(starts) != len(set(starts)):
            raise RandomizerError(f"NPC starting locations overlap in {zone}")
        shuffled = rng.shuffle(starts)
        result.update({npc["slot"]: location for npc, location in zip(npcs, shuffled)})
    return result


def _pick_by_tier(spawns: list[dict], options: list[dict], rng: SeedRng) -> dict[str, str]:
    result = {}
    for slot in sorted(spawns, key=lambda x: x["slot"]):
        current = str(slot["id"])
        if slot.get("protected", False):
            result[slot["slot"]] = current
            continue
        tier = int(slot["tier"])
        valid = sorted([str(item["id"]) for item in options
                        if int(item.get("tier", -1)) == tier and item.get("supported", False)])
        if not valid:
            raise RandomizerError(f"no supported tier {tier} replacement for {slot['slot']}")
        result[slot["slot"]] = rng.choice(valid)
    return result


def _reward_shuffle(catalog: dict, settings: dict, seed: str) -> dict[str, str]:
    result = {}
    candidates = catalog.get("reward_pool", [])
    kinds = {"quest": "quest_rewards", "boss": "boss_loot", "mob": "mob_loot"}
    for check in sorted(catalog.get("reward_checks", []), key=lambda x: x["id"]):
        kind = check["kind"]
        if kind not in kinds:
            raise RandomizerError(f"invalid reward check kind: {kind}")
        if not settings.get(kinds[kind], False) or check.get("protected", False):
            result[check["id"]] = check["item"]
            continue
        valid = sorted([x["id"] for x in candidates
                        if x.get("pool") == check.get("pool") and x.get("supported", False)
                        and int(x.get("min_level", 1)) <= int(check.get("level", 1))])
        if not valid:
            raise RandomizerError(f"no compatible reward for {check['id']}")
        result[check["id"]] = SeedRng(seed, "reward:" + check["id"]).choice(valid)
    return result


def _reachable(edges: list[dict], start: str) -> set[str]:
    adj = {}
    for e in edges:
        adj.setdefault(e["source"], []).append(e["destination"])
    found = {start}
    queue = deque([start])
    while queue:
        for dest in adj.get(queue.popleft(), []):
            if dest not in found:
                found.add(dest)
                queue.append(dest)
    return found


def _portal_shuffle(catalog: dict, rng: SeedRng, enabled: bool) -> tuple[dict[str, str], dict]:
    edges = catalog.get("portals", [])
    fixed = [x for x in edges if x.get("protected", False)]
    mutable = sorted([x for x in edges if not x.get("protected", False)], key=lambda x: x["id"])
    original = {x["id"]: x["destination"] for x in edges}
    def valid(mapping: dict[str, str]) -> bool:
        proposed = [{"source": e["source"], "destination": mapping[e["id"]]} for e in edges]
        required = set(catalog.get("required_zones", [])) | {catalog["start_zone"]}
        if not required.issubset(_reachable(proposed, catalog["start_zone"])):
            return False
        return not catalog.get("require_return_paths", True) or all(
            catalog["start_zone"] in _reachable(proposed, zone) for zone in required
        )
    if not valid(original):
        raise RandomizerError("original portal graph cannot reach every required zone and return")
    if not enabled:
        return original, {"reachability_checked": True, "shuffled": False}
    if len(mutable) < 2:
        raise RandomizerError("portal shuffle requires at least two eligible portals")
    destinations = [e["destination"] for e in mutable]
    for _ in range(512):
        rolled = rng.shuffle(destinations)
        proposal = dict(original)
        proposal.update(zip([x["id"] for x in mutable], rolled))
        if proposal != original and valid(proposal):
            return proposal, {"reachability_checked": True, "shuffled": True}
    raise RandomizerError("could not produce a different reachable portal arrangement")


def generate_manifest(catalog: dict, settings: dict) -> dict:
    """Generate *plans* for external game adapters, not live server changes."""
    validate_catalog(catalog)
    seed = str(settings.get("seed", ""))
    if not seed or len(seed) > 128:
        raise RandomizerError("seed must be 1-128 characters")
    modules = settings.get("modules", {})
    spell_mode = modules.get("spells", "vanilla")
    if spell_mode not in ("vanilla", "wildcard", "draft"):
        raise RandomizerError("spells must be vanilla, wildcard, or draft")
    npc_slots = [n["slot"] for n in catalog.get("npcs", [])]
    identity = {n["slot"]: n["identity"] for n in catalog.get("npcs", [])}
    roles = {slot: slot for slot in npc_slots}
    locations = {n["slot"]: n.get("location", n["slot"]) for n in catalog.get("npcs", [])}
    creatures = {x["slot"]: x["id"] for x in catalog.get("creature_spawns", [])}
    bosses = {x["slot"]: x["id"] for x in catalog.get("boss_spawns", [])}
    if modules.get("npc_identity", False):
        identity = _identity_shuffle(catalog, SeedRng(seed, "npc.identity"))
    if modules.get("npc_roles", False):
        roles = _role_shuffle(catalog, SeedRng(seed, "npc.roles"))
    if modules.get("npc_locations", False):
        locations = _npc_location_shuffle(catalog, SeedRng(seed, "npc.locations"))
    if modules.get("creatures", False):
        creatures = _pick_by_tier(catalog.get("creature_spawns", []), catalog.get("creature_pool", []), SeedRng(seed, "creatures"))
    if modules.get("bosses", False):
        bosses = _pick_by_tier(catalog.get("boss_spawns", []), catalog.get("boss_pool", []), SeedRng(seed, "bosses"))
    portals, portal_checks = _portal_shuffle(catalog, SeedRng(seed, "portals"), modules.get("portals", False))
    result = {
        "schema": MANIFEST_SCHEMA, "engine_version": ENGINE_VERSION, "seed": seed,
        "catalog_sha256": fingerprint(catalog), "settings_sha256": fingerprint(settings),
        "modules": modules,
        "spells": {"mode": spell_mode, "starting_count": int(settings.get("starting_spells", 3)),
                   "level_step": int(settings.get("levels_per_spell", 3)),
                   "max_starter_pips": int(settings.get("max_starter_pips", 2))},
        "npc_identity": identity, "npc_roles": roles, "npc_locations": locations,
        "creatures": creatures, "bosses": bosses,
        "rewards": _reward_shuffle(catalog, modules, seed), "portals": portals,
        "checks": {"portals": portal_checks, "quest_progression": "not validated (game integration required)",
                   "npc_role_quest_links": "not validated (game integration required)",
                   "client_appearances": "not validated (game integration required)"},
    }
    if result["spells"]["starting_count"] < 1 or result["spells"]["level_step"] < 1:
        raise RandomizerError("starting_spells and levels_per_spell must be positive")
    result["manifest_sha256"] = fingerprint(result)
    return result
