# Production Queues & Factories

The per-house production system: which building is currently producing for a
category, which item advances, and how a finished object leaves the factory.

Three groupings live here and are **routinely conflated**. Keeping them apart is
most of the work of understanding this subsystem:

| Grouping | What it is | Count |
|---|---|---|
| **Channel** (queue) | per-house production slot, keyed by `AbstractType` + naval flag | 5 |
| **Tab** | sidebar strip the cameo appears in | 4 |
| **Factory** | the `BuildingClass` doing the producing | many |

They are not in correspondence:

- **Naval is its own channel but shares the vehicle tab.** A house has separate
  `Factory_VehicleType` and `Factory_NavyType` slots; both draw in tab 3.
- **Defenses are their own queue but share the building factory.** Antares'
  comment at `0x509140` states this directly; the engine's own
  `HouseClass::Update_FactoriesQueues(AbstractType factoryOf, bool isNaval,
  BuildCat buildCat)` takes `BuildCat` *separately from* `factoryOf` for exactly
  this reason.
- **A channel names one factory building at a time** (see `0x4502F4`), but the
  object that finally exits may leave from a *different* building — see the
  alternate-kickout search at `0x4444E2`.

**The per-house channel table** (Ares-lineage). Antares stores it in its house
extension as five `BuildingClass*` slots — `Factory_BuildingType`,
`Factory_InfantryType`, `Factory_VehicleType`, `Factory_NavyType`,
`Factory_AircraftType` — serialized with the house and null-invalidated when a
pointed-to building dies. Set at `0x4502F4`, cleared at `0x4CA07A` and at each
kick-out site.

**Production commands are network events.** Sidebar production input does not
mutate queue state directly; it appends an `EventClass` to the outgoing event
list (`EventClass::OutList`). Anything that changes queue state from user input
must go through that path or it will desync in multiplayer. See `0x6AB773`.

---

### `0x4502F4` — BuildingClass::Update (factory section)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Update_Factory` | 0x6 | `src/Ext/House/Hooks.Queue.cpp` |
| Ares | `BuildingClass_Update_Factory` | 0x6 | — |
| Phobos | `BuildingClass_Update_Factory_Phobos` | — | `src/Ext/Building/Hooks.cpp` |

**What it does.** Runs as a producing building updates. In the Ares lineage it
enforces **one active factory building per channel**: it looks up the house's
channel slot for `B->Type->Factory` (splitting `UnitType` into vehicle/navy on
`B->Type->Naval`), claims the slot if empty, and if the slot is held by a
*different* building, returns `0x4503CA` to skip this building's production
update entirely.

The guard is conditional:

```cpp
if(H->Production && !RulesExt::Global()->AllowParallelAIQueues) { … }
```

`[GlobalControls]►AllowParallelAIQueues` defaults to **true** in Antares, so by
default this restriction **does not engage at all**.

**What it does *not* do — easily mistaken.**
- It is **not** a general "one factory at a time" rule for every house. It is
  gated on `H->Production` (⚠ believed to be the AI-production flag — *not
  verified here*). Do not assume it constrains the human player.
- It does **not** limit how many *items* advance — only how many *buildings*
  produce for a channel. One `FactoryClass` still advances exactly one object;
  that limit lives elsewhere and is untouched by `AllowParallelAIQueues`.
- Setting `AllowParallelAIQueues=no` is not inert elsewhere: Phobos documents an
  AI-aircraft-docking bug tied to that setting.
- Antares implements **only** the global flag. The per-category
  `ForbidParallelAIQueues.Infantry/.Vehicle/.Navy/.Aircraft/.Building` tags and
  the per-TechnoType override attributed to classic Ares have **no
  implementation in the Antares tree** (`grep ForbidParallel` → no hits). ⚠ Whether
  classic Ares truly has them is unverified.

**Used by / interactions.** In `registry/conflicts.md` as a **genuine three-way**
(Antares, Ares, Phobos). Antares/Ares are mutually exclusive, so the live
collision is **Antares + Phobos**, which are co-loadable. Anyone adding a fourth
hook here is joining a crowded site — and a handler that returns `0x4503CA`
skips the rest of the chain.

**Register / calling convention** (Antares).
```
ESI = BuildingClass*  (the producing building)
→ return 0 to continue, or 0x4503CA to skip this building's production update
```

**Confirmed via.** Antares source `src/Ext/House/Hooks.Queue.cpp:11-46` and
`src/Ext/Rules/Body.h:119,175` (`~/Claude/Antares-src`, master); registry
`hooks.csv` + `conflicts.md`. `H->Production` semantics and classic-Ares per-
category tags **not verified**. Vanilla body not independently disassembled.

---

