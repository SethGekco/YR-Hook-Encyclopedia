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
| [AI-Trigger-Team-Lifecycle.md](AI-Trigger-Team-Lifecycle.md) | AI trigger evaluation, team selection & lifecycle | vanilla-RE (7 behavioural + 4 extension sites; unhooked by frameworks) + **ScriptType action grammar** (ordering rules, BwP target encoding `65536*mode+idx`, the `53→8` unload-in-the-field trap) + **AI situational-awareness data** (`HouseClass::ZoneInfos[5]{Air,Armor,Inf}`, `ThreatPosedEstimates[130][130]`, `LATime`; ⚠ frame-key RNG for lockstep; ⚠ never LogWrite unconditionally in `ConditionMet` — 322MB log) |
| [Attachment-Cell-Placement.md](Attachment-Cell-Placement.md) | Unit placement marking, cell occupation, custom-locomotor recursion | 4 entries (2 registry-absent DEFINE_JUMPs, 1 do-not-hook, 1 three-framework conflict) |
| [Map-Cell-Indexing.md](Map-Cell-Indexing.md) | Map coordinate→cell indexing & row stride | vanilla-RE (the 512 stride machinery; map-resize crash surface) |
| [PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) | Player Count & House-Array Limits | 3 entries + structural + reference impl &mdash; **RUNTIME-VALIDATED** in a live skirmish (all globals + `+0x16054` confirmed; AssignHouses runs TWICE; ⚠ AI-loop sentinels SKIP not break, EAX counts creations not slots) |
| [Input-ActiveClickWith.md](Input-ActiveClickWith.md) | Active-click order dispatch + building-planning guard | 2 entries (full-reimpl conflict hazard: PR#352 vs PR#1993 vs release 0x4AE95E) |
| [Selection-Mouse.md](Selection-Mouse.md) | Object selection & mouse-picking | 4 entries (ObjectClass::Select R0-stub footgun; SelectAt Kratos conflict + occupier fetch; **0x692300 ProcessClickCoords is the ONLY correct screen&rarr;cell — ClientToCoords 0x6D2280 assumes flat ground and lands ~1 cell north per height level, invisible on a flat map; view origin is DSurface::ViewBounds 0x886FA0 not 0xB0CE28**) |
| [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md) | When `return 0` is a bug (stub re-runs the stolen bytes) | 2 crash shapes: un-relocated relative branch; stolen read re-dereferencing a register the handler wrote. Both have perfect geometry, so size/overlap checkers pass them |
| [Savegame-Stream.md](Savegame-Stream.md) | Savegame object-stream save/load boundaries | 4 entries (global append + late-swizzle at LoadInStream_End verified; ⚠ 0x67E42E stolen-byte mismatch Kratos 0xD vs Antares/Ares 0x5) |
| [Techno-Instance-Lifecycle.md](Techno-Instance-Lifecycle.md) | TechnoClass per-instance create/tick/destroy/death | 3 entries (Update/DTOR/ReceiveDamage-destroy; per-instance vs per-type & death-vs-teardown scope traps) |
| [Target-Evaluation-Threat.md](Target-Evaluation-Threat.md) | `EvaluateObject` threat gates (aggressive-stance / attack-anything) | vanilla-RE, 3 gates (0x6F84A9 vehicle / 0x6F8503 non-building / 0x6F858F building; **all three steal a relative branch — hooking at entry with `return 0` re-runs the un-relocated `jcc` from Syringe's stub and crashes `C0000005` at ~0x09ED0475 reached from GreatestThreat 0x6F9D7B; never return 0, replicate the branch and return an explicit address**) |
| [Projectile-Scatter.md](Projectile-Scatter.md) | Projectile scatter (`Inaccurate`/`BallisticScatter`/`FlakScatter`) | vanilla-RE, 7 entries (both magnitude draws + angle synthesis + **unhooked convergence points 0x6FE8D8/0x6FE8EE**; scatter is a circle by construction, Z never scattered, coords are **aim-vector deltas** feeding atan2; FlakScatter path = `drawn×dist÷GetWeaponRange` — the normalisation IS the cap; ⚠ `and esp,0xF8` at 0x6FDD53 makes `ebp−k` invalid for locals) |
| [Production-Queues-Factories.md](Production-Queues-Factories.md) | Per-house production channels, factory selection & unit kick-out | 6 entries (channel≠tab≠factory: naval is its own channel sharing the vehicle tab, defenses their own queue sharing the building factory; ⚠ 0x5F7900 FindFactory is a full Antares replacement → same dead-code trap as 0x4F7870; 3-way conflicts at 0x4502F4/0x4CA07A + the 4-address kick-out cluster with **per-site house registers**; production input must go through EventClass::OutList at 0x6AB773 or desync) |
| [Buildability-Prerequisites.md](Buildability-Prerequisites.md) | `CanBuild` gate & prerequisite helpers | 6 entries (⚠ hidden conflict invisible to conflicts.md: Ares-lineage fully replaces 0x4F7870 → hook the 0x4F8361 epilogue; Phobos raw-patches 0x4F8361 away when Ares absent, clobbering third-party hooks; registry stolen-byte mismatch 0x3 vs source 0x5; **0x4F657A: `Owner=` is parent-indexed via `ParentCountry` while Required/ForbiddenHouses use the country's own ArrayIndex2 — and vanilla defines `ParentCountry` for NO country, so a blank `Name=` hijacks `FindIndexOfName("")`**; **0x4F671D: unguarded NULL deref = the C0000005 the whole country-identity mess actually crashes at; Antares guards 2 of 3 sites**) |
| [Logic-Frame-Update.md](Logic-Frame-Update.md) | Per-frame logic update / object loop | 3 entries (0x55AFB3 crowded vs 0x55B6B3 uncontended post-loop seat; lockstep determinism note) |
| [Start-Locations-Spawn-Identity.md](Start-Locations-Spawn-Identity.md) | Start locations & spawn identity | structural + PR#1853 cluster (**three** identity axes not two: country/house-slot are bitfields, start-location is loop-capped; ScenarioClass `HouseIndices[0x10]` is 16-wide vs `StartingPoints[8]` and maps start→house so many-to-one is structurally permitted; ⚠ `NumberStartingPoints` is read downstream as *player count* — Phobos House/Hooks.cpp:475; `<Player @ X>` is trigger-owner only, **not** buildability) |
| [Gap-Generator-Vision.md](Gap-Generator-Vision.md) | Gap generators & vision denial | vanilla-RE + 3 entries (**gap is client-side, computed against `CurrentPlayer` only** — no per-house gap state, so "see through their gap" is a render decision; `CellClass +0x13C` identified as the friendly-gap counter YRpp calls `unknown_13C`; shape is a hard-coded circle; **VERIFIED: create clears AltCellFlags::Mapped, which is why gap shroud is permanent AND why animated patterns are invisible without SpySat — preserve that bit for a second shroud class**; ⚠ do not co-hook Antares' inner sites 0x6FB306/0x6FB5F0 — wrap the entry 0x6FB170 instead; CreateGap/DestroyGap are RX stubs in YRpp) |
| [Fog-Of-War-Dormant-Layer.md](Fog-Of-War-Dormant-Layer.md) | Fog of war — the dormant TS layer | vanilla-RE (**the layer EXISTS but is broken — do not budget it as small**; `FogOfWar` is a real vanilla tag in THREE places: `RulesClass`, `GameModeOptionsClass`, `ScenarioClass` bit; per-cell `FogCell`/`CleanFog`/`IsFogged` + `FoggedObjects` snapshot vector + `Foggedness` byte indexing `fog.shp`; `FogRate` lives in `[AudioVisual]`; Phobos issue #28 open with a bounty since Dec 2020, PRs #122/#1872/#2229 all unmerged; **units are still visible under fog**; key asymmetry — shroud is first-class and fully respected, fog is second-class and half-honoured, so prefer restyling shroud over enabling fog) |
| [Veterancy-Abilities.md](Veterancy-Abilities.md) | `HasAbility` & the veteran/elite ability tables | 1 entry (0x70D0D0, **34 call sites, no framework hooks it**; hook the body at 0x70D0D5 not the entry — both exits pop ebx/esi/edi; arg moves 0x4→0x10; **all 34 sites classified**: only 9 abilities are ever queried here — CRUSHER 12, C4 11, FEARLESS 3, SCATTER/GUARD_AREA 2, FASTER/VEIN_PROOF/EXPLODES/SENSORS 1; STRONGER/FIREPOWER/ROF/SIGHT/CLOAK/TIBERIUM_PROOF/SELF_HEAL/RADAR_INVISIBLE/TIBERIUM_HEAL are read directly off +0x29C/+0x2AE and CANNOT be granted from this hook) |
| [Veterancy-Academy.md](Veterancy-Academy.md) | Where rank is **assigned**: academy promotion sites, academy bookkeeping & stolen veterancy | 11 entries (the 9 academy addresses are **interior points** of Init/Place/Remove/ChangeOwnership, all handlers `return 0` → promotion is **commutative**, so independent implementations compose but a *reducing* effect is unreachable; ⚠ `0x446366` uses **EBP** while its three siblings use ESI; ⚠ `UnitClass::Init` is **two** sites 0x735678+0x74689B and category is by `Organic`/`ConsideredAircraft`, not C++ class; `ScenarioInit` mutex = preplaced objects get no bonus; ⚠ stolen veterancy is a hardcoded `SetVeteran()` 1.0 that a third party **cannot lower**; Antares adds 5 per-branch SpyEffect flags Ares lacks; `0x4575A2` documented as a **dead end, not needed**) |
| [Countries-Taunts.md](Countries-Taunts.md) | Country-index width limits & taunt playback | vanilla-RE, 6 entries (**country storage is unbounded — two *field widths* cap it**: `1u << ArrayIndex2` into a DWORD = 32, and a 4-bit nibble in the taunt wire byte = 16; `INIClass::ReadHouseTypesList` 0x4750D0 is the single country-set parser with **exactly 4 call sites**; `PlayTaunt` 0x752B70 has **3 callers and Antares hooks only 2** — ⚠ 0x64A75E unclaimed and the leading suspect for the residual 16 limit; offline taunts are 4 `GameMode::Skirmish=5` compares; ⚠ latent OOB read in Antares' `PlayCountryTaunt`) |
| [Superweapon-Launch-Targeting.md](Superweapon-Launch-Targeting.md) | Superweapon launch, targeting & the pending-SW cursor | 4 entries (**inhibitors/designators have NO engine address — framework C++ only, duplicated in Antares + Phobos**; **0x4FAE50 Fire_SW is the universal 17-call-site launch funnel with an unhooked entry** — abort via AL=0 + jump 0x4FAEF3, never the 0x4FAEED epilogue; 0x4AC21C is the click convergence point Antares returns to; &#9888; **GetAction 0x6CEF80 has a FOUR-byte prologue** so a 5-byte jmp corrupts Antares' 0x6CEF84 hook — replace vtable slot 0x7F40FC instead; SuperClass::Launch clears the pending-SW global 0x8809A0 at **11** sites) |
| [Spy-Infiltration.md](Spy-Infiltration.md) | Spy infiltration & stolen tech | 1 entry + structural (engineers do **not** pass through 0x4571E0 — capture is a separate path; co-hooking 0x4571E0 is load-order-safe *only* while you return 0; the stolen-tech 32 ceiling is a `DWORD` storage choice, not an engine limit, and Antares already accepts a comma **list** per building) |

| [Building-Production-KickOut.md](Building-Production-KickOut.md) | Factory unit ejection (KickOutUnit) — the "built by a factory" event | 1 entry (0x443C60 entry: pTechno at [esp+4]; the built-only-gate hook, excludes paradrop/crate/map/spawn) |

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
