"""Tests use minimal records shaped exactly like the real SpiralDB JSON sources."""
import json
import tempfile
import unittest
from pathlib import Path
from randomizer.core import RandomizerError, generate_manifest
from randomizer.spiraldb import import_spiraldb


class SpiralDbImporterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self._write('ZoneTransfer/WizardZoneDatas_1-A.json', {
            'ZoneName': 'WizardCity/WC_Hub',
            'Teleports': [
                {'TriggerName': 'Trigger TelepotToUW', 'Teleport': {
                    'm_destinationZone': 'WizardCity/WC_Streets/WC_Unicorn',
                    'm_destinationLoc': '-87.5,-533.3,18.5,3.0'}},
                {'TriggerName': 'Trigger TelepotToUW (1)', 'Teleport': {
                    'm_destinationZone': 'WizardCity/WC_Streets/WC_Unicorn'}}],
            'Events': []})
        self._write('ZoneTransfer/WizardZoneDatas_2-A.json', {
            'ZoneName': 'WizardCity/WC_Streets/WC_Unicorn',
            'Teleports': [{'TriggerName': 'Back', 'Teleport': {
                'm_destinationZone': 'WizardCity/WC_Hub'}}]})
        self._write('QuestTemplates/questtemplates_WC-COMMONS-MAIN-001.json', {
            'm_questName': 'WC-COMMONS-MAIN-001', 'm_questTitle': 'QuestTitle_1625BF',
            'm_questLevel': 1, 'm_mainline': True,
            'm_startGoals': ['Explore'], 'm_goals': [
                {'$type': 'WaypointGoalTemplate', 'm_goalName': 'Explore',
                 'm_destinationZone': 'WizardCity/WC_Streets/WC_Unicorn'},
                {'$type': 'PersonaGoalTemplate', 'm_goalType': 'GOAL_TYPE_PERSONA',
                 'm_goalName': 'Talk', 'm_personaName': 'WC-ST01-NPC04',
                 'm_destinationZone': 'WizardCity/WC_Streets/WC_Unicorn'}],
            'm_goalLogic': [{'m_goalsAND': ['Explore'], 'm_goalsToAdd': ['Talk'],
                            'm_completeQuest': False},
                           {'m_goalsAND': ['Talk'], 'm_goalsToAdd': [],
                            'm_completeQuest': True}],
            'm_endResults': {'m_results': [{'$type': 'Imcodec.ResDropTable',
                                            'm_tableName': 'WC-COMMONS-MAIN-001'}]}})
        self._write('QuestTemplates/questtemplates_WC-STORY-MAIN-002.json', {
            'm_questName': 'WC-STORY-MAIN-002', 'm_goals': [
                {'m_goalName': 'Missing npc', 'm_personaName': 'WC-NPC-MISSING',
                 'm_destinationZone': 'OtherWorld/Nowhere'}]})
        self._write('QuestTemplates/questtemplates_DS-MAIN-001.json', {
            'm_questName': 'DS-MAIN-001', 'm_goals': []})
        self._write('NpcSpellInventory/NPCSpellInventories_1025-A.json', {
            'TemplateID': 470479, 'Spells': [
                {'TemplateID': 1649942288, 'RequiredSpellID': 0, 'Level': 80}]})
        self._write('NpcInventory/NPCInventories_1-A.json', {
            'TemplateID': 87112, 'Inventory': [126913, 126914]})
        self._write('DropTables/droptables_wand.json', {
            'Name': 'WC-COMMONS-MAIN-001',
            'Items': [{'ItemId': '1248063', 'ItemName': 'Assaulted Caramels'}]})
        self._write('CreatureSpellbook/CreatureSpellbooks_1-A.json', {
            'DeckName': 'Mdeck-L-BR-DS-SylviaDrake-A-50',
            'SpellTemplateIds': [409737272, 1321504283]})

    def _write(self, relative, payload):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding='utf8')

    def test_real_ids_extracted_without_claiming_game_support(self):
        catalog, report = import_spiraldb(self.root)
        self.assertIn('WizardCity/WC_Hub', catalog['zones'])
        self.assertEqual(len(catalog['portals']), 3)
        self.assertTrue(all(p['protected'] for p in catalog['portals']))
        self.assertEqual(catalog['source_index']['trainer_spell_template_ids'], ['1649942288'])
        self.assertEqual(catalog['source_index']['npc_shops']['87112'][0]['id'], '126913')
        self.assertEqual(catalog['reward_pool'][0]['id'], '1248063')
        self.assertFalse(catalog['reward_pool'][0]['supported'])
        self.assertEqual(report['import_counts']['quests'], 2)
        self.assertEqual(report['import_counts']['unplaced_persona_goals'], 1)
        self.assertEqual(catalog['npcs'][0]['identity'], 'quest-persona:WC-ST01-NPC04')
        self.assertTrue(catalog['npcs'][0]['protected'])
        self.assertFalse(catalog['identities'][0]['visual_supported'])
        self.assertEqual(catalog['source_index']['quests']['WC-COMMONS-MAIN-001']['drop_tables'],
                         ['WC-COMMONS-MAIN-001'])
        self.assertFalse(report['safe_to_generate_manifest'])
        with self.assertRaisesRegex(RandomizerError, 'beginner-eligible attack'):
            generate_manifest(catalog, {'seed': 'ABCD'})

    def test_reproducible_and_overlay_enables_manifest(self):
        spell = [{'id': 100001, 'school': 'Fire', 'pips': 1, 'min_level': 1,
                  'tags': ['attack'], 'supported': True}]
        first, r = import_spiraldb(self.root, spell_overlay=spell)
        second, r2 = import_spiraldb(self.root, spell_overlay=spell)
        self.assertEqual(first, second)
        self.assertEqual(r, r2)
        self.assertTrue(r['safe_to_generate_manifest'])
        manifest = generate_manifest(first, {'seed': 'abc', 'modules': {'spells': 'vanilla'}})
        self.assertEqual(manifest['portals']['zone-transfer:WizardCity/WC_Hub:WizardZoneDatas_1-A.json:0'],
                         'WizardCity/WC_Streets/WC_Unicorn')
        self.assertEqual(manifest['npc_identity'][first['npcs'][0]['slot']],
                         'quest-persona:WC-ST01-NPC04')
        self.assertEqual(manifest['manifest_sha256'],
                         generate_manifest(second, {'seed': 'abc', 'modules': {'spells': 'vanilla'}})['manifest_sha256'])

    def test_modifying_source_changes_fingerprint(self):
        _, r1 = import_spiraldb(self.root)
        self._write('DropTables/droptables_wand.json', {
            'Name': 'WC-COMMONS-MAIN-001', 'Items': [{'ItemId': '87654321'}]})
        _, r2 = import_spiraldb(self.root)
        self.assertNotEqual(r1['source_metadata']['source_sha256'], r2['source_metadata']['source_sha256'])

    def test_invalid_overlay_not_treated_as_verified(self):
        for invalid in [
            [{'id': 'demo-attack', 'school': 'fire', 'pips': 1, 'min_level': 1,
              'tags': ['attack'], 'supported': True}],
            [{'id': 42, 'school': 'fire', 'pips': 1, 'min_level': 1,
              'tags': ['attack'], 'supported': False}],
        ]:
            with self.assertRaises(RandomizerError):
                import_spiraldb(self.root, spell_overlay=invalid)

    def test_corrupt_json_and_missing_sources_rejected(self):
        path = self.root / 'NpcInventory/NPCInventories_1-A.json'
        path.write_text('{')
        with self.assertRaisesRegex(RandomizerError, 'invalid SpiralDB JSON'):
            import_spiraldb(self.root)
        path.unlink()
        for p in (self.root / 'ZoneTransfer').glob('*.json'):
            p.unlink()
        with self.assertRaisesRegex(RandomizerError, 'QuestTemplates/ and ZoneTransfer/'):
            import_spiraldb(self.root)


if __name__ == '__main__':
    unittest.main()

class SpiralDbCliTests(SpiralDbImporterTests):
    def test_cli_writes_both_outputs(self):
        from randomizer.cli import main
        catalog = self.root / 'out/catalog.json'
        report = self.root / 'out/report.json'
        self.assertEqual(main(['import-spiraldb', '--spiraldb', str(self.root),
                               '--out', str(catalog), '--report', str(report)]), 0)
        saved = json.loads(catalog.read_text())
        summary = json.loads(report.read_text())
        self.assertIn('WC-COMMONS-MAIN-001', saved['source_index']['quests'])
        self.assertEqual(summary['import_counts']['portal_triggers'], 3)
