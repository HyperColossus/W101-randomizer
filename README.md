# W101 Randomizer

A work-in-progress **seed-based Wizard101 randomizer** built around the open-source [Revive101 / Imlight](https://github.com/Revive101/Imlight) private-server framework.

**Two equally important pillars:** (1) Ascension-inspired **Wildcard/Draft spell progression** with cross-school builds and rerolls, and (2) **seeded adventure randomization** for creatures, bosses, loot, quest rewards, **talk-to NPCs**, and eventually portal connections. These modules can be turned on separately or combined into one chaotic playthrough.

See the [Unified Feature Plan](docs/FEATURES.md) for the complete feature catalog, including NPC identity, questgiver, and location shuffle. See the [Ascension Wildcard Feature Design](docs/ASCENSION_WILDCARD_DESIGN.md) for spell progression mechanics.

> **Status:** Offline prototype v0.3. The seed engine, Wildcard/Draft rules, SQLite bridge, SpiralDB source importer, provenance-checked curation, and C# actor-owned effect contract are implemented. **No live Imlight actor hooks, NPC swaps, or playable game-server integration have been deployed or verified.**

## Project goals

- **Seeded replayability:** Every run has repeatable world and reward mappings, with per-character randomized ability progression.
- **Ascension-style spell builds:** Wildcard random unlocks, three-choice Draft, protected spells, limited rerolls, skill cards, synergy weighting and prototype prestige.
- **Creature and boss shuffle:** Remixed encounters and boss variants with encounter difficulty guards.
- **Loot and quest reward shuffle:** Change supported drops and reward placements without blocking progression.
- **Talk-to NPC shuffle:** Randomize eligible NPC appearance/identity, later questgiver roles and locations while keeping quests functional.
- **Gateway shuffle:** Randomized routes once all critical paths pass reachability checks.
- **Multiplayer and presets:** Shared seeded world, personal spell progress, independent module toggles including a future Full Spiral Chaos preset.

### First playable milestone (not yet achieved)

A **Wizard City-focused** base that demonstrates deterministic Wildcard spell rewards and at least one safe, seeded adventure-world shuffle (creature or eligible NPC appearance). Build NPC questgiver swaps, loot/reward shuffle, Draft and boss variants incrementally after quests and persistence are tested. A complete all-world randomizer is not part of v0.1.

## Run the prototype locally

No game server or game assets are required for the example; its `demo-*` identifiers are fictional placeholders, not genuine Wizard101 IDs.

```bash
python3 -m unittest discover -s tests -v
python3 -m randomizer.cli generate --catalog config/example_catalog.json --settings config/example_settings.json --out out/demo-manifest.json
python3 -m randomizer.cli progress --catalog config/example_catalog.json --manifest out/demo-manifest.json --state state/demo-players.json --character player-001 --level 10
python3 -m randomizer.cli status --catalog config/example_catalog.json --manifest out/demo-manifest.json --db state/demo.sqlite3
```

**Implemented in local code:** independently seeded world mappings; Wildcard/Draft progression; spell locks/reroll tokens; supported skill cards and a prototype prestige lifecycle; tier-filtered creature and boss placements; seeded reward checks; compatible NPC role, identity and location mappings; basic graph + optional modeled quest progression checks; SQLite state/idempotent commands/claim ledger/durable event outbox; an authenticated loopback HTTP API; and a C# HTTP client plus actor-owned effect validation contract for future Imlight integration; SpiralDB source extraction and fingerprint-pinned manual curation.

**Automated tests:** 65 Python unit/integration tests passed locally on October 22, 2026. GitHub Actions now also builds the standalone .NET 10 bridge library; verify the latest job result in Actions.

**Not yet connected to a playable Wizard101 private server:** game-specific Imlight hooks, authoritative spellbook/item grants, NPC appearance and dialogue swaps, quest and NPC service rebinding, actual portal rerouting, complete real-world content/quest catalogs, live cross-school pip balancing, multiplayer game tests, and Discord bot integration. See [Developer Notes](docs/DEVELOPMENT.md), [Game Server Integration](docs/INTEGRATION.md), and [Unified Feature Plan](docs/FEATURES.md).

## SpiralDB → catalog → manifest

Use [the audited SpiralDB pipeline](docs/SPIRALDB_CURATED_PIPELINE.md) to extract real quest/NPC/zone/trainer/loot references from a pinned local SpiralDB checkout, then add an explicit, game-tested curation file. The importer refuses mismatched source fingerprints and unknown spell/item references. This is **not** proof that NPC appearances, real client spellbooks, quest services, or portal transitions work until tested in Imlight. [Example curation schema](config/curation.example.json).

## Intended deployment

The server will run on an existing **Ubuntu laptop** that also hosts a Discord bot. The two services will be isolated in separate directories and managed independently so development doesn't interrupt the bot.

| Component | Purpose |
| --- | --- |
| [Imlight](https://github.com/Revive101/Imlight) | Login, game logic, combat, player state |
| [Aurorium](https://github.com/Revive101/Aurorium) | Game asset / patch server |
| [SpiralDB](https://github.com/Revive101/spiraldb) | World data such as zone transfers and drop tables |
| Embedded RavenDB (Imlight) | Player accounts and character saves |
| W101 Randomizer (this project) | Seed generation, randomized placements, validation, and integration |

Revive101 provides Linux builds. We plan to start from a compatible tagged Imlight release rather than immediately rebuilding the framework from source.

## Development roadmap

- [ ] Check Ubuntu architecture, available RAM, disk space, and port conflicts
- [ ] Install and test the official Imlight Linux build
- [ ] Set up Aurorium and verify compatible game assets / client
- [ ] Change default admin credentials and test local login
- [ ] Keep game services separate from the existing Discord bot
- [x] Build an offline deterministic spell-rolling engine with a **demo** catalog (real game content still needed)
- [ ] Integrate level-up rolls and actual spellbook mutations into Imlight's owning actor (standalone C# event contract committed)
- [ ] Verify cross-school pip behavior and prevent unusable rolls
- [x] Implement offline spell locks and event-based reroll tokens (in-game award hookup pending)
- [x] Implement offline three-choice Draft and pending-offer state (in-game choice UI pending)
- [x] Extract NPC quest-persona references from SpiralDB and add reviewable visual curation (real NPC appearance swaps still pending)
- [ ] Implement NPC questgiver/goal role mapping with dialogue, markers and progression tests
- [x] Implement seed-stable creature, boss and reward **plans** (game changes pending)
- [ ] Validate randomized NPC locations and portal routes before enabling
- [ ] Add configuration controls and optional Discord bot integration
- [x] Test SQLite persistence, event idempotency and concurrent claims locally
- [ ] Test live Imlight multiplayer, reconnection and content restoration

## Existing randomization hooks

Imlight currently exposes experimental settings in `Imlight.ini`:

```ini
[April Fools]
RandomizeCreatures = false
RandomizeGateways = false
RandomBackflips = false
```

These are **not** a complete seed-based randomizer. We will initially test creature randomization separately. Gateway shuffle can introduce broken routes, so it stays disabled until we add reachability checks.

## Project structure (planned)

```text
W101-randomizer/
├── README.md
├── randomizer/       # Python offline seed and progression engine
├── tests/            # Executable deterministic/progression unit tests
├── config/           # DEMO catalogs and settings (not game data)
├── docs/             # Designs and integration guidance
├── integration/      # Standalone C# HTTP bridge source, not wired
└── .github/workflows/ # CI tests
```

These directories exist. The integration helper is source-only; actual Imlight source patches still need implementing and testing.

## Security and data

- Never commit login credentials, Discord tokens, private keys, local certificates, databases, save files, or copyrighted Wizard101 client assets.
- Change the admin credentials supplied in the Imlight example configuration before starting a network-accessible server.
- Begin with a **local-only** game service. Review networking and authentication before allowing outside connections.
- Use legitimately obtained game-client files. Imlight follows a bring-your-own-data approach; this repository will not distribute proprietary game files.

## References

- [Revive101 documentation](https://revive101.de/docs/overview)
- [Imlight releases](https://github.com/Revive101/Imlight/releases)
- [Aurorium](https://github.com/Revive101/Aurorium)
- [SpiralDB](https://github.com/Revive101/spiraldb)
- [Wizapelago](https://github.com/cloiss/manual_wizard101_wizapelago) — community Wizard101 randomizer reference for progression design

## Disclaimer

Independent fan/community project. Not affiliated with or endorsed by KingsIsle Entertainment or the Revive101 team. All trademarks belong to their respective owners.
