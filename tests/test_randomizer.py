import copy
import json
import unittest
from pathlib import Path
from randomizer import RandomizerError, SpellProgression, generate_manifest
from randomizer.core import SeedRng

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "config/example_catalog.json").read_text())
SETTINGS = json.loads((ROOT / "config/example_settings.json").read_text())


class ManifestTests(unittest.TestCase):
    def test_same_seed_is_identical(self):
        self.assertEqual(generate_manifest(CATALOG, SETTINGS), generate_manifest(CATALOG, SETTINGS))

    def test_independent_modules(self):
        enabled = generate_manifest(CATALOG, SETTINGS)
        altered = copy.deepcopy(SETTINGS)
        altered["modules"]["npc_identity"] = False
        other = generate_manifest(CATALOG, altered)
        self.assertEqual(enabled["creatures"], other["creatures"])
        self.assertEqual(enabled["bosses"], other["bosses"])
        self.assertEqual(enabled["rewards"], other["rewards"])
        self.assertEqual(enabled["npc_roles"], other["npc_roles"])

    def test_protected_content_unchanged(self):
        m = generate_manifest(CATALOG, SETTINGS)
        self.assertEqual(m["npc_identity"]["story-mentor"], "demo-special")
        self.assertEqual(m["npc_roles"]["story-mentor"], "story-mentor")
        self.assertEqual(m["bosses"]["mandatory-boss"], "demo-boss-a")
        self.assertEqual(m["creatures"]["quest-scripted-mob"], "demo-weak-a")
        self.assertEqual(m["rewards"]["critical-quest-key"], "demo-story-key")

    def test_portal_shuffle_validated(self):
        s = copy.deepcopy(SETTINGS)
        s["modules"]["portals"] = True
        m = generate_manifest(CATALOG, s)
        self.assertTrue(m["checks"]["portals"]["shuffled"])
        self.assertNotEqual(m["portals"], {p["id"]: p["destination"] for p in CATALOG["portals"]})

    def test_unsafe_catalog_rejected(self):
        c = copy.deepcopy(CATALOG)
        c["required_zones"].append("not-a-zone")
        with self.assertRaises(RandomizerError):
            generate_manifest(c, SETTINGS)

    def test_namespace_rng(self):
        a = SeedRng("abc", "npc")
        b = SeedRng("abc", "npc")
        c = SeedRng("abc", "spells")
        self.assertEqual([a.below(1000) for _ in range(20)], [b.below(1000) for _ in range(20)])
        self.assertNotEqual([a.below(1000) for _ in range(5)], [c.below(1000) for _ in range(5)])


class SpellTests(unittest.TestCase):
    def test_start_attack_and_determinism(self):
        m = generate_manifest(CATALOG, SETTINGS)
        a = SpellProgression(CATALOG, m)
        b = SpellProgression(CATALOG, m)
        self.assertEqual(a.create_character("test-character"), b.create_character("test-character"))
        ch = a.create_character("test-character")
        self.assertEqual(len(ch["spells"]), 3)
        attack = {s["id"] for s in CATALOG["spells"] if "attack" in s.get("tags", [])}
        self.assertTrue(any(x in attack for x in ch["spells"]))

    def test_levelup_idempotent_and_skipped_levels(self):
        m = generate_manifest(CATALOG, SETTINGS)
        a = SpellProgression(CATALOG, m)
        ch = a.level_to("one", 10)
        self.assertEqual(set(ch["milestones"]), {"4", "7", "10"})
        before = copy.deepcopy(ch)
        self.assertEqual(before, a.level_to("one", 10))
        self.assertEqual(len(ch["spells"]), len(set(ch["spells"])))

    def test_persistence_and_seed_validation(self):
        m = generate_manifest(CATALOG, SETTINGS)
        a = SpellProgression(CATALOG, m)
        a.level_to("one", 7)
        resumed = SpellProgression(CATALOG, m, json.loads(json.dumps(a.state)))
        self.assertEqual(resumed.level_to("one", 10), a.level_to("one", 10))
        changed = copy.deepcopy(m)
        changed["manifest_sha256"] = "wrong"
        with self.assertRaises(RandomizerError):
            SpellProgression(CATALOG, changed, a.state)

    def test_draft_is_stable(self):
        s = copy.deepcopy(SETTINGS)
        s["modules"]["spells"] = "draft"
        m = generate_manifest(CATALOG, s)
        engine = SpellProgression(CATALOG, m)
        ch = engine.level_to("drafter", 4)
        options = ch["pending_drafts"]["4"]
        self.assertEqual(len(options), 3)
        again = engine.level_to("drafter", 4)
        self.assertEqual(options, again["pending_drafts"]["4"])
        self.assertIn(options[0], engine.choose_draft("drafter", 4, options[0])["spells"])
        with self.assertRaises(RandomizerError):
            engine.choose_draft("drafter", 4, options[1])

    def test_token_grants_and_reroll(self):
        m = generate_manifest(CATALOG, SETTINGS)
        a = SpellProgression(CATALOG, m)
        c = a.level_to("one", 7)
        a.grant_tokens("one", 2, "first-boss")
        a.grant_tokens("one", 2, "first-boss")
        self.assertEqual(c["reroll_tokens"], 2)
        target = next((s for s in c["spells"] if s not in c["locked"]), None)
        self.assertIsNotNone(target)
        self.assertNotIn(target, a.reroll("one", target)["spells"])
        self.assertEqual(c["reroll_tokens"], 1)
        with self.assertRaises(RandomizerError):
            a.reroll("one", c["locked"][0])


if __name__ == "__main__":
    unittest.main()
