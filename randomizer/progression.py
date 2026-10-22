"""Persistable per-character Wildcard / Draft progression planner."""
from __future__ import annotations
from .core import RandomizerError, SeedRng


class SpellProgression:
    def __init__(self, catalog: dict, manifest: dict, state: dict | None = None):
        self.catalog, self.manifest = catalog, manifest
        self.state = state if state is not None else {"manifest_sha256": manifest["manifest_sha256"], "characters": {}}
        if self.state.get("manifest_sha256") != manifest["manifest_sha256"]:
            raise RandomizerError("character saves belong to a different seed/catalog/settings manifest")
        self.state.setdefault("characters", {})

    def _pool(self, level: int, known: list[str]) -> list[dict]:
        # Placeholder cross-school policy: do not grant very expensive spells too early.
        max_pips = min(8, 1 + level // 4)
        return sorted([spell for spell in self.catalog.get("spells", [])
                       if spell.get("supported", False) and spell["id"] not in known
                       and int(spell.get("min_level", 1)) <= level
                       and int(spell.get("pips", 99)) <= max_pips], key=lambda x: x["id"])

    def create_character(self, character_id: str) -> dict:
        characters = self.state["characters"]
        if character_id in characters:
            return characters[character_id]
        mode = self.manifest["spells"]["mode"]
        if mode == "vanilla":
            raise RandomizerError("vanilla spell mode does not create randomized characters")
        eligible = self._pool(1, [])
        max_starter_pips = self.manifest["spells"]["max_starter_pips"]
        attacks = [x for x in eligible if "attack" in x.get("tags", []) and x["pips"] <= max_starter_pips]
        if not attacks:
            raise RandomizerError("no safe usable starting attack")
        rng = SeedRng(self.manifest["seed"], f"spells.character:{character_id}:start")
        first = rng.choice(attacks)["id"]
        picks = [first]
        while len(picks) < self.manifest["spells"]["starting_count"]:
            candidates = [x for x in eligible if x["id"] not in picks]
            if not candidates:
                raise RandomizerError("not enough validated starter spells")
            picks.append(rng.choice(candidates)["id"])
        character = {"level": 1, "spells": picks, "locked": [first], "reroll_tokens": 0,
                     "reroll_count": 0, "milestones": {}, "pending_drafts": {}, "history": [{"type": "starter", "spells": picks[:]}]}
        characters[character_id] = character
        return character

    def level_to(self, character_id: str, new_level: int) -> dict:
        c = self.create_character(character_id)
        if new_level < c["level"]:
            raise RandomizerError("cannot decrease level via progression planner")
        step = self.manifest["spells"]["level_step"]
        mode = self.manifest["spells"]["mode"]
        for lvl in range(c["level"] + 1, new_level + 1):
            if (lvl - 1) % step != 0:
                continue
            key = str(lvl)
            if key in c["milestones"]:
                continue
            rng = SeedRng(self.manifest["seed"], f"spells.character:{character_id}:level:{lvl}")
            pool = self._pool(lvl, c["spells"])
            if mode == "wildcard":
                if pool:
                    spell = rng.choice(pool)["id"]
                    c["spells"].append(spell)
                    c["milestones"][key] = {"granted": spell}
                    c["history"].append({"type": "milestone", "level": lvl, "spell": spell})
                else:
                    c["milestones"][key] = {"granted": None, "reason": "pool_empty"}
            elif mode == "draft":
                options = [x["id"] for x in rng.shuffle(pool)[:3]]
                if len(options) != 3:
                    # Explicitly track missing pool instead of quietly granting a duplicate.
                    c["milestones"][key] = {"granted": None, "reason": "draft_pool_too_small"}
                else:
                    c["pending_drafts"][key] = options
                    c["milestones"][key] = {"draft": options}
        c["level"] = new_level
        return c

    def choose_draft(self, character_id: str, level: int, spell_id: str) -> dict:
        c = self.create_character(character_id)
        key = str(level)
        choices = c["pending_drafts"].get(key)
        if choices is None or spell_id not in choices:
            raise RandomizerError("spell is not in a pending draft at this level")
        if spell_id in c["spells"]:
            raise RandomizerError("spell already learned (resolve earlier draft first)")
        c["spells"].append(spell_id)
        c["milestones"][key] = {"draft": choices, "chosen": spell_id}
        del c["pending_drafts"][key]
        c["history"].append({"type": "draft_choice", "level": level, "spell": spell_id})
        return c

    def grant_tokens(self, character_id: str, count: int, event_id: str) -> dict:
        c = self.create_character(character_id)
        if count <= 0 or not event_id:
            raise RandomizerError("token grant must be positive and identified")
        if any(e.get("type") == "token_grant" and e.get("event_id") == event_id for e in c["history"]):
            return c
        c["reroll_tokens"] += count
        c["history"].append({"type": "token_grant", "count": count, "event_id": event_id})
        return c

    def lock_spell(self, character_id: str, spell_id: str) -> dict:
        c = self.create_character(character_id)
        if spell_id not in c["spells"]:
            raise RandomizerError("cannot lock unknown spell")
        c["locked"] = [spell_id]
        return c

    def reroll(self, character_id: str, spell_id: str) -> dict:
        c = self.create_character(character_id)
        if c["reroll_tokens"] < 1:
            raise RandomizerError("no reroll tokens")
        if spell_id not in c["spells"] or spell_id in c["locked"]:
            raise RandomizerError("spell is unknown or locked")
        attack_ids = {s["id"] for s in self.catalog["spells"] if "attack" in s.get("tags", [])}
        if spell_id in attack_ids and not any(s != spell_id and s in attack_ids for s in c["spells"]):
            raise RandomizerError("cannot reroll the only attack")
        pool = self._pool(c["level"], c["spells"])
        if not pool:
            raise RandomizerError("no suitable replacement")
        rng = SeedRng(self.manifest["seed"], f"spells.character:{character_id}:reroll:{c['reroll_count']}")
        replacement = rng.choice(pool)["id"]
        # Local state update is atomic as one operation; file transaction is CLI's responsibility.
        c["spells"][c["spells"].index(spell_id)] = replacement
        c["reroll_tokens"] -= 1
        c["reroll_count"] += 1
        c["history"].append({"type": "reroll", "before": spell_id, "after": replacement})
        return c
