import copy
import json
import unittest
from pathlib import Path
from randomizer.core import generate_manifest, RandomizerError
from randomizer.logic import check_story_logic

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'config/example_catalog.json').read_text())
SETTINGS = json.loads((ROOT / 'config/example_settings.json').read_text())


def sample_logic():
    return {
        'starting_flags': [],
        'portal_rules': {'commons-to-olde': ['spoke_to_mentor']},
        'goals': [
            {'id': 'mentor', 'npc_slot': 'story-mentor', 'grants': ['spoke_to_mentor']},
            {'id': 'town', 'npc_slot': 'town-a', 'requires': ['spoke_to_mentor'],
             'grants': ['spoke_to_town']},
            {'id': 'last', 'npc_slot': 'town-d', 'requires': ['spoke_to_town'],
             'grants': ['story_finished']},
        ],
        'required_goals': ['mentor', 'town', 'last'],
        'victory_flags': ['story_finished']
    }


class StoryLogicTests(unittest.TestCase):
    def test_explicit_story_can_complete(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['story_logic'] = sample_logic()
        manifest = generate_manifest(catalog, SETTINGS)
        self.assertTrue(manifest['checks']['story_logic']['ok'])
        self.assertGreaterEqual(len(manifest['checks']['story_logic']['spheres']), 2)

    def test_full_chaos_quest_logic_and_portals(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['story_logic'] = sample_logic()
        settings = copy.deepcopy(SETTINGS)
        settings['modules']['portals'] = True
        manifest = generate_manifest(catalog, settings)
        self.assertTrue(manifest['checks']['portals']['shuffled'])
        self.assertTrue(manifest['checks']['story_logic']['ok'])

    def test_impossible_story_is_rejected(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['story_logic'] = sample_logic()
        catalog['story_logic']['goals'][0]['requires'] = ['story_finished']
        with self.assertRaisesRegex(RandomizerError, 'story progression blocked'):
            generate_manifest(catalog, SETTINGS)

    def test_missing_story_is_reported_unverified(self):
        catalog = copy.deepcopy(CATALOG)
        del catalog['story_logic']
        result = generate_manifest(catalog, SETTINGS)
        self.assertIsNone(result['checks']['story_logic']['ok'])

    def test_missing_npc_is_rejected(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['story_logic'] = sample_logic()
        catalog['story_logic']['goals'][0]['npc_slot'] = 'no-one'
        with self.assertRaises(RandomizerError):
            generate_manifest(catalog, SETTINGS)

    def test_portal_missing_critical_zone_is_rejected(self):
        catalog = copy.deepcopy(CATALOG)
        catalog['story_logic'] = sample_logic()
        # All routes to Unicorn Way become gated by the victory flag that needs its NPC.
        catalog['story_logic']['portal_rules']['commons-to-unicorn'] = ['story_finished']
        with self.assertRaises(RandomizerError):
            generate_manifest(catalog, SETTINGS)


if __name__ == '__main__':
    unittest.main()
