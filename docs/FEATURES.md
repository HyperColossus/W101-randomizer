# W101 Randomizer — Unified Feature Plan

**Status:** Design proposal; nothing in this document is implemented yet.  
**Target:** Revive101/Imlight private server on an Ubuntu laptop, initially Wizard City.  
**North star:** Make **every character and every adventure feel different** while keeping Wizard101 playable.

## All randomizer modules are first-class

Project Ascension-inspired ability progression is an **addition** to the original game/world randomizer, not a replacement.

| Module | Design | Initial constraints |
| --- | --- | --- |
| **Wildcard spells** | Personal randomized cross-school spell unlocks at level milestones | Vetted spell list, guaranteed affordable attack, saved rolls |
| **Draft spells** | Choose one of three random valid spells | Save unclaimed offers; exclusive with automatic Wildcard awards |
| **Locks/rerolls** | Protect selected spells; earned tokens replace unprotected spells | Never remove the only usable attack; atomic operations |
| **Skill Cards / synergy / prestige** | Influence future rolls, reward themed builds, replay with fresh build | Later after core progression works |
| **Creature shuffle** | Replace ordinary encounter spawns from suitable difficulty pools | Exclude scripted quest-sensitive encounters initially |
| **Boss shuffle** | Remixed boss abilities/minions and eligible boss substitutions | Preserve mandatory quest-boss identifiers/flags |
| **Loot shuffle** | Fixed seeded one-time reward assignments; optionally shuffled farmable drop pools | Keep necessary quest items obtainable |
| **Quest reward shuffle** | Assign random supported gear/spells to eligible quest completions | No disruption of required script events |
| **NPC randomizer** | Shuffle who players meet or talk to, with multiple safety levels | See full design below |
| **Gateway shuffle** | Rewire portal destinations for an exploration challenge | Only after graph reachability/return-route validation |
| **Seed/multiplayer** | Shared seeded world layout with per-character Wildcard rolls, deterministic across reboots | Version and save every manifest; per-player claims |
| **Discord** | Display seed/modes, optional admin-only resets and stats | Later, isolated from the existing production bot |

## NPC Randomizer — First-class module

### Goal

NPCs a player interacts with can surprise them, including questgivers, quest turn-in targets, and ordinary town characters. Different seeds rearrange encounters in different ways. A specific seed keeps its assignments stable, including after restart.

### Modes

**A. Identity/appearance shuffle — first implementation target**

- Randomly assign eligible NPC identities/appearance templates to existing **interaction slots**.
- The original slot remains in its usual position and continues to own the questgiver, goal, shop, tutorial, transport and other services.
- A shuffled appearance is NOT by itself a rewritten quest or dialogue. If the client cannot display the desired look independently from the original template, mark that pairing incompatible rather than replacing the entire NPC object unsafely.
- Names, quest icons, dialogue portraits, prompts and animations must be checked for consistency; provide a fallback to the original NPC when display is unsupported.

**B. Questgiver / talk-to role shuffle — advanced**

- Assign supported quest offer/goal-completion *roles* to new eligible interaction slots with explicit mapping: `original_quest_role -> replacement_npc_slot`.
- Redirect all relevant operations consistently: quest offers, NPC interaction service options, persona-goal completion, quest markers, destination hints, and dialogue identity.
- A player should never be instructed to talk to an NPC who cannot actually complete the goal. For a given seed, mappings are stable and shared.
- Quest dependencies and dialogue timing must remain valid. Exclude tutorial, special scripted cinematics, critical vendors, and quest NPCs with unknown requirements until separately tested.

**C. NPC location shuffle — advanced exploration mode**

- Place an eligible NPC *role* at one of a catalog of validated spawn locations.
- A location is valid only if accessible at the time it is needed and has suitable geometry/interact distance, pathing, visuals, and quest-marker support.
- Forbid unreachable realms, broken zone transfers, collision hazards and quest-locked locations until reachability is solved.
- Combine with gateway shuffle only if joint graph validation passes.

### NPC rules and exclusions

- **Role vs appearance vs location are separate concepts.** Shuffling a visual template must never inadvertently remove a quest service, vendor inventory, or completion trigger.
- Keep a strong fallback when a replacement NPC template is missing or unsupported.
- Start with **noncombat, nonessential NPCs**, then progress to normal questgivers, then critical story NPCs after fully tested.
- One NPC can offer multiple quests; maintain all mapped interactions or forbid ambiguous multi-role swaps.
- Do not confuse quest conversation NPCs with hostile mob spawn templates. NPC shuffle and creature shuffle use different eligibility catalogs.
- Leave original quest narrative/dialogue text intact unless a dialogue rewrite is deliberately added; changing NPC visuals alone may produce funny mismatch (and can be a mode), but show clear objective guidance.
- Avoid placing quest progression behind randomized vendors, transport or daily/session-dependent spawns.
- Exclude NPCs with missing client assets, animations or incompatible interaction services.
- Require deterministic mapping, full manifest persistence, compatibility logs, and replayable test cases.

