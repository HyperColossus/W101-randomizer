"""Deterministic, persistable per-character ability progression rules.

No Imlight calls or database writes happen here. Runtime commits state changes and
an outbox in one transaction; the game adapter must apply and acknowledge them.
"""
from __future__ import annotations

from .core import RandomizerError, SeedRng


class SpellProgression:
    def __init__(self, catalog: dict, manifest: dict, state: dict | None = None):
        self.catalog, self.manifest = catalog, manifest
        self.spell_index = {str(x['id']): x for x in catalog.get('spells', [])}
        self.state = state if state is not None else {
            'manifest_sha256': manifest['manifest_sha256'], 'characters': {}
        }
        if self.state.get('manifest_sha256') != manifest['manifest_sha256']:
            raise RandomizerError('character saves belong to a different manifest')
        self.state.setdefault('characters', {})

    def _rng(self, character_id: str, context: str, prestige: int = 0) -> SeedRng:
        return SeedRng(self.manifest['seed'],
                       f'spells.character:{character_id}:prestige:{prestige}:{context}')

    def _pool(self, level: int, known: list[str]) -> list[dict]:
        # Actual in-game cross-school power-pip support still requires validation.
        max_pips = min(8, 1 + level // 4)
        return sorted((s for s in self.catalog.get('spells', [])
                       if s.get('supported', False) and s['id'] not in known
                       and int(s.get('min_level', 1)) <= level
                       and int(s.get('pips', 99)) <= max_pips), key=lambda s: s['id'])

    def _weighted_choice(self, rng: SeedRng, candidates: list[dict], known: list[str]) -> str:
        """Small synergy bonus for shared schools; never violates eligibility."""
        if not candidates:
            raise RandomizerError('no eligible spells')
        learned_schools = {self.spell_index[s].get('school') for s in known if s in self.spell_index}
        factor = int(self.manifest['spells'].get('synergy_bonus', 0))
        if not 0 <= factor <= 10:
            raise RandomizerError('synergy_bonus must be 0..10')
        weights = [1 + (factor if s.get('school') in learned_schools else 0) for s in candidates]
        index = rng.below(sum(weights))
        for spell, weight in zip(candidates, weights):
            if index < weight:
                return str(spell['id'])
            index -= weight
        raise AssertionError('weighted roll overflow')

    def _starting_spells(self, character_id: str, prestige: int) -> tuple[list[str], str]:
        eligible = self._pool(1, [])
        starter_pips = int(self.manifest['spells']['max_starter_pips'])
        attacks = [s for s in eligible if 'attack' in s.get('tags', [])
                   and int(s['pips']) <= starter_pips]
        if not attacks:
            raise RandomizerError('no safe usable starting attack')
        rng = self._rng(character_id, 'start', prestige)
        first = rng.choice(attacks)['id']
        selected = [first]
        while len(selected) < int(self.manifest['spells']['starting_count']):
            pool = [s for s in eligible if s['id'] not in selected]
            if not pool:
                raise RandomizerError('not enough validated starter spells')
            selected.append(self._weighted_choice(rng, pool, selected))
        return selected, first

    def create_character(self, character_id: str) -> dict:
        if not character_id or len(character_id) > 128:
            raise RandomizerError('invalid character identifier')
        characters = self.state['characters']
        if character_id in characters:
            return characters[character_id]
        mode = self.manifest['spells']['mode']
        if mode == 'vanilla':
            raise RandomizerError('vanilla spell mode does not randomize spells')
        selected, attack = self._starting_spells(character_id, 0)
        c = {'level': 1, 'spells': selected, 'locked': [attack],
             'reroll_tokens': 0, 'reroll_count': 0, 'milestones': {},
             'pending_drafts': {}, 'skill_cards': [], 'equipped_skill_card': None,
             'prestige': 0, 'prestige_history': [], 'history': [
                 {'type': 'starter', 'spells': selected[:], 'prestige': 0}
             ]}
        characters[character_id] = c
        return c

    def _queue_next_draft(self, character_id: str, c: dict) -> None:
        """Queue only one unresolved draft at a time; prevent duplicate offers."""
        if c['pending_drafts']:
            return
        step = int(self.manifest['spells']['level_step'])
        for level in range(1 + step, c['level'] + 1, step):
            key = str(level)
            if key in c['milestones']:
                continue
            rng = self._rng(character_id, f'level:{level}', c.get('prestige', 0))
            pool = self._pool(level, c['spells'])
            card = c.get('equipped_skill_card')
            eligible_card = next((s for s in pool if s['id'] == card), None)
            if eligible_card is not None:
                selected = [card] + [s['id'] for s in rng.shuffle(pool)
                                     if s['id'] != card][:2]
            else:
                selected = [s['id'] for s in rng.shuffle(pool)[:3]]
            if len(selected) < 3:
                c['milestones'][key] = {'granted': None, 'reason': 'draft_pool_too_small'}
            else:
                c['pending_drafts'][key] = selected
                c['milestones'][key] = {'draft': selected[:],
                                        'guaranteed': card if eligible_card else None}
                return

    def level_to(self, character_id: str, new_level: int) -> dict:
        c = self.create_character(character_id)
        cap = int(self.manifest['spells'].get('max_level', 170))
        if not isinstance(new_level, int) or not c['level'] <= new_level <= cap:
            raise RandomizerError('level must be nondecreasing and within the configured cap')
        step = int(self.manifest['spells']['level_step'])
        mode = self.manifest['spells']['mode']
        if mode == 'draft':
            c['level'] = new_level
            self._queue_next_draft(character_id, c)
            return c
        for level in range(c['level'] + 1, new_level + 1):
            if (level - 1) % step != 0:
                continue
            key = str(level)
            if key in c['milestones']:
                continue
            rng = self._rng(character_id, f'level:{level}', c.get('prestige', 0))
            pool = self._pool(level, c['spells'])
            card = c.get('equipped_skill_card')
            eligible_card = next((s for s in pool if s['id'] == card), None)
            if eligible_card is not None:
                picked = eligible_card['id']
                c['equipped_skill_card'] = None
                c['skill_cards'].remove(card)
            elif pool:
                picked = self._weighted_choice(rng, pool, c['spells'])
            else:
                picked = None
            if picked is not None:
                c['spells'].append(picked)
                c['milestones'][key] = {'granted': picked}
                c['history'].append({'type': 'milestone', 'level': level, 'spell': picked})
            else:
                c['milestones'][key] = {'granted': None, 'reason': 'pool_empty'}
        c['level'] = new_level
        return c

    def choose_draft(self, character_id: str, level: int, spell_id: str) -> dict:
        c = self.create_character(character_id)
        key = str(level)
        choices = c['pending_drafts'].get(key)
        if choices is None or spell_id not in choices:
            raise RandomizerError('spell is not offered in this pending draft')
        if spell_id in c['spells']:
            raise RandomizerError('spell already learned')
        reserved = c['milestones'][key].get('guaranteed')
        if reserved is not None and spell_id != reserved:
            raise RandomizerError('guaranteed skill card requires selecting its spell')
        c['spells'].append(spell_id)
        c['milestones'][key] = {'draft': choices[:], 'chosen': spell_id}
        del c['pending_drafts'][key]
        if reserved is not None:
            c['skill_cards'].remove(reserved)
            c['equipped_skill_card'] = None
        c['history'].append({'type': 'draft_choice', 'level': level, 'spell': spell_id})
        self._queue_next_draft(character_id, c)
        return c

    def grant_tokens(self, character_id: str, count: int, event_id: str) -> dict:
        c = self.create_character(character_id)
        if not isinstance(count, int) or count <= 0 or count > 100 or not event_id:
            raise RandomizerError('token grant must be positive, bounded and identified')
        if any(e.get('type') == 'token_grant' and e.get('event_id') == event_id for e in c['history']):
            return c
        c['reroll_tokens'] += count
        c['history'].append({'type': 'token_grant', 'count': count, 'event_id': event_id})
        return c

    def lock_spell(self, character_id: str, spell_id: str) -> dict:
        c = self.create_character(character_id)
        if spell_id not in c['spells']:
            raise RandomizerError('cannot lock unknown spell')
        c['locked'] = [spell_id]
        return c

    def reroll(self, character_id: str, spell_id: str) -> dict:
        c = self.create_character(character_id)
        if c['reroll_tokens'] < 1:
            raise RandomizerError('no reroll tokens')
        if spell_id not in c['spells'] or spell_id in c['locked']:
            raise RandomizerError('spell is unknown or locked')
        attacks = {s['id'] for s in self.catalog['spells'] if 'attack' in s.get('tags', [])}
        if spell_id in attacks and not any(s in attacks and s != spell_id for s in c['spells']):
            raise RandomizerError('cannot reroll the only attack')
        pool = self._pool(c['level'], c['spells'])
        if not pool:
            raise RandomizerError('no suitable replacement')
        rng = self._rng(character_id, f'reroll:{c["reroll_count"]}', c.get('prestige', 0))
        replacement = self._weighted_choice(rng, pool, c['spells'])
        c['spells'][c['spells'].index(spell_id)] = replacement
        c['reroll_tokens'] -= 1
        c['reroll_count'] += 1
        c['history'].append({'type': 'reroll', 'before': spell_id, 'after': replacement})
        return c

    def grant_skill_card(self, character_id: str, spell_id: str, event_id: str) -> dict:
        c = self.create_character(character_id)
        spell = self.spell_index.get(spell_id)
        if not spell or not spell.get('supported'):
            raise RandomizerError('unsupported skill card spell')
        if not event_id:
            raise RandomizerError('skill card grant needs event id')
        if any(e.get('type') == 'skill_card_grant' and e.get('event_id') == event_id
               for e in c['history']):
            return c
        if spell_id in c['spells']:
            raise RandomizerError('cannot reserve a known spell')
        if spell_id not in c['skill_cards']:
            c['skill_cards'].append(spell_id)
        c['history'].append({'type': 'skill_card_grant', 'spell': spell_id, 'event_id': event_id})
        return c

    def equip_skill_card(self, character_id: str, spell_id: str) -> dict:
        c = self.create_character(character_id)
        if spell_id not in c['skill_cards'] or spell_id in c['spells']:
            raise RandomizerError('skill card must be owned and spell not yet learned')
        c['equipped_skill_card'] = spell_id
        return c

    def prestige(self, character_id: str, event_id: str) -> dict:
        c = self.create_character(character_id)
        if not event_id:
            raise RandomizerError('prestige needs event id')
        if any(e.get('type') == 'prestige' and e.get('event_id') == event_id
               for e in c['history']):
            return c
        if c['level'] < self.manifest['spells'].get('max_level', 170):
            raise RandomizerError('prestige requires configured level cap')
        if c['pending_drafts']:
            raise RandomizerError('resolve drafts before prestige')
        prev = {'prestige': c.get('prestige', 0), 'level': c['level'], 'spells': c['spells'][:]}
        c['prestige_history'].append(prev)
        c['prestige'] = c.get('prestige', 0) + 1
        new_spells, attack = self._starting_spells(character_id, c['prestige'])
        c.update({'level': 1, 'spells': new_spells, 'locked': [attack],
                  'reroll_tokens': 0, 'reroll_count': 0, 'milestones': {},
                  'pending_drafts': {}, 'equipped_skill_card': None})
        # The account's skill card collection survives prestige, but the equipped card resets.
        c['history'].append({'type': 'prestige', 'event_id': event_id, 'new_prestige': c['prestige'],
                             'spells': new_spells[:]})
        return c
