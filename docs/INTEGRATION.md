# Imlight integration and deployment — NOT yet wired into the game

The repository contains an independent, **working offline randomizer service**, a Python loopback API, and the source of a lightweight **C# HTTP client** at [`integration/ImlightBridge/RandomizerClient.cs`](../integration/ImlightBridge/RandomizerClient.cs). That C# source is an integration building block, **not an installed plugin or a compiled server patch**.

## Critical prerequisites

1. Audit the Ubuntu laptop's memory, disk, CPU, network ports and .NET installation. Keep the existing Discord bot isolated in its own systemd unit.
2. Pin compatible Imlight, Aurorium, SpiralDB, and client versions. Do not assume an old client works with the newest prebuilt server.
3. Build a **verified content catalog** using *real* template IDs and placement IDs in that revision. The checked-in `example_catalog.json` uses fake `demo-*` IDs and a tiny illustrative story dependency graph. **The bridge refuses to start with sample IDs unless explicitly passed `--allow-demo`.** That flag is for local tests only.
4. Before exposing a server, change every default admin password, keep RavenDB private, and review listening interfaces. The Python bridge only allows loopback HTTP with a private bearer token.
5. Set up backups of player saves, catalog, active manifest, and SQLite run database. Avoid changing the manifest while players have an active run.

## Run the randomizer bridge (local simulation only)

```bash
python3 -m unittest discover -s tests -v
python3 -m randomizer.cli generate --catalog config/example_catalog.json \
  --settings config/example_settings.json --out out/demo-manifest.json

# Generate a token locally. Never commit or post it in chat.
export W101_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(40))')"

python3 -m randomizer.cli serve --catalog config/example_catalog.json \
  --manifest out/demo-manifest.json --db state/demo.sqlite3 --allow-demo
```

Test from a second shell on the SAME machine (with the same token in its environment):

```bash
curl -sf -H "Authorization: Bearer $W101_API_TOKEN" \
  http://127.0.0.1:18951/v1/health
```

A production run must use a real catalog, without `--allow-demo`, and a separate database path.

## API contract (JSON; all calls require Bearer token)

- `GET /v1/health` — service status and pending count.
- `GET /v1/manifest` — full frozen world manifest.
- `GET /v1/world/<category>/<slot>` — deterministic result; categories: `npc_identity`, `npc_roles`, `npc_locations`, `creatures`, `bosses`, `rewards`, `portals`.
- `POST /v1/commands` — `{"actor":"stable-character-ID", "action":"start|level|draft|reroll|lock|tokens|skill_card_grant|skill_card_equip|prestige|claim", "request_id":"stable-unique-event-ID", "payload":{...}}`.
- `GET /v1/characters/<id>` — persisted spell plan.
- `GET /v1/characters/<id>/pending` — pending `spell.grant`, `spell.revoke`, `item.grant` events, each with a numeric `id`.
- `POST /v1/ack` — `{"actor":"stable-character-ID", "event_id":123}`; call **only after** the authoritative Imlight change succeeded and persisted.

`request_id` is unique across the entire run. Retrying it with the **same actor, action and payload** returns the first result, even across restarts; reuse for a different command returns an error. Quest and boss reward check claims are one-time per character. A `mob` reward requires a unique combat `encounter_id` so repeats of one fight cannot be claimed twice.

**Event delivery is at-least-once, not exactly-once**: if Imlight applies an event but loses its acknowledgment, it may see the same event again. The adapter must check if the spell/item is already granted before repeating the effect and must write its own transactionally durable receipt or reconcile state. Do not acknowledge first. A `spell.revoke` is only safe after the replacement `spell.grant` is applied.

### Example of a simulated command

```bash
curl -sf -H "Authorization: Bearer $W101_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"actor":"character-123","action":"start","request_id":"create:character-123","payload":{}}' \
  http://127.0.0.1:18951/v1/commands

curl -sf -H "Authorization: Bearer $W101_API_TOKEN" \
  http://127.0.0.1:18951/v1/characters/character-123/pending
```

This will queue **demo spell IDs** in a local SQLite database. It will **NOT give real game spells** until the Imlight adapter handles events.

