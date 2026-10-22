"""Offline reachability and talk-to NPC progression checks using explicit logic data.

This models quest/portal conditions only when the catalog supplies them. It cannot
infer quests from the live game and does NOT substitute for end-to-end game tests.
"""
from __future__ import annotations

from collections import deque

from .core import RandomizerError


def _zones_reachable(start: str, portals: list[dict], mapping: dict,
                     gate_rules: dict[str, list[str]], flags: set[str]) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for portal in portals:
        if set(gate_rules.get(portal['id'], [])).issubset(flags):
            adjacency.setdefault(portal['source'], []).append(mapping[portal['id']])
    seen = {start}
    todo = deque([start])
    while todo:
        for dest in adjacency.get(todo.popleft(), []):
            if dest not in seen:
                seen.add(dest)
                todo.append(dest)
    return seen


def check_story_logic(catalog: dict, npc_roles: dict[str, str],
                      portals: dict[str, str]) -> dict:
    """Prove modeled objectives reachable by fixed-point logic spheres.

    Catalog optional `story_logic` example:
    {"starting_flags": [],
     "portal_rules": {"portal-id": ["talked:someone"]},
     "goals": [{"id":"g1", "npc_slot":"npc-a", "requires":[],
                "grants":["talked:someone"]}],
     "required_goals": ["g1"], "victory_flags": ["talked:someone"]}

    Every flag is monotone; no negative prerequisites and no hidden logic.
    """
    logic = catalog.get('story_logic')
    if logic is None:
        return {'modeled': False, 'ok': None,
                'note': 'no quest dependency graph provided; gameplay progression unverified'}
    npcs = {n['slot']: n for n in catalog.get('npcs', [])}
    known_portals = {e['id'] for e in catalog.get('portals', [])}
    gates = logic.get('portal_rules', {})
    if not isinstance(gates, dict) or any(p not in known_portals for p in gates):
        raise RandomizerError('story_logic references unknown portal id')
    for portal_id, rules in gates.items():
        if not isinstance(rules, list) or not all(isinstance(k, str) for k in rules):
            raise RandomizerError(f'invalid rules for {portal_id}')
    goals = logic.get('goals', [])
    if not isinstance(goals, list):
        raise RandomizerError('story_logic.goals must be a list')
    names: set[str] = set()
    for goal in goals:
        gid = goal.get('id')
        if not isinstance(gid, str) or not gid or gid in names:
            raise RandomizerError('story_logic goal id missing or duplicated')
        names.add(gid)
        if goal.get('npc_slot') not in npcs:
            raise RandomizerError(f'{gid} references missing NPC slot')
        if not isinstance(goal.get('requires', []), list) or not isinstance(goal.get('grants', []), list):
            raise RandomizerError(f'{gid} must use requires/grants lists')
    required = set(logic.get('required_goals', []))
    if not required.issubset(names):
        raise RandomizerError('story_logic required_goals includes unknown goal')
    start = catalog['start_zone']
    flags = set(logic.get('starting_flags', []))
    reached_goals: set[str] = set()
    spheres: list[dict] = []
    zones: set[str] = set()
    for step in range(len(goals) + len(catalog.get('zones', [])) + 2):
        new_zones = _zones_reachable(start, catalog['portals'], portals, gates, flags)
        obtained = []
        for goal in sorted(goals, key=lambda x: x['id']):
            if goal['id'] in reached_goals or not set(goal.get('requires', [])).issubset(flags):
                continue
            # NPC role assignment determines who fulfills the original talk-to role.
            target_slot = npc_roles.get(goal['npc_slot'])
            if target_slot not in npcs:
                raise RandomizerError(f'unresolvable NPC quest role: {goal["id"]}')
            if npcs[target_slot]['zone'] in new_zones:
                reached_goals.add(goal['id'])
                flags.update(goal.get('grants', []))
                obtained.append(goal['id'])
        if obtained or new_zones != zones:
            spheres.append({'sphere': step, 'zones': sorted(new_zones), 'completed_goals': obtained})
            zones = new_zones
            continue
        break
    missing_goals = sorted(required - reached_goals)
    missing_flags = sorted(set(logic.get('victory_flags', [])) - flags)
    missing_zones = sorted(set(catalog.get('required_zones', [])) - zones)
    return {'modeled': True, 'ok': not (missing_goals or missing_flags or missing_zones),
            'missing_goals': missing_goals, 'missing_flags': missing_flags,
            'missing_zones': missing_zones, 'spheres': spheres}
