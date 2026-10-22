# Developer notes — prototype 0.2

This repository contains a stdlib-only **offline randomizer generator**, a **transactional SQLite progression and reward-planning service**, an authenticated **loopback HTTP API**, and an **unwired .NET client**. It is **not yet a playable Wizard101 private-server mod**; see [INTEGRATION.md](INTEGRATION.md) for the substantial remaining game-specific work.

## Smoke test (no game client, no server required)

```bash
python3 -m unittest discover -s tests -v
python3 -m randomizer.cli generate --catalog config/example_catalog.json --settings config/example_settings.json --out out/demo-manifest.json
python3 -m randomizer.cli progress --catalog config/example_catalog.json --manifest out/demo-manifest.json --state state/demo-players.json --character player-001 --level 10
python3 -m randomizer.cli status --catalog config/example_catalog.json --manifest out/demo-manifest.json --db state/demo-run.sqlite3
```

Run a local bridge using the commands in [INTEGRATION.md](INTEGRATION.md). The example catalog is fictional, not real SpiralDB/Wizard101 data. Running the bridge in demo mode cannot alter the game.

## What has executable code

- SHA-256 deterministic RNG streams for world modules; immutable content fingerprints.
- Vetted-pool Wildcard starter spells, milestone rolls, Draft offers and choices, reroll tokens, protected spells, per-character skill cards, a limited synergy weight, and a prototype prestige lifecycle.
- Seeded mappings for NPC appearances, matching quest-role slots, approved positions, ordinary encounters, boss roles, quest/boss/mob reward checks, and portal destinations.
- Directed-zone portal connectivity and return-path checks plus an optional **explicit quest dependency graph** for NPC talk-to goals, prerequisite flags, and gated portals; real game quests are not yet exported into the graph.
- SQLite `BEGIN IMMEDIATE` transactions with command-idempotency records, durable spell/item outbox, first-clear claims and distinct mob-encounter claim IDs.
- Authenticated local HTTP service and independent .NET HTTP client source code.
- Test suite covering determinism, persistence, concurrency, replay, authorization, and selected gameplay rules.

## What has NOT been accomplished

No verified SpiralDB catalog or Imlight integration hooks, no server-side actor-backed game events, no client rendering tests, no runtime NPC movement, no quest role rebind, no portal rewrites, no actual learned spells or item awards, no normal-player XP validation, and no Discord bot commands. The Python API *schedules* game effects in an outbox; it cannot apply them on its own.

## Next engineering checkpoints

1. Audit existing Ubuntu laptop and bring up pinned Imlight/Aurorium with a legal compatible client; validate core game login and quests unmodified.
2. Export or hand-curate real spell/NPC/encounter/loot/portal identifiers and verify actual behavior.
3. Integrate the .NET bridge into Imlight's actors; implement idempotent grant/confirm and catch up on pending effects.
4. Enable spells first (test cross-school pip policy), then creature + NPC visual swaps, reward interception, and remaining modules one by one.
5. Add quest-aware NPC role rebind, storyline progression solver, and final live end-to-end multiplayer tests before enabling NPC relocation and portals.

The project will **not** include the proprietary Wizard101 client, patches, or copyrighted assets.
