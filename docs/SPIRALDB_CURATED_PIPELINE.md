# SpiralDB → verified catalog → seed manifest → Imlight event bridge

This is a *working offline, opt-in data pipeline*. It is **not a playable private server** and it does not self-install into Imlight. Source identifiers alone are insufficient to approve creature spawns, NPC appearances, pip costs, safe portal swaps, or quest rewards.

## 1. Pin a SpiralDB checkout

On a development machine, clone `https://github.com/Revive101/spiraldb.git` outside this project. The importer reads the checkout **locally**, without modifying it:

```bash
git clone https://github.com/Revive101/spiraldb.git ../spiraldb-cache
git -C ../spiraldb-cache rev-parse HEAD
python3 -m randomizer.spiral_cli --spiraldb ../spiraldb-cache \
  --out out/spiraldb-unverified.json --report out/spiraldb-audit.json
```

The report identifies source revision and SHA-256 fingerprint. Keep the exact revision alongside the Imlight/client revisions for the run. Do not use stock Imlight's fetch-on-every-boot setting for an active randomizer run until the content snapshot policy is established.

## 2. Curate actual game-template IDs

Copy and fill `config/curation.example.json`. Required fields:

- `spiraldb_sha256` — exact `source_metadata.source_sha256` from the audit file. Any upstream data change fails closed.
- `client_build`, `imlight_revision` — tested build identifiers.
- `spells` — IDs must occur in SpiralDB NPC trainer inventories or creature spellbooks **and** have manually checked school/pip/min-level and successful cast evidence. Every entry requires `client_verified: true` and `cast_verified: true`.
- `reward_items` — IDs must occur in drop tables and have verified item/client-grant behavior, `pool` and `min_level`.
- `quest_rewards` — quests must exist in the selected World/quest scope. The rewarded item must be listed in a drop table referenced by that quest and be separately approved. Real scripted quest requirements must still be validated in-game.
- `npc_visuals` — map existing *persona references* to manually verified visual template IDs and named compatibility groups; `spawn_verified`, `client_verified`, `services_verified` are required. **Role swaps and location swaps stay disabled**, even when visuals are approved.
- `portal_triggers` — only known ZoneTransfer trigger IDs with tested transition and return routes can be released from protection. Other zone graph requirements are not proven by this check.

Never set verification booleans just to make the importer succeed: the importer can verify data provenance, **not** your gameplay test results.

```bash
python3 -m randomizer.spiral_cli --spiraldb ../spiraldb-cache \
  --curation config/my-verified-curation.json \
  --settings config/my-world-seed.json \
  --out out/live-catalog.json \
  --report out/live-source-audit.json \
  --manifest out/live-manifest.json
```

Generating a manifest requires at least one verified low-pip starter attack. An unverified catalog can still be extracted for review without generating a manifest. A manifest is **data for an adapter**, not a modified game world.

## 3. Connect to Imlight

`integration/ImlightBridge/RandomizerClient.cs` is the C# loopback API client. `PendingEffects.cs` adds strict parsing and a small actor-owned effects contract. It deliberately does **not** touch Imlight's `Wizard` outside of the owning Akka actor or call game APIs that may not exist in the chosen revision.

1. In a pinned Imlight source fork, reference `integration/ImlightBridge` or copy its source with AGPL-compatible attribution and licensing consideration.
2. At character creation/login, enqueue a stable `start` command. After level changes, enqueue `level` with a stable XP event ID and the highest actual level reached. On quest reward/boss combat success, enqueue verified `claim` checks.
3. Fetch pending events **asynchronously**, then send immutable `PendingEffect` messages back to the owning wizard actor. Do **not** mutate the `Wizard` inside an HTTP continuation.
4. Implement `IActorOwnedWizardEffects` using Imlight's real `SpellFactory`, `Wizard.LearnSpell` / `UnlearnSpell`, client spellbook packets, and its item-loot/save APIs. These methods must throw on failure, and `GrantItemOnceAndSync` must persist its receipt atomically with the item.
5. Once the actor has successfully saved + synchronized a single effect, acknowledge the event through `RandomizerClient.AckAsync`. Never acknowledge before game save. Process effects in ascending event order; grant replacement spells before revoking old spells.
6. Reconcile pending effects on login and after bridge outages. At-least-once delivery is intentional and the adapter must be idempotent.

The Python API is bound only to loopback and requires a secret bearer token. Keep it and RavenDB unexposed; do not attach this to a public IP or the existing Discord bot.

**Important:** The bridge project is source-level and cannot be regarded as compiled or playable until a .NET 10 SDK and a pinned Imlight checkout compile it and a compatible client verifies in-game behavior. See `docs/INTEGRATION.md`.

## 4. Safety coverage still missing

- Client-derived spell taxonomy and pip mechanics; global trainer references are not enough.
- Quest complete-state requirements, NPC spawn instance IDs, safe visual role binding, quest icons/dialogue.
- Encounter spawn coordinates, difficulty validation, combat result integrity, boss scripted behaviors.
- Full travel graph plus quest requirements and usable return routes.
- Game-side item receipt persistence, character reconciliation, and real multiplayer playtests.

These remain explicitly unsupported rather than silently randomized with incomplete data.
