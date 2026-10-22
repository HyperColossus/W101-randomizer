import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from randomizer.api import make_server
from randomizer.core import RandomizerError, generate_manifest
from randomizer.progression import SpellProgression
from randomizer.runtime import RunStore

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'config/example_catalog.json').read_text())
SETTINGS = json.loads((ROOT / 'config/example_settings.json').read_text())


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = generate_manifest(CATALOG, SETTINGS)
        self.path = Path(self.temp.name) / 'run.sqlite3'
        self.store = RunStore(self.path, CATALOG, self.manifest)

    def test_persistent_rolls_and_idempotent_replay(self):
        first = self.store.perform('one', 'start', 'start-one')
        again = self.store.perform('one', 'start', 'start-one')
        self.assertEqual(first, again)
        self.assertEqual(len(self.store.pending('one')), 3)
        reopened = RunStore(self.path, CATALOG, self.manifest)
        self.assertEqual(first['character'], reopened.get_character('one'))
        self.assertEqual(len(reopened.pending('one')), 3)

    def test_command_cannot_be_replayed_with_changed_payload_or_actor(self):
        self.store.perform('one', 'level', 'xp-event', {'level': 4})
        with self.assertRaises(RandomizerError):
            self.store.perform('one', 'level', 'xp-event', {'level': 7})
        with self.assertRaises(RandomizerError):
            self.store.perform('two', 'level', 'xp-event', {'level': 4})

    def test_level_up_only_emits_new_spells_once(self):
        self.store.perform('one', 'start', 'start')
        self.store.perform('one', 'level', 'xp', {'level': 10})
        self.store.perform('one', 'level', 'xp', {'level': 10})
        self.assertEqual(len(self.store.pending('one')), 6)
        self.store.perform('one', 'level', 'noop', {'level': 10})
        self.assertEqual(len(self.store.pending('one')), 6)

    def test_claim_is_first_clear_even_under_new_request_id(self):
        a = self.store.perform('one', 'claim', 'claim-first', {'check_id': 'quest-01'})
        b = self.store.perform('one', 'claim', 'claim-another', {'check_id': 'quest-01'})
        self.assertTrue(a['new_claim'])
        self.assertFalse(b['new_claim'])
        self.assertEqual(a['reward_id'], b['reward_id'])
        self.assertEqual(len(self.store.pending('one')), 1)

    def test_farmable_mob_requires_distinct_encounter_ids(self):
        with self.assertRaises(RandomizerError):
            self.store.perform('one', 'claim', 'bad', {'check_id': 'mob-01'})
        a = self.store.perform('one', 'claim', 'fight1', {'check_id': 'mob-01', 'encounter_id': 'fight-1'})
        b = self.store.perform('one', 'claim', 'fight2', {'check_id': 'mob-01', 'encounter_id': 'fight-1'})
        c = self.store.perform('one', 'claim', 'fight3', {'check_id': 'mob-01', 'encounter_id': 'fight-2'})
        self.assertTrue(a['new_claim'])
        self.assertFalse(b['new_claim'])
        self.assertTrue(c['new_claim'])
        self.assertEqual(len(self.store.pending('one')), 2)

    def test_failed_transaction_does_not_write_command_or_character(self):
        with self.assertRaises((KeyError, RandomizerError)):
            self.store.perform('one', 'level', 'bad', {'level': -10})
        self.assertIsNone(self.store.get_character('one'))
        self.assertEqual(self.store.status()['pending_events'], 0)
        self.store.perform('one', 'start', 'bad')  # identical request_id allowed after rollback

    def test_ack_is_idempotent_and_character_scoped(self):
        self.store.perform('one', 'start', 's1')
        event = self.store.pending('one')[0]
        with self.assertRaises(RandomizerError):
            self.store.ack('two', event['id'])
        self.assertTrue(self.store.ack('one', event['id']))
        self.assertFalse(self.store.ack('one', event['id']))
        self.assertEqual(len(self.store.pending('one')), 2)

    def test_manifest_change_rejected(self):
        changed = copy.deepcopy(SETTINGS)
        changed['seed'] = 'OTHER'
        other = generate_manifest(CATALOG, changed)
        with self.assertRaises(RandomizerError):
            RunStore(self.path, CATALOG, other)
        tampered = copy.deepcopy(self.manifest)
        tampered['npc_identity']['town-a'] = 'hijacked'
        with self.assertRaises(RandomizerError):
            RunStore(Path(self.temp.name) / 'tampered.db', CATALOG, tampered)

    def test_concurrent_commands_are_serialized(self):
        errors = []
        barrier = threading.Barrier(8)
        def worker():
            try:
                barrier.wait(timeout=5)
                self.store.perform('one', 'claim', 'same-claim', {'check_id': 'quest-01'})
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertFalse(errors, errors)
        self.assertEqual(self.store.status()['claims'], 1)
        self.assertEqual(len(self.store.pending('one')), 1)

    def test_world_lookup_valid_and_invalid(self):
        self.assertEqual(self.store.lookup('npc_roles', 'story-mentor'), 'story-mentor')
        with self.assertRaises(RandomizerError):
            self.store.lookup('unknown', 'x')
        with self.assertRaises(RandomizerError):
            self.store.lookup('creatures', 'absent')

    def test_reboot_preserves_pending_and_claims(self):
        self.store.perform('one', 'claim', 'quest', {'check_id': 'quest-01'})
        restarted = RunStore(self.path, CATALOG, self.manifest)
        self.assertFalse(restarted.perform('one', 'claim', 'quest2', {'check_id': 'quest-01'})['new_claim'])
        self.assertEqual(restarted.status()['pending_events'], 1)