### `0x4CA07A` — FactoryClass::AbandonProduction

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `FactoryClass_AbandonProduction` | 0x8 | `src/Ext/House/Hooks.Queue.cpp` |
| Ares | `FactoryClass_AbandonProduction` | 0x8 | — |
| Phobos | `FactoryClass_AbandonProduction_Phobos` | — | `src/Ext/Building/Hooks.cpp` |

**What it does.** On abandoning production, clears the house's channel slot that
the abandoned object occupied — switching on `F->Object->WhatAmI()` and, for
`Unit`, splitting vehicle vs navy on the type's `Naval` flag. Releases the claim
made at `0x4502F4`.

**What it does *not* do — easily mistaken.**
- It switches on the **object's** `WhatAmI()`, not on the producing building's
  `Factory` type. These usually agree; they are still different reads.
- It clears the channel slot only. It does not itself refund, remove the cameo,
  or update the sidebar — a *separate* Antares hook at `0x4CA0E3` handles the
  sidebar-tab-object cleanup, and only for `HouseClass::CurrentPlayer`.

**Register / calling convention** (Antares). `ESI = FactoryClass*`.

**Confirmed via.** Antares source `src/Ext/House/Hooks.Queue.cpp:48-73`;
registry `conflicts.md` (three-way, same caveat as `0x4502F4`).

---

### `0x5F7900` — ObjectTypeClass::FindFactory

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `ObjectTypeClass_FindFactory` | 0x5 | `src/Ext/House/Hooks.Queue.cpp` |

**⚠ This is a FULL REPLACEMENT, not an extension.** Antares' handler delegates to
`HouseExt::HasFactory(...)`, writes the result to `EAX`, and `return 0x5F7A89` —
jumping to the function epilogue so **the entire vanilla body never executes**.

**What it does.** Answers "which factory building would produce this type for
this house, if any usable one exists." Returns the factory only when
`HasFactory` reports state `>= Available`; the richer `FactoryCheckReturn`
(`Unbuildable` / `NoFactory` / `Unpowered` / `Available` / `Primary`) is
collapsed to a single pointer-or-null at this boundary.

**What it does *not* do — easily mistaken.**
- **Anything hooked inside the vanilla body (between `0x5F7900` and `0x5F7A89`)
  is dead code whenever Antares is loaded.** This is the trap. It is the same
  failure mode this encyclopedia documents for `HouseClass::CanBuild` at
  `0x4F7870`.
- Do **not** add a second hook at `0x5F7900` expecting to refine the verdict —
  the handler returns a jump target, so a chained hook either never runs or
  fights over `EAX`. Extend `HouseExt::HasFactory`, or chain at the epilogue.
- It does not decide where the object *exits* — that is the kick-out cluster
  below. A type can have a factory here and still leave from another building.
- The nuance the collapse hides: `Unpowered` is distinct from `NoFactory`, and
  callers that only see null cannot tell "you have one, it's unpowered" from
  "you have none." `0x6AB312` reads that distinction to grey the cameo.

**Register / calling convention** (Antares).
```
ECX        = TechnoTypeClass const* pThis
[ESP+0x4]  = bool  allowOccupied
[ESP+0x8]  = bool  requirePower
[ESP+0xC]  = bool  requireCanBuild
[ESP+0x10] = HouseClass const* pHouse
→ writes EAX = BuildingClass* or nullptr, returns 0x5F7A89
```

**Confirmed via.** Antares source `src/Ext/House/Hooks.Queue.cpp:182-199` and
`src/Ext/House/Body.cpp:377-448`, `Body.h:64-74`. Not in `conflicts.md` (no other
registry framework hooks this address). Vanilla body not disassembled — the
"never executes" claim rests on the `return 0x5F7A89` in the Antares handler.

---

### `0x444119` / `0x444131` / `0x44531F` / `0x443CCA` — BuildingClass::KickOutUnit (per category)

**Framework names**
| Address | Category | Frameworks |
|---|---|---|
| `0x444119` | UnitType | Antares, Ares, Phobos (`…_UnitType_Phobos`) |
| `0x444131` | InfantryType | Antares, Ares, Phobos (`…_InfantryType_Phobos`) |
| `0x44531F` | BuildingType | Antares, Ares, Phobos (`…_BuildingType_Phobos`) |
| `0x443CCA` | AircraftType | Antares, Ares, Phobos (`…_AircraftType_Phobos`) |

**What it does.** As a finished object is kicked out, the Ares-lineage hook
**clears the house's channel slot** for that category, freeing the channel for
the next producer. The unit variant re-reads `U->Type->Naval` to pick the vehicle
or navy slot.

**What it does *not* do — easily mistaken.**
- These are **four separate addresses for four categories**, not one shared site.
  Patching "the kick-out hook" means patching all four; missing one leaves that
  category's channel slot stuck.
