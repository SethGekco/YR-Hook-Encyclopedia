# Encyclopedia (Tier 2)

Curated, hand-written prose entries. One markdown page per subsystem; one entry
per hook address, sorted by address within the page. Use `_TEMPLATE.md` for each
new entry.

This tier is deliberately incomplete and always will be. The goal is not to
write up all ~2,900 addresses — it's to cover the hooks that are **widely used,
widely misunderstood, or conflict-prone**, so the reference earns its keep.

## Priority order for what to write up next

1. **Shared addresses** (`registry/conflicts.md`) — 300 addresses where two or
   more frameworks collide. These are where compatibility bugs actually live and
   where a written explanation saves the most time. The 79 hooked by *all three*
   frameworks are the top of the list.
2. **Famous / high-traffic hooks** — game-loop, firing, targeting, save/load —
   the ones everyone eventually touches.
3. **Easily-mistaken hooks** — anywhere the address's scope (per-type vs
   per-instance, per-frame vs event-driven) trips people up.

## Pages

| Page | Subsystem | Status |
|---|---|---|
| [Ext-Aircraft.md](Ext-Aircraft.md) | Aircraft | seed (1 exemplar entry) |
- [Map Reveal / Sight](Map-Reveal-Sight.md) — RevealArea0/1/2; the big-map trap (YRpp hardcodes stride 512 at compile time).
| [AI-Trigger-Team-Lifecycle.md](AI-Trigger-Team-Lifecycle.md) | AI trigger evaluation, team selection & lifecycle | vanilla-RE (7 behavioural + 4 extension sites; unhooked by frameworks) |
| [Attachment-Cell-Placement.md](Attachment-Cell-Placement.md) | Unit placement marking, cell occupation, custom-locomotor recursion | 4 entries (2 registry-absent DEFINE_JUMPs, 1 do-not-hook, 1 three-framework conflict) |
| [Map-Cell-Indexing.md](Map-Cell-Indexing.md) | Map coordinate→cell indexing & row stride | vanilla-RE (the 512 stride machinery; map-resize crash surface) |
| [PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) | Player Count & House-Array Limits | 3 entries + structural notes (AssignHouses 0x687F10 disassembled: ctor 0x4F54A0, AI cap 0x6882C5, 2nd start-counter 0x6883E6; colour-picker hang refuted for YR) |
| [Input-ActiveClickWith.md](Input-ActiveClickWith.md) | Active-click order dispatch + building-planning guard | 2 entries (full-reimpl conflict hazard: PR#352 vs PR#1993 vs release 0x4AE95E) |
| [Selection-Mouse.md](Selection-Mouse.md) | Object selection & mouse-picking | 3 entries (ObjectClass::Select R0-stub footgun; SelectAt Kratos conflict + occupier fetch) |
| [Savegame-Stream.md](Savegame-Stream.md) | Savegame object-stream save/load boundaries | 4 entries (global append + late-swizzle at LoadInStream_End verified; ⚠ 0x67E42E stolen-byte mismatch Kratos 0xD vs Antares/Ares 0x5) |
| [Techno-Instance-Lifecycle.md](Techno-Instance-Lifecycle.md) | TechnoClass per-instance create/tick/destroy/death | 3 entries (Update/DTOR/ReceiveDamage-destroy; per-instance vs per-type & death-vs-teardown scope traps) |
| [Projectile-Scatter.md](Projectile-Scatter.md) | Projectile scatter (`Inaccurate`/`BallisticScatter`/`FlakScatter`) | vanilla-RE, 6 entries (both magnitude draws + angle synthesis + **unhooked convergence point 0x6FE8D8**; scatter is a circle by construction, Z never scattered, FlakScatter path range-divides at 0x6FE73D) |
| [Production-Queues-Factories.md](Production-Queues-Factories.md) | Per-house production channels, factory selection & unit kick-out | 6 entries (channel≠tab≠factory: naval is its own channel sharing the vehicle tab, defenses their own queue sharing the building factory; ⚠ 0x5F7900 FindFactory is a full Antares replacement → same dead-code trap as 0x4F7870; 3-way conflicts at 0x4502F4/0x4CA07A + the 4-address kick-out cluster with **per-site house registers**; production input must go through EventClass::OutList at 0x6AB773 or desync) |
| [Buildability-Prerequisites.md](Buildability-Prerequisites.md) | `CanBuild` gate & prerequisite helpers | 4 entries (⚠ hidden conflict invisible to conflicts.md: Ares-lineage fully replaces 0x4F7870 → hook the 0x4F8361 epilogue; Phobos raw-patches 0x4F8361 away when Ares absent, clobbering third-party hooks; registry stolen-byte mismatch 0x3 vs source 0x5) |
| [Start-Locations-Spawn-Identity.md](Start-Locations-Spawn-Identity.md) | Start locations & spawn identity | structural + PR#1853 cluster (**three** identity axes not two: country/house-slot are bitfields, start-location is loop-capped; ScenarioClass `HouseIndices[0x10]` is 16-wide vs `StartingPoints[8]` and maps start→house so many-to-one is structurally permitted; ⚠ `NumberStartingPoints` is read downstream as *player count* — Phobos House/Hooks.cpp:475; `<Player @ X>` is trigger-owner only, **not** buildability) |

_(Add a row per subsystem page as it's created. Subsystem names mirror the
`Subsystem` column in the registry.)_

## Writing standard

- Key each entry by **address**, with the engine function name as the heading.
- Fill the **"does not do — easily mistaken"** field. If you can't think of a
  misconception, say so briefly rather than leaving it blank — a blank reads as
  "not yet written."
- **Cite how you confirmed each claim.** Upstream source (name file + version),
  Ghidra/objdump, or in-game test. Mark guesses as unverified. An honest
  "unconfirmed" is worth more than a confident error.
- Frame everything around the **vanilla engine and public frameworks**. Do not
  make a private mod the subject of an entry (incidental-consumer mention only —
  see the neutrality rule in the top-level README).
