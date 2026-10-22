"""Provenance-bound live catalog curation checks."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from randomizer.core import RandomizerError, generate_manifest
from randomizer.curation import curate_spiraldb
from randomizer.spiraldb import import_spiraldb
from tests.test_spiraldb import SpiralDbImporterTests


class CurationTests(SpiralDbImporterTests):
    def setUp(self):
        super().setUp()
        # Existing fixture drop table is a source reference, not proof of functionality.
        self.cat, _ = import_spiraldb(self.root)
        self.base = {'spiraldb_sha256': self.cat['source_metadata']['source_sha256'],
                     'client_build': 'test-client', 'imlight_revision': 'test-revision'}

    def _spell(self):
        return {'id': '1649942288', 'school': 'fire', 'pips': 1, 'min_level': 1,
                'tags': ['attack'], 'client_verified': True, 'cast_verified': True}

    def test_verified_spell_usable_in_generated_manifest(self):
        approvals = {**self.base, 'spells': [self._spell()]}
        result, report = curate_spiraldb(self.cat, approvals)
        self.assertEqual(result['spells'][0]['id'], '1649942288')
        self.assertEqual(report['counts']['approved_spells'], 1)
        self.assertFalse(result['source_metadata']['game_integration_verified'])
        man = generate_manifest(result, {'seed': 'W101', 'modules': {'spells': 'wildcard'}})
        self.assertEqual(man['spells']['mode'], 'wildcard')

    def test_wrong_source_or_unknown_spell_rejected(self):
        with self.assertRaisesRegex(RandomizerError, 'fingerprint'):
            curate_spiraldb(self.cat, {**self.base, 'spiraldb_sha256': 'different'})
        bad = self._spell()
        bad['id'] = '9999999'
        with self.assertRaisesRegex(RandomizerError, 'absent from SpiralDB'):
            curate_spiraldb(self.cat, {**self.base, 'spells': [bad]})
        bad['id'] = '1649942288'
        bad['cast_verified'] = False
        with self.assertRaisesRegex(RandomizerError, 'cast_verified'):
            curate_spiraldb(self.cat, {**self.base, 'spells': [bad]})

    def test_quest_reward_source_membership(self):
        approvals = {**self.base, 'reward_items': [
            {'id': '1248063', 'pool': 'gear', 'min_level': 1,
             'client_verified': True, 'grant_verified': True}],
            'quest_rewards': [{'quest': 'WC-COMMONS-MAIN-001', 'item': '1248063',
                               'quest_grant_verified': True}]}
        out, report = curate_spiraldb(self.cat, approvals)
        self.assertEqual(out['reward_checks'][0]['id'], 'quest:WC-COMMONS-MAIN-001')
        self.assertEqual(out['reward_pool'][0]['id'], '1248063')
        self.assertEqual(report['counts']['approved_quest_rewards'], 1)
        bad = copy.deepcopy(approvals)
        bad['quest_rewards'][0]['quest'] = 'WC-STORY-MAIN-002'
        with self.assertRaisesRegex(RandomizerError, 'not present in quest'):
            curate_spiraldb(self.cat, bad)

    def test_npc_appearance_does_not_unlock_quest_or_location_swaps(self):
        slot = self.cat['npcs'][0]['slot']
        approvals = {**self.base, 'npc_visuals': [
            {'slot': slot, 'template_id': '39088', 'group': 'human',
             'spawn_verified': True, 'client_verified': True, 'services_verified': True}]}
        result, _ = curate_spiraldb(self.cat, approvals)
        npc = result['npcs'][0]
        self.assertFalse(npc['identity_protected'])
        self.assertTrue(npc['roles_protected'])
        self.assertTrue(npc['location_protected'])
        self.assertEqual(npc['identity'], 'npcvisual:39088')
        result['spells'] = [{'id': '1649942288', 'school': 'fire', 'pips': 1,
                              'min_level': 1, 'tags': ['attack'], 'supported': True}]
        m = generate_manifest(result, {'seed': 'abc', 'modules': {
            'npc_identity': True, 'npc_roles': True, 'npc_locations': True}})
        self.assertEqual(m['npc_roles'][slot], slot)
        self.assertEqual(m['npc_locations'][slot], slot)

    def test_portal_requires_exact_verified_trigger_and_return(self):
        first = self.cat['portals'][0]['id']
        with self.assertRaisesRegex(RandomizerError, 'return_path_verified'):
            curate_spiraldb(self.cat, {**self.base, 'portal_triggers': [
                {'id': first, 'transition_verified': True}]})
        result, report = curate_spiraldb(self.cat, {**self.base, 'portal_triggers': [
            {'id': first, 'transition_verified': True, 'return_path_verified': True}]})
        self.assertFalse(next(p for p in result['portals'] if p['id'] == first)['protected'])
        self.assertEqual(report['counts']['approved_portals'], 1)

    def test_duplicate_approvals_rejected(self):
        row = self._spell()
        with self.assertRaisesRegex(RandomizerError, 'duplicate spells'):
            curate_spiraldb(self.cat, {**self.base, 'spells': [row, row]})

    def test_spiraldb_portals_cannot_shuffle_unvalidated_zone_subset(self):
        result, _ = curate_spiraldb(self.cat, {**self.base, 'spells': [self._spell()]})
        with self.assertRaisesRegex(RandomizerError, 'validated full-zone scope'):
            generate_manifest(result, {'seed': 'abc', 'modules': {'portals': True}})

    def test_cli_generation_from_approved_local_data(self):
        from randomizer.spiral_cli import main
        approvals = {**self.base, 'spells': [self._spell()]}
        folder = self.root / 'results'
        folder.mkdir()
        (folder / 'approve.json').write_text(json.dumps(approvals))
        (folder / 'settings.json').write_text(json.dumps({'seed': 'seed-123', 'modules': {'spells': 'wildcard'}}))
        rc = main(['--spiraldb', str(self.root), '--out', str(folder / 'catalog.json'),
                   '--report', str(folder / 'report.json'), '--curation', str(folder / 'approve.json'),
                   '--settings', str(folder / 'settings.json'), '--manifest', str(folder / 'manifest.json')])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((folder / 'manifest.json').read_text())['seed'], 'seed-123')


if __name__ == '__main__':
    unittest.main()