- The register holding the house **differs per site** — `ESI->Owner` (unit),
  `EAX` (infantry, building), `EDX` (aircraft). Copying a handler between them
  without adjusting the register is a silent wrong-pointer bug.
- They clear channel state; they do **not** choose the exit building or cell.
  Selection of an alternate factory to exit from is `0x4444E2`
  (`…_FindAlternateKickout`, Antares + Ares), with `0x4444B3`
  (`…_NoAlternateKickout`) as its counterpart; the barracks exit cell is a
  separate Phobos hook at `0x444B83`.

**Used by / interactions.** All four are **triple-hooked** (Antares + Ares +
Phobos) — the busiest cluster in this subsystem. Live collision is Antares +
Phobos. Check load order before adding anything here.

**Confirmed via.** Antares source `src/Ext/House/Hooks.Queue.cpp:75-112`
(registers read directly from the `GET` macros); registry `hooks.csv` for the
Phobos and Ares rows and for `0x4444E2` / `0x4444B3` / `0x444B83`.

---

### `0x509140` — HouseClass::Update_FactoriesQueues (call site)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `HouseClass_Update_Factories_Queues` | 0x5 | `src/Misc/Interface.Sidebar.cpp` |

**What it does.** Antares intercepts the per-house queue update and, when the
call is for `BuildingType` with `BuildCat::DontCare`, issues an **additional**
call for `BuildCat::Combat` — because **defenses occupy their own queue while
sharing the building factory**, and the vanilla single call misses them. Then
sets `MouseClass::Instance.SidebarBackgroundNeedsRedraw = true`.

This is the clearest evidence in the codebase that **`BuildCat` is a distinct
axis from `factoryOf`**.

**What it does *not* do — easily mistaken.** It does not replace the vanilla
update (returns 0 — vanilla still runs); it *adds* a second pass. Hooking here
and returning non-zero would drop the original update.

**Register / calling convention** (Antares).
```
ECX       = HouseClass*
[ESP+0x4] = AbstractType factoryOf
[ESP+0x8] = bool         isNaval
[ESP+0xC] = BuildCat     buildCat
```

**Confirmed via.** Antares source `src/Misc/Interface.Sidebar.cpp:298-313`.
Antares is the only registry framework at this address.

---

### `0x6AB773` — SelectClass::ProcessInput (production event dispatch)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SelectClass_ProcessInput_ProduceUnsuspended` | 0xA | `src/Misc/Interface.Sidebar.cpp` |

**What it does.** The sidebar cameo production input path. Antares implements
"shift-click queues five" by reading the modifier byte from the stack and adding
the **same `EventClass` to the network out-list N times**:

```cpp
auto count = 4 * (modifiers & 1) | 1;   // 5 with shift, else 1
while(count--) { Networking::AddEvent(pEvent); }
```

**This is the canonical example of how production input must reach game state:**
by appending an `EventClass` to `EventClass::OutList`, not by writing queue state
locally. Any hook that changes production from user input and skips this path
will desync in multiplayer.

**What it does *not* do — easily mistaken.**
- It does not "queue 5 items" as one operation — it enqueues **five identical
  events**. Per-event validation still runs five times, so build limits and
  affordability are re-checked, not bypassed.
- `modifiers & 1` is bit 0 only (shift). Other modifier bits are untouched and
  available for new gestures — the natural place to add one.
- Returning `0x6AB7CC` skips the vanilla single-add; a chained hook must account
  for that.

**Register / calling convention** (Antares).
```
EAX        = EventClass*
[ESP+0xB8] = byte modifiers   (bit 0 = shift)
→ returns 0x6AB7CC
```

**Confirmed via.** Antares source `src/Misc/Interface.Sidebar.cpp:370-383`.
Antares is the only registry framework at this address (as is `0x6AB312`,
`SidebarClass_ProcessCameoClick_Power`, which greys the cameo when
`HasFactory` reports `Unpowered`).

---

## Related pages

- **Buildability & Prerequisites** — `HouseClass::CanBuild` (`0x4F7870`), same
  full-replacement trap as `0x5F7900` here.
- **Sidebar strips & tabs** — *not yet written*; the ~175 hooks in the `0x6A`
  range (strip draw, tab index, button pool) are in the registry but have no
  prose page. The tab-index sites `0x6A5F6E`, `0x6A614D`, `0x6A633D`, `0x6ABC9D`
  all sit in Phobos `src/Ext/SWType/Hooks.cpp` — i.e. they arrived with the
  Exclusive SuperWeapon Sidebar (PR #1384, merged 2025-06-05; PRs #1383 and #1379
  are its closed predecessors).
