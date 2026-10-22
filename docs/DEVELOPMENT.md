# Developer notes — prototype 0.1

The included Python 3.10+ tool is an **offline randomizer manifest generator and simulated spell-progression engine**. It does **not** launch Wizard101, modify Imlight, swap the visuals of NPCs in a live client, or award actual spells. It is deliberately isolated so the rules can be developed and tested before connecting to a running server.

## Quick start (Ubuntu / macOS / Windows)

Run from the repository root; no third-party Python packages are needed for the CLI or tests:

```bash
python3 -m unittest discover -s tests -v
python3 -m randomizer.cli generate --catalog config/example_catalog.json --settings config/example_settings.json --out out/demo-manifest.json
python3 -m randomizer.cli progress --catalog config/example_catalog.json --manifest out/demo-manifest.json --state state/demo-players.json --character player-001 --level 10
```

Draft example: copy `config/example_settings.json` to your own local file, change `modules.spells` to `draft`, regenerate with a different output and state path, and run `progress` at level 4. That outputs three `pending_drafts` spell IDs. Choose with:

```bash
python3 -m randomizer.cli draft --catalog config/example_catalog.json --manifest out/draft-manifest.json --state state/draft-players.json --character player-001 --level 4 --spell YOUR_OFFERED_ID
```

**Important:** The example catalog uses fake `demo-*` identifiers and artificial world connections. They are only for testing. A **verified content catalog** must be built from the specific compatible Revive101/Imlight and SpiralDB revisions, with user-provided legally obtained asset references, before attempting in-game use.

## Feature coverage in this repository

| Module | Offline prototype | What remains |
| --- | --- | --- |
| Seed engine | SHA-256 counter stream, namespaced reproducible rolls | Versioning and multi-machine replay tests against pinned runtime |
| Wildcard spells | Safe starter attack, three starting spells, level-milestone awards, restartable state | Imlight XP hook, castability checks, synced client spellbook |
| Draft spells | Repeatable 3-choice pending offers and saved choices | In-game UI, NPC or commands, transactional persistence |
| Rerolls/locks | Limited reroll tokens, idempotent token grants, protect starter attack | In-game acquisition, transactions and safety under concurrent commands |
| Skill Cards / synergy / prestige | Architecture and design only | Collection/pity pools, prerequisites, prestige lifecycle |
| Creatures | Tier-filtered, protected encounter manifest | Server spawn replacement, quest kill tracking |
| Bosses | Tier-filtered, protected encounter manifest | AI/deck, cutscenes, quest-boss completion integration |
| Loot/quest rewards | Distinct namespaced deterministic assignments for quest/boss/mob checks | Server-side reward grant interception, claim ledger, shop/gear validation |
| Talk-to NPC appearance | Compatible identity candidate manifest with protected quest NPCs | Client appearance/animation testing and quest icon sync |
| NPC quest roles | Seeded permutation within compatible zone/service signatures | Service and persona-goal rebind, quest-marker and dialogue updates |
| NPC locations | Seeded within-zone unique approved-slot permutations | Actual entity relocation, bounds/paths, objective hints |
| Gateways | Directed-graph reachability and return-path validation | Complete quest dependency logic, teleport rewrite, in-game routing |
| Multiplayer | Shared world seed, personal character spell rolls | Concurrent safe database writes, party quest reward handling |
| Discord commands | Proposed | Separate authenticated integration after bot/server setup |

## Constraints and correctness boundaries

- Generated mappings are **declarative** only; they cannot be safely applied to an Imlight process as-is.
- A portal graph test verifies **zone connectivity only**, not quest unlock conditions, key items, door prerequisites, or NPC activation logic. Therefore `portals` is **not production-ready** even when graph tests pass.
- NPC role mapping must retain original quest logic and rewrite every reference to the role. Merely changing template IDs risks disabling interaction components.
- Some randomizer features compete for the same server hooks. For example, spell-learning results must be routed through an authoritative, single grant path so quest-granted spells cannot bypass Wildcard/Draft rules.
- Python JSON files and atomic rename make a useful local prototype, but **not a concurrent production database transaction**. Do not let a running game server directly read/write this sample state without locking and a transaction protocol.
- The game should fail closed on invalid content or missing requirements. If the adapter does not support a mapping, preserve original content, report why, and never replace mandatory quest services with broken templates.

## Suggested integration approach

1. Pin a specific Imlight release, compatible Wizard101 client revision and SpiralDB snapshot; generate safe catalogs keyed by verified template IDs.
2. Introduce a thin **C# adapter** in an Imlight fork, with interfaces like `IWorldManifestProvider`, `ISpellRollService`, `INpcRoleResolver`, `IEncounterResolver`, `ILootPlacementResolver` and `IPortalResolver`.
3. For each feature, read the immutable manifest and apply it **at the correct authoritative server hook** while preserving quest completion and client updates.
4. Migrate player progression to RavenDB / the selected persistent database with concurrency-safe transactions and idempotency keys. Never perform unprotected parallel updates to JSON files.
5. Verify each mode on a local server, then test combined modes (especially NPC roles + portal shuffle + mandatory quests).
6. Keep existing Discord bot as a separate process and enable read-only seed/status integration first.

See [`FEATURES.md`](FEATURES.md) and [`ASCENSION_WILDCARD_DESIGN.md`](ASCENSION_WILDCARD_DESIGN.md) for the complete design.
