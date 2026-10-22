# W101 Randomizer

A work-in-progress **seed-based Wizard101 randomizer** built around the open-source [Revive101 / Imlight](https://github.com/Revive101/Imlight) private-server framework.

**Two equally important pillars:** (1) Ascension-inspired **Wildcard/Draft spell progression** with cross-school builds and rerolls, and (2) **seeded adventure randomization** for creatures, bosses, loot, quest rewards, **talk-to NPCs**, and eventually portal connections. These modules can be turned on separately or combined into one chaotic playthrough.

See the [Unified Feature Plan](docs/FEATURES.md) for the complete feature catalog, including NPC identity, questgiver, and location shuffle. See the [Ascension Wildcard Feature Design](docs/ASCENSION_WILDCARD_DESIGN.md) for spell progression mechanics.

> **Status:** Offline engine v0.1 is implemented and locally tested. It can generate seed manifests and simulate Wildcard/Draft character progression. **Nothing is connected to a running Wizard101 client or Imlight server yet.**

## Project goals

- **Seeded replayability:** Every run has repeatable world and reward mappings, with per-character randomized ability progression.
- **Ascension-style spell builds:** Wildcard random unlocks, optional three-choice Draft, protected spells, limited rerolls, and future synergy.
- **Creature and boss shuffle:** Remixed encounters and boss variants with encounter difficulty guards.
- **Loot and quest reward shuffle:** Change supported drops and reward placements without blocking progression.
- **Talk-to NPC shuffle:** Randomize eligible NPC appearance/identity, later questgiver roles and locations while keeping quests functional.
- **Gateway shuffle:** Randomized routes once all critical paths pass reachability checks.
- **Multiplayer and presets:** Shared seeded world, personal spell progress, independent module toggles including a future Full Spiral Chaos preset.

### First playable milestone (v0.1)

A **Wizard City-focused** base that demonstrates deterministic Wildcard spell rewards and at least one safe, seeded adventure-world shuffle (creature or eligible NPC appearance). Build NPC questgiver swaps, loot/reward shuffle, Draft and boss variants incrementally after quests and persistence are tested. A complete all-world randomizer is not part of v0.1.

## Run the prototype locally

No game server or game assets are required for the example; its `demo-*` identifiers are fictional placeholders, not genuine Wizard101 IDs.

```bash
python3 -m unittest discover -s tests -v
python3 -m randomizer.cli generate --catalog config/example_catalog.json --settings config/example_settings.json --out out/demo-manifest.json
python3 -m randomizer.cli progress --catalog config/example_catalog.json --manifest out/demo-manifest.json --state state/demo-players.json --character player-001 --level 10
```

**Implemented in the offline planner:** deterministic seeds; starter and level-up Wildcard spells; Draft choices; locks and reroll tokens; tier-safe encounter/boss assignments; deterministic reward checks; NPC identity, compatible roles, and within-zone location mappings; and a basic directed-portal reachability test.

**Not implemented in-game yet:** hooking Imlight's XP, spellbook, quest/NPC and loot code; actual entity/portal swaps; server persistence; client visuals; complete quest progression logic; and Discord bot integration. Also see [Developer Notes](docs/DEVELOPMENT.md) and [Unified Feature Plan](docs/FEATURES.md).

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
- [ ] Build an offline deterministic per-character spell-rolling engine and vetted spell catalog
- [ ] Integrate level-up rolls, spellbook updates, persistence, and starter attack guarantee
- [ ] Verify cross-school pip behavior and prevent unusable rolls
- [ ] Implement protected spell slots and earned reroll tokens
- [ ] Add optional three-card Draft mode
- [ ] Build an eligible NPC catalog and implement safe seeded identity/appearance swaps
- [ ] Implement NPC questgiver/goal role mapping with dialogue, markers and progression tests
- [ ] Add seed-stable creature, boss and loot/quest reward modules
- [ ] Validate randomized NPC locations and portal routes before enabling
- [ ] Add configuration controls and optional Discord bot integration
- [ ] Test multiplayer and persist / restore active runs

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
└── .github/workflows/# CI tests
```

The listed offline prototype folders exist; production Imlight integration code will be added separately.

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
