# W101 Randomizer

A work-in-progress **seed-based Wizard101 randomizer** built around the open-source [Revive101 / Imlight](https://github.com/Revive101/Imlight) private-server framework.

The goal is to turn Wizard City into a replayable challenge where a seed determines the spells you learn, enemies you encounter, and rewards you earn, while preserving a fair and completable route through the game.

> **Status:** Planning / environment setup. This repository does not yet contain a playable randomizer or a configured game server.

## Project goals

- **Seeded runs:** Generate and save a reproducible mapping of encounters and rewards. The same seed and settings should give the same placements.
- **Randomized spell progression:** Shuffle spell unlocks while guaranteeing early access to usable attacks.
- **Randomized enemies:** Replace encounters with difficulty-appropriate creatures rather than unrestricted endgame bosses.
- **Randomized loot:** Shuffle selected quest and boss rewards, taking account of item eligibility.
- **Progression safety:** Validate placements so required abilities and routes remain accessible.
- **Multiplayer:** Support a shared server seed so friends can play the same world.
- **Optional later modes:** Gateway shuffle, harder seeds, and Discord-bot commands.

### First playable milestone (v0.1)

A **Wizard City-focused** prototype that runs locally, successfully loads a character, and demonstrates one reproducible randomized system. After that, add spell rewards and item drops, then progression checks. A complete all-world randomizer is not part of v0.1.

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
- [ ] Test Imlight's experimental `RandomizeCreatures` option
- [ ] Build a seed generator that produces deterministic, saved placement maps
- [ ] Add tiered enemy pools and spell reward pools
- [ ] Implement quest/boss loot placement and repeat-claim protection
- [ ] Validate game progression to avoid softlocks
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
├── docs/             # Ubuntu deployment, design notes, testing
├── config/           # Safe sample config; no secrets
├── src/              # Seed generator and server integration
└── tests/            # Determinism and progression tests
```

Folders above describe the intended layout; they will be added as development starts.

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