## Imlight hook design

The following code points were identified in Imlight's source; check file paths against the **tag actually deployed**.

| In-game event | Integration hook | Required behavior |
| --- | --- | --- |
| Character initialized/login | `WizardService`, session/character load | Start character if enabled, drain pending spell events and reconcile game spellbook |
| Character gains XP | `WizardService.ReceiveGainXP` | Send max reached level using a **stable XP event key**; drain queued grants in actor context. This method may skip several levels at once. |
| Learn permanent spell | `Wizard.LearnSpell`, `TrainService`, quest result handlers | Apply grants via authoritative spell factory and notify client; block duplicates; intercept vanilla spell awards only where safe |
| Win / finish quest | Quest/reward handler & `LootGranter` | Resolve supported reward check; grant exactly once; never remove mandatory item/flag/quest result |
| Combat creatures | Zone spawn constructors/components | Map eligible **spawn slot** to vetted same-tier template and keep quest target completion compatible |
| Bosses | Combat spawn/deck / quest-completion handlers | Keep protected critical boss roles and completion hooks intact |
| NPC visuals | Zone entity client behavior / appearance | Render substitute *visual* on original interactive slot, preserving logical template and services |
| NPC quest roles | `InteractPersonaGoalComponent`, `InteractQuestOfferComponent` | Rebind persona goal, offer, dialogue, and quest markers together; template ID substitution alone is unsafe |
| NPC positions | Zone entity spawn position & quest hints | Use approved points, validate access/geometry and rebind quest destinations |
| Portal transitions | `ZoneTriggerSupervisor` or compatible zone transfer handler | Resolve remapped destination after verifying dependencies and return route; protect scripted transfers |

**Threading:** `WizardService` uses actors. Do not mutate live `Wizard` objects from a background HTTP callback. Marshal completed HTTP results back to the *owning actor* and perform spellbook/character-save changes there. Handle temporary API outages by replaying the pending outbox on reconnect.

**Plugin integration status:** The C# `RandomizerClient.cs` is source-only, using standard .NET HTTP/JSON APIs. This repository **does not yet include an Imlight fork/patch**, and the helper has not been compiled against a pinned Imlight build in this environment. It cannot prove that a changed NPC will have correct rendering, dialogue or cinematics.

## Linux service template (do not enable yet)

The sample [`deploy/w101-randomizer.service.example`](../deploy/w101-randomizer.service.example) can be adapted after creating an unprivileged `w101randomizer` account, installing files in `/opt/w101-randomizer`, creating a **verified** catalog and active manifest, and putting a secret environment file in `/etc/w101-randomizer/bridge.env` with mode `0600`. It binds only to loopback and writes SQLite state to its own data directory. Never run the template with the demo catalog on an internet-facing service.

The C# helper has a [`net10.0` library project](../integration/ImlightBridge/ImlightBridge.csproj). Building it still requires the .NET 10 SDK, and embedding it in Imlight still requires separate actor-safe patches. This source has **not** been compiled or tested against the actual pinned game-server build here.

## Security and operational constraints

- Bind Python bridge to `127.0.0.1` only. It rejects non-loopback bind addresses and has no TLS, so do not proxy the API to the public internet.
- Use a separate private service user, private directory permissions, and secret environment file (not version-controlled).
- Keep Imlight game ports and database ports segregated from the existing bot and restrict remote clients by VPN or firewall until tested.
- Use idempotent character IDs and event identifiers and do not trust player-supplied XP or quest completion values without server-side checks.
- Keep a known-good seed and untouched content backup to restore if a newly enabled feature breaks gameplay.

## Completion gates

- **Unfinished**: real Imlight adapter hooks, compatible content export, safe NPC visual/quest role changes, actual loot interception, scripted boss/portal handling, in-client Draft/reroll UI, cross-school pip mastery verification, end-to-end quest validation, and live Ubuntu test.
- **Built/testable today**: deterministic manifest generation, all mapping modules, ability planner with Skill Cards/synergy/prestige, SQLite commands/outbox/claim ledger, authenticated loopback API, standalone C# client source and Python automated tests.