class ExtendedSpellTests(unittest.TestCase):
    def test_skill_card_guarantees_eligible_future_spell(self):
        m = generate_manifest(CATALOG, SETTINGS)
        e = SpellProgression(CATALOG, m)
        c = e.create_character('player')
        selected = next(x['id'] for x in CATALOG['spells'] if x['min_level'] == 4
                        and x['id'] not in c['spells'])
        e.grant_skill_card('player', selected, 'card-drop')
        e.grant_skill_card('player', selected, 'card-drop')
        e.equip_skill_card('player', selected)
        e.level_to('player', 4)
        self.assertIn(selected, c['spells'])
        self.assertNotIn(selected, c['skill_cards'])
        self.assertIsNone(c['equipped_skill_card'])

    def test_draft_level_skip_queues_one_at_a_time(self):
        settings = copy.deepcopy(SETTINGS)
        settings['modules']['spells'] = 'draft'
        m = generate_manifest(CATALOG, settings)
        e = SpellProgression(CATALOG, m)
        c = e.level_to('one', 10)
        self.assertEqual(list(c['pending_drafts']), ['4'])
        self.assertEqual(list(c['milestones']), ['4'])
        spell = c['pending_drafts']['4'][0]
        e.choose_draft('one', 4, spell)
        self.assertNotIn('4', c['pending_drafts'])
        self.assertIn('7', c['milestones'])
        self.assertEqual(list(c['pending_drafts']), ['7'])

    def test_draft_skill_card_requires_reservation(self):
        settings = copy.deepcopy(SETTINGS)
        settings['modules']['spells'] = 'draft'
        m = generate_manifest(CATALOG, settings)
        e = SpellProgression(CATALOG, m)
        c = e.create_character('p')
        selected = next(x['id'] for x in CATALOG['spells'] if x['min_level'] == 4)
        e.grant_skill_card('p', selected, 'd1')
        e.equip_skill_card('p', selected)
        e.level_to('p', 4)
        self.assertEqual(c['pending_drafts']['4'][0], selected)
        with self.assertRaises(RandomizerError):
            e.choose_draft('p', 4, c['pending_drafts']['4'][1])
        e.choose_draft('p', 4, selected)
        self.assertIn(selected, c['spells'])

    def test_prestige_requires_cap_and_uses_new_roll_stream(self):
        settings = copy.deepcopy(SETTINGS)
        settings['max_level'] = 4
        m = generate_manifest(CATALOG, settings)
        e = SpellProgression(CATALOG, m)
        c = e.create_character('p')
        with self.assertRaises(RandomizerError):
            e.prestige('p', 'prestige-1')
        e.level_to('p', 4)
        e.prestige('p', 'prestige-1')
        self.assertEqual(c['level'], 1)
        self.assertEqual(c['prestige'], 1)
        self.assertEqual(len(c['prestige_history']), 1)
        snapshot = copy.deepcopy(c)
        e.prestige('p', 'prestige-1')
        self.assertEqual(c, snapshot)

    def test_invalid_config_values_rejected(self):
        for key, value in [('max_level', -1), ('synergy_bonus', 11),
                           ('starting_spells', 0), ('levels_per_spell', 0)]:
            setting = copy.deepcopy(SETTINGS)
            setting[key] = value
            with self.subTest(key=key), self.assertRaises(RandomizerError):
                generate_manifest(CATALOG, setting)


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        manifest = generate_manifest(CATALOG, SETTINGS)
        store = RunStore(Path(self.temp.name) / 'a.db', CATALOG, manifest)
        self.token = 'test-token-1234567890-long-enough'
        self.server = make_server(store, self.token, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, endpoint, body=None, token=None):
        headers = {'Authorization': 'Bearer ' + (self.token if token is None else token)}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        req = Request(self.base + endpoint, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        with urlopen(req, timeout=4) as resp:
            return json.load(resp)

    def test_auth_and_health(self):
        self.assertTrue(self.request('/v1/health')['ok'])
        with self.assertRaises(HTTPError) as cm:
            self.request('/v1/health', token='incorrect')
        self.assertEqual(cm.exception.code, 401)

    def test_command_events_ack_lookup(self):
        self.request('/v1/commands', {'actor': 'player', 'action': 'start', 'request_id': 'start'})
        events = self.request('/v1/characters/player/pending')['events']
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]['kind'], 'spell.grant')
        self.request('/v1/ack', {'actor': 'player', 'event_id': events[0]['id']})
        self.assertEqual(len(self.request('/v1/characters/player/pending')['events']), 2)
        self.assertEqual(self.request('/v1/world/npc_roles/story-mentor')['result'], 'story-mentor')

    def test_refuses_non_loopback_bind(self):
        manifest = generate_manifest(CATALOG, SETTINGS)
        with tempfile.TemporaryDirectory() as t:
            store = RunStore(Path(t) / 'x.db', CATALOG, manifest)
            with self.assertRaises(RandomizerError):
                make_server(store, self.token, host='0.0.0.0', port=0)


if __name__ == '__main__':
    unittest.main()