### Integration points in Imlight (verify against a pinned version)

Code review indicates current NPC interactions are attached by template-specific properties:
- `Game/Zone/Components/InteractPersonaGoalComponent.cs`: persona goals use `m_personaName` matching NPC `m_objectName` and complete quest goals through `MSG_COMPLETEPERSONAGOAL`.
- `Game/Zone/Components/InteractQuestOfferComponent.cs`: quest offers depend on matching NPC dialog definitions.
- `Game/Zone/Components/InteractVendorComponent.cs`: vendor inventory is resolved using NPC template IDs.
- `Game/Zone/Components/NpcComponent.cs`: client NPC behavior, combat properties, and other status.

**Implication:** Naively swapping NPC template IDs is unsafe; it can strip off a questgiver/quest target/vendor role. Implement an `NpcRandomizerService` that separates logical role identity from appearance identity and location, or restrict v1 to proven-safe template pairs.

### NPC acceptance checks

1. Same seed and catalog produces same NPC mapping on every reboot.
2. Swapped NPC can still offer, advance and complete every supported quest attached to the original slot.
3. Appropriate quest icons, objective guidance and dialogue interactions still appear.
4. No duplicate or missing required NPC roles; no stranded vendors/teleporters/tutorial steps.
5. Appearance asset exists and animates; failing swaps fall back without crashing.
6. NPC location assignments only use currently reachable and legal spawn positions.
7. Shared seed gives the same NPC mapping in multiplayer, regardless of per-player spell rolls.
8. NPC shuffle can be toggled independently from creature, loot, portal, and spell shuffle.

## How seeds and modules interact

- The **realm seed** generates immutable world manifests for NPC appearance, NPC roles, NPC placements, encounters, bosses, loot and optional portal graph.
- Each module gets its own deterministic RNG namespace (e.g. `npc.identity`, `npc.role`, `creatures`, `bosses`, `loot`, `portals`) so turning NPC shuffle on doesn't unexpectedly reroll spell rewards.
- Per-character spell rewards are derived from realm seed + stable character ID + milestone number + ruleset version, and persisted.
- Freeze active run settings, content/catalog fingerprint and randomizer version. Preserve player completion/claim ledgers.
- Any configuration incompatible with supported content fails validation loudly rather than silently introducing a softlock.

## Presets (target behavior, not implemented)

| Preset | Spells | NPCs | Creatures | Loot/Bosses | Portals |
| --- | --- | --- | --- | --- | --- |
| Wildcard Journey | Wildcard | Normal | Normal | Normal | Normal |
| Draft Journey | Draft | Normal | Normal | Normal | Normal |
| Adventure Shuffle | Normal | Identity shuffle | Tier shuffle | Enabled where tested | Normal |
| **Full Spiral Chaos** | Wildcard or Draft | Identity + eligible roles | Tier shuffle | Enabled where tested | Validated shuffle when ready |
| Custom | Pick one spell mode | Independent NPC options | Toggle | Toggle independently | Toggle when supported |
| Vanilla Baseline | Normal | Normal | Normal | Normal | Normal |

## Illustrative future configuration (NOT working Imlight.ini)

```yaml
ruleset_version: 1
seed: "WIZ-48291"
scope: wizard_city
spells:
  mode: wildcard   # vanilla | wildcard | draft
  starting_spells: 3
  levels_per_new_spell: 3
npc:
  identity_shuffle: true
  questgiver_shuffle: false
  location_shuffle: false
  preserve_interaction_roles: true
enemies:
  shuffle: true
  difficulty_bands: true
bosses:
  shuffle: false
loot:
  shuffle_quest_rewards: true
  shuffle_boss_first_clear: true
portals:
  shuffle: false
multiplayer:
  shared_world_seed: true
  personal_spell_rolls: true
```

This file is conceptual; schema, supported switches and configuration loading will be built and verified separately.

## Delivery order

1. **Planning and offline tests:** versioned seeded RNG, manifest formats and isolated NPC/creature/spell catalogs; test determinism.
2. **Ubuntu test deployment:** official Linux Imlight and Aurorium with correct compatible game client; leave Discord bot untouched.
3. **First playable randomization:** one seeded spell-roll flow and a validated creature or NPC **identity** shuffle on supported Wizard City content.
4. **Experience depth:** spell Draft/rerolls, safe loot/quest reward shuffle, tiered creatures.
5. **NPC quest role shuffle:** quest goals, offers, guidance, persistence and multiplayer testing.
6. **Boss variants, NPC relocations and portal graph shuffle:** implement reachability validation before enabling.
7. **Full Spiral Chaos preset, balance passes and optional Discord control.**

## References

- [Revive101 / Imlight](https://github.com/Revive101/Imlight)
- [Ascension-inspired Wildcard design](ASCENSION_WILDCARD_DESIGN.md)
- [SpiralDB](https://github.com/Revive101/spiraldb)
- [Wizapelago](https://github.com/cloiss/manual_wizard101_wizapelago)
