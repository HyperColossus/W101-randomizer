# Ascension-inspired Wizard101 Wildcard — Feature Design

**Status:** Working design proposal, not implemented.  
**Scope:** Wizard City first; multi-world support later.  
**Inspirations:** Project Ascension *Wildcard*, *Draft*, Skill Cards, rerolls, and build-defining enchantments.

## Core product decision

The defining mechanic is **a personal, evolving, cross-school spellbook**. Players level up and discover new spells without controlling every unlock. Building a functional, surprising combination is the game.

This **supersedes the earlier emphasis on item-location and portal shuffling**. World progression, bosses, and normal loot should initially remain as close to vanilla as Revive101 currently supports. Creature/loot/portal randomization become optional secondary modes.

These features are an original Wizard101 adaptation. They are **not** present in stock Imlight and the Ascension implementation details described below are not Ascension source code.

## What Project Ascension does (verified design influences)

- **Wildcard:** Random abilities from different WoW classes are gained during leveling; the character grows into an unpredictable build. Original mode had very limited choice.
- **Draft:** Each ability reward presents **three random ability cards** and player chooses one.
- **Skill Cards:** Rare or earned cards guarantee one particular ability in a future roll; this gives players some control over a random build.
- **Rerolls:** Players have ways to replace unwanted randomized abilities; later designs sought to make each roll more meaningful, rather than forcing repeated grind.
- **Synergy:** Drafting an enabling skill can make a dependent skill more likely. Some skills only make sense if you already have the relevant prerequisite.
- **Build customization:** Talents and random/collectible enchantments enhance the randomized spell combinations.
- **Prestige/rebirth:** Optional replay with a fresh evolving build and some persistent meta-progression.

**Caution:** Ascension has changed exact counts, levels, slot limits and consumable names across seasons. Our numbers below are original design choices, not claims about Ascension's current rules.

**Primary references**
- https://ascension.gg/en/news/season-2-begins-next-friday/125
- https://ascension.gg/es/news/season-4-in-depth-overview/168
- https://ascension.gg/de/news/chapter-2-pre-patch-updates/461
- https://ascension.gg/en/news/an-enchanting-update-to-ascension/72
- https://features.ascension.gg/ascension-custom-wow/

## Proposed game modes

### 1. Wildcard (main / recommended)

- On character creation, randomly grant **three spells** from a vetted beginner pool:
  1. **One attack spell** the wizard can actually afford/cast in early combat (guaranteed).
  2. One utility, heal, shield, blade, or second low-cost attack.
  3. One more level-safe ability, from any school.
- Every **three character levels** (4, 7, 10, 13, ...): auto-grant one **new eligible spell** from the pool. Final cadence is tunable in settings.
- Existing abilities remain learned unless the player actively rerolls an eligible spell. No duplicate learned spells and no unexpected removals.
- Random choices are generated deterministically from `seed + character identifier + roll index + ruleset version`; rolls are persisted with an idempotency key to prevent duplicate grants.
- Level gating, pip costs, and valid animations/data are checked before granting a spell.
- **Protected starter attack** cannot be rerolled away until a second eligible attack is owned.
- If no eligible spells exist for a roll, give a safe fallback/credit instead of crashing or silently losing the reward.

### 2. Draft (optional mode, after Wildcard works)

- At each eligible level reward, draw **three distinct** compatible spells.
- Player chooses exactly **one**, kept permanently.
- Unselected spells are not granted.
- Server persists offer and pending choice. A reconnect must show the same offer; it must **not regenerate**.
- Until a usable in-client UI is verified, offer choices through a **safe in-game text command / NPC dialogue**. No assumed custom client popup.

### 3. Chaos Wildcard (optional challenge)

- Broader pools, fewer favorable synergy rolls, reduced reroll access.
- Still always guarantees an early usable attack and excludes spells that cannot function.

## Build-agency mechanics

### Lock / protection
- Allow **one protected spell** at first; grants are protected separately from normal reroll targets.
- The wizard may change the protected spell only outside combat and if doing so leaves a viable attack.
- Later allow 2-3 locks after balancing.

### Reroll tokens
- Earn from configured milestone quests, boss first defeats, or other tested rewards.
- Consume a token to reroll **one unprotected spell** into a new eligible spell.
- Exclude duplicates and the removed spell from the immediate replacement pool.
- Do **not** grant rerolls in an unlimited loop; cap to avoid grind and exploitation.
- Atomic grant+remove+token-consume transaction with recovery on failures; do not let a failed grant delete a spell.

### Guaranteed Spell Cards (later)
- Collect a named **Guaranteed Spell Card** for a spell that exists in our validated catalog.
- Equipping one reserves a future eligible reward slot for that spell, only when its minimum level is reached.
- Limit to one guaranteed slot initially.
- Maintain separate per-account collection and per-character equipped cards.
- Never paywall essential spells or combat viability.

### Synergy roll weights
- Spells have validated tags: `damage`, `heal`, `blade`, `trap`, `shield`, `aoe`, `dot`, `support`, `school:fire`, etc.
- Weight an eligible card more heavily when it synergizes with existing spells (e.g., traps/blades for already-owned attacks), but preserve surprises.
- Spell prerequisites are hard eligibility rules; synergy is a **soft** weighting rule.
- Keep the first version's weights in a versioned config for predictable seeds.

### Prestige (later)
- At level cap, optionally restart from level 1 with fresh rolls on a new character-run record.
- Keep only expressly selected account-level unlocks and cosmetic statistics.
- Prestige must never silently overwrite the player's current spells, pets, items, or equipment.

## Wizard101-specific rules

### School identity and cross-school spells
- Keep the chosen school for wizard identity and baseline stats in the MVP.
- Let rolled spells come from **all schools** when the server/client validate them.
- Because off-school spells have different **power-pip efficiency**, we need a fair pip policy. First playable build can restrict early spells to low pip costs, then prototype a **universal power-pip / mastery rule** only after combat tests prove it possible and fair.
- Do **not** promise universal school mastery until client/server support is verified.
- Do not randomly grant malformed or unsupported treasure-card/item-card templates as permanent spells.

### Trainer and quest bypass
- Ordinary trainers and quest rewards could otherwise undermine Wildcard.
- In Wildcard mode, intercept supported permanent spell-grant pathways; give either a randomizer roll, a token, or a non-spell reward per explicit rules.
- Preserve quest completion logic, quest flags, cinematics and mandatory scripted tutorial behavior.
- Consider special quest-granted spells as protected until verified safe to redirect.

### Deck restrictions
- Learned does not mean equipped: deck capacity and normal deck configuration still apply.
- Never insert incompatible spells directly into decks without server/client testing.
- Track spell identity using template IDs, not names.

## Seed design

- **Realm seed:** determines common world/encounter settings if enabled.
- **Personal rolls:** derive from realm seed + stable character ID, so friends get different builds while sharing the same realm run.
- Save original seed, algorithm version, catalog revision/fingerprint, roll history and active mode.
- Once a run starts, upgrading Imlight or the spell catalog must not silently change future rolls; migrate explicitly.
- Tests: identical inputs -> identical roll sequence; different character IDs -> appropriately different sequences; no duplicated roll reward on relog; no duplicate learned spells.

## Implementation mapping to Revive101 / Imlight

Source inspection has identified useful integration locations (check exact tagged version before coding):

- `src/Imlight.CoreLib/Game/Services/WizardService.cs` handles experience (`ReceiveGainXP`) and detects level changes.
- `src/Imlight.CoreLib/WizardData/Models/Player/Wizard.cs` contains spell-learning persistence (`LearnSpell`, `UnlearnSpell`).
- `src/Imlight.CoreLib/Game/Spells/SpellFactory.cs` resolves spell template IDs.
- `src/Imlight.CoreLib/Game/Services/TrainService.cs`, `src/Imlight.CoreLib/Game/Services/QuestService.cs`, and `src/Imlight.CoreLib/Game/Results/Handlers/` cover other spell-grant paths.
- `SpellTeacher.TryTeach` is visible in the active development branch but may differ across prebuilt release tags. Verify the pinned version and implement a reusable grant/sync path accordingly.

Implementation should isolate randomization behind a `WildcardRollService` / `SpellCatalog` / `RunStore` boundary, rather than scattering RNG calls throughout existing game service handlers.

## Acceptance criteria for first usable Wildcard version

1. New Wizard City wizard gets 3 nonduplicate validated spells and at least one affordable attack.
2. On reaching the first configured milestone level, wizard learns exactly one new eligible spell.
3. Spell shows in the game client's spellbook and persists across relogs/restarts.
4. Multi-level XP awards grant exactly the correct number of milestone rolls (do not only check if `beforeLevel != afterLevel`).
5. Replayed XP, duplicate messages, or crashes cannot duplicate rolls or remove spells.
6. Two characters can play on the same server and roll different classless/cross-school builds.
7. Vanilla scripted quest/tutoral behavior and ordinary combat still work.
8. Existing Discord bot is not modified by any setup step.

## Incremental milestones

1. **Offline prototype:** Spell catalog schema + seeded picker + tests (no server required).
2. **Imlight integration:** Level-up events, safe spell-grant, persistence, single-player test.
3. **Cross-school balancing:** Pip eligibility and starter-pool balance.
4. **Agency:** Lock spell and earnable reroll token.
5. **Draft mode:** 3-card saved offers and choice commands.
6. **Long-term:** Skill Cards, synergy, enchantment-style passives, prestige, optional enemy/loot/portal shuffle.

## Open design decisions

- Wildcard as **main mode**, Draft as optional mode (recommended), or equal priority?
- Auto-roll cadence: every 2, 3, or 5 levels?
- No-choice Wildcard versus 1 re-roll per milestone?
- Should school choice affect weighting, or should all schools be equally likely?
- Should spells be randomly rolled at level 1, or should the user be able to reroll the entire starting hand?

Recommended answers for the first prototype: **Wildcard main**, every **3 levels**, one protected starter attack, weighted toward synergy after the first roll, and a rerollable starter hand before beginning normal questing.
