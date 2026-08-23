# Veterancy & Academy

The points where a newly created object's rank is decided — the "academy"
promotion sites in `InfantryClass::Init` / `UnitClass::Init` /
`AircraftClass::Init` / `BuildingClass::Init`, the bookkeeping sites that track
which promotion buildings a house owns, and the infiltration entry point that
grants stolen veterancy.

**Veterancy scale** (YRpp `VeterancyStruct`, `TechnoClass.h:39`) — a `float`:

| Value | Meaning |
|---|---|
| `< 0.0` | invalid / untrainable |
| `0.0 – 1.0` | rookie, partial progress toward veteran |
| `1.0` | veteran |
| `2.0` | elite |

Capped by `[General] VeteranCap=` (`RulesClass::VeteranCap`, a `double`; vanilla
read site `0x66EF87`). Only types with `Trainable=yes` are promoted.

> **Sibling page.** This page is about where a rank is **assigned**. For what a
> rank then *grants* — `TechnoClass::HasAbility` and the ability tables — see
> [Veterancy-Abilities.md](Veterancy-Abilities.md).

This subsystem has an unusually pleasant property and one sharp trap, and they
sit right next to each other:

- The **nine academy addresses are all interior points of larger routines**, and
  every framework handler there returns `0`. They chain cleanly — several
  independent DLLs can compute a promotion at the same address without fighting.
- **`BuildingClass::Infiltrate` (`0x4571E0`) is the opposite**: a function entry
  that Antares/Ares wrap wholesale and exit via a jump target. A second hook
  there is silently dead. See that entry before hooking anything spy-related.

> **Naming caveat.** The PDB symbol map labels these addresses
> `*_Academy` (e.g. `0x413FD2 AircraftClass_Init_Academy`). Those names come from
> the **Antares PDB** and are Antares' own hook labels for *points inside*
> `AircraftClass::Init` — they are not distinct engine functions, and vanilla has
> no function called "Academy". `0x445F80 BuildingClass_Place` is a real function
> start; `0x446366` is an offset within it.

---

### `0x413FD2` — inside `AircraftClass::Init`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `AircraftClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `AircraftClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Promotion point for a freshly constructed `AircraftClass`.
Antares does two things here: applies the aircraft-factory infiltration flag
(`SetVeteran()` if the house has infiltrated one) and then its academy bonus.

**Register / calling convention.** `ESI = AircraftClass*`; return `0` to continue.

**Confirmed via.** Antares source (`~/Claude/Antares-src`, master,
`Hooks.Academy.cpp:105`); registry `hooks.csv`; PDB symbol map.

---

### `0x442D1B` — inside `BuildingClass::Init`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `BuildingClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Promotion point for a freshly constructed `BuildingClass`.
Antares stacks three separate effects here in order: the country's
`VeteranBuildings=` list, the building-infiltration flag, then the academy bonus.

**What it does *not* do — easily mistaken.** This is *building* promotion, i.e.
structures that are themselves veteran. It is unrelated to a building granting
veterancy to units it produces — that is the academy bonus applied at the four
*other* Init sites.

**Register / calling convention.** `ESI = BuildingClass*`; return `0` to continue.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:120`); registry; PDB map.

---

### `0x445905` — inside `BuildingClass::Remove`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Remove_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `BuildingClass_Remove_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Bookkeeping, not promotion: drops the building from the owning
house's list of academies when it leaves the map.

**What it does *not* do — easily mistaken.** Antares gates this on
`pThis->IsOnMap` (`ObjectClass.h:301`). A building that was never placed was
never in the list, and removing it unconditionally would be wrong for any
implementation that tracks membership by identity rather than by count.

**Register / calling convention.** `ESI = BuildingClass*`; return `0` to continue.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:25`); registry; PDB map.

---

### `0x446366` — inside `BuildingClass::Place` (function starts `0x445F80`)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Place_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `BuildingClass_Place_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Bookkeeping: adds the building to its owner's academy list.

**⚠ Register differs from its siblings.** This site uses **`EBP`**, while the
other three list-maintenance sites use `ESI`. Copying a neighbouring handler
without changing the register yields a garbage pointer.

**What it does *not* do — easily mistaken.** Unlike the Remove sites this is
**not** gated on `IsOnMap` — the building is being placed, so it is on the map by
construction.

**Register / calling convention.** `EBP = BuildingClass*`; return `0` to continue.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:11`); registry; PDB map.

---

### `0x448AB2` — inside `BuildingClass::ChangeOwnership` (remove half)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_ChangeOwnership_Remove_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `BuildingClass_ChangeOwnership_Remove_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** The first half of a remove/add pair that migrates an academy
between houses on capture or mind-control. Paired with `0x4491D5` below.

**Ordering.** Both sites live inside one `ChangeOwnership` call and `0x448AB2 <
0x4491D5`, so the remove executes first. The pairing only makes sense if this
site still sees the **old** owner and `0x4491D5` sees the **new** one.
*(Address ordering is confirmed from the PDB map; that the owner pointer actually
swaps between the two sites is inferred from the pairing, not independently
disassembled.)*

**Register / calling convention.** `ESI = BuildingClass*`; return `0` to continue.
Gated on `IsOnMap` like the other Remove site.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:39`); registry; PDB map.

---

### `0x4491D5` — inside `BuildingClass::ChangeOwnership` (add half)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_ChangeOwnership_Add_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `BuildingClass_ChangeOwnership_Add_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Second half of the migration: adds the building to the new
owner's academy list. Not gated on `IsOnMap`.

**Register / calling convention.** `ESI = BuildingClass*`; return `0` to continue.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:53`); registry; PDB map.

---

### `0x4571E0` — `BuildingClass::Infiltrate` — stolen veterancy

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Infiltrate` | 0x5 | `src/Ext/Building/Hooks.Infiltrate.cpp` |
| Ares | `BuildingClass_Infiltrate` | 0x5 | `src/Ext/Building/Hooks.Infiltrate.cpp` |

> **Primary entry:** [Spy-Infiltration.md](Spy-Infiltration.md). This section
> covers only the *veterancy* half of what the site dispatches; the effect
> dispatch, engineer path and stolen-tech model are documented there.

**What it does.** Function entry of
`void __thiscall Infiltrate(HouseClass* pEnterer)`. Antares' handler is, in its
own words, "a wrapper around the entire function": it calls
`BuildingExt::InfiltratedBy(Enterer)` and then

```cpp
return (pBuilding->InfiltratedBy(Enterer)) ? 0x4575A2 : 0;
```

i.e. on success it **jumps to `0x4575A2`** and the vanilla body never runs.

**✅ Co-hooking is safe if you return `0` — verified at runtime.** It is tempting
to assume that because Antares returns a jump target, a later-registered handler
never executes. **That is wrong.** Syringe invokes *every* registered handler for
an address; the first non-zero return only decides where control ultimately goes.
The runtime evidence is recorded in
[Spy-Infiltration.md](Spy-Infiltration.md#verified-co-hooking-0x4571e0-alongside-antares).

**What it does *not* do — easily mistaken.** The five stolen-veterancy branches
are *not* symmetric across frameworks, and this is a real Antares-vs-Ares
divergence rather than a naming difference:

- **Ares** derives the promoted branch from the infiltrated building's
  `Factory=`, so only infantry and vehicle production are reachable.
- **Antares** adds five explicit per-branch flags —
  `SpyEffect.{Infantry,Vehicle,Naval,Aircraft,Building}Veterancy` — which stack
  on top of the `Factory=`-derived behaviour and are *not* limited to what the
  building actually produces. Infantry/vehicle reuse the stock `HouseClass`
  fields `BarracksInfiltrated` / `WarFactoryInfiltrated`; naval, aircraft and
  building promotion have no stock flag and live in Antares' House extension.

**⚠ Stolen veterancy is a hardcoded `SetVeteran()`.** All of these flags are
booleans that resolve to exactly `1.0`. There is no magnitude and no partial
level, and because every consumer applies it raise-only (below), **a third-party
DLL cannot lower it** — a partial (e.g. `0.5`) stolen promotion is unreachable
while the framework flag is set. Any design wanting magnitudes has to use tag
names the framework does not read, and require the framework's own booleans to be
left unset.

**Register / calling convention** (Antares `Hooks.Infiltrate.cpp:58`):
```
ECX       = BuildingClass* EnteredBuilding
[ESP+0x4] = HouseClass*    Enterer
→ returns 0x4575A2 when handled, else 0
```

**Register / calling convention** (Antares `Hooks.Infiltrate.cpp:58`):
```
ECX       = BuildingClass* EnteredBuilding
[ESP+0x4] = HouseClass*    Enterer
→ returns 0x4575A2 when handled, else 0
```

**Confirmed via.** Antares source (`Hooks.Infiltrate.cpp:58`,
`Ext/Building/Body.cpp:670-730`, `Ext/BuildingType/Body.cpp:215-220`); registry
`hooks.csv`; PDB symbol map (`0x4571E0 BuildingClass_Infiltrate`). Co-hook
survival verified at runtime — see below.

---

### `0x4575A2` — inside `BuildingClass::Infiltrate` — *not needed*

Recorded to close off a plausible-looking dead end. `0x4575A2` is the address
Antares/Ares **jump to** from `0x4571E0` once infiltration is handled, and it
looks like the natural "post-infiltration seam" for anyone who believes a second
hook at `0x4571E0` would be skipped.

**There is no reason to use it.** Co-hooking `0x4571E0` directly and returning
`0` works (verified below), which gives the same observation point with a
documented calling convention instead of an unverified one. Register/stack state
at `0x4575A2` has never been checked.

For reference it lies inside `BuildingClass::Infiltrate`: the function begins at
`0x4571E0` and the next distinct routine in the PDB map is
`BuildingClass_SWAvailable` at `0x457630`, with `BuildingClass_Infiltrate_Standard`
labelled at `0x4574D2` and `0x457533` in between.

---

### `0x517D51` — inside `InfantryClass::Init`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `InfantryClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `InfantryClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Promotion point for a freshly constructed `InfantryClass`.

**Register / calling convention.** `ESI = InfantryClass*`; return `0` to continue.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:70`); registry; PDB map.

---

### `0x735678` and `0x74689B` — `UnitClass::Init` — **two sites, both required**

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `UnitClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |
| Ares | `UnitClass_Init_Academy` | 0x6 | `src/Ext/House/Hooks.Academy.cpp` |

**What it does.** Promotion point for a freshly constructed `UnitClass`.
`0x735678` is the copy **inlined into the constructor**; `0x74689B` is
`UnitClass::Init` proper. Antares covers both with one handler via
`DEFINE_HOOK_AGAIN`.

**⚠ Hooking only one leaves a hole.** Vehicles created down the other path
silently miss their promotion. The two addresses look unrelated (different
`0x7xxxxx` pages) which makes it easy to find one and assume it is the site.

**⚠ `VehicleType` does not imply "vehicle".** The category is derived from
behaviour, not class:

| Condition | Treated as |
|---|---|
| `ConsideredAircraft=yes` | aircraft |
| `Organic=yes` | infantry |
| otherwise | vehicle |

A promotion system that dispatches on the C++ class rather than these flags will
disagree with the framework about which bonus a unit gets. Additionally
`Naval=yes` units are ordinary `UnitType`s — Antares treats them as vehicles for
academy purposes while giving them a *separate* infiltration branch, which is
exactly the set the stock `WarFactoryInfiltrated` flag misses.

**Register / calling convention.** `ESI = UnitClass*` at both sites; return `0`.

**Confirmed via.** Antares source (`Hooks.Academy.cpp:81-103`); registry; PDB map
(both addresses carry the same label). `Naval` / `Organic` / `ConsideredAircraft`
/ `Trainable` all confirmed on `TechnoTypeClass` in YRpp.

---

## Why several promotion implementations can coexist

Worth stating explicitly, because it is unusual and it is what makes this
subsystem safe to extend from a co-loaded DLL:

1. **Every framework handler at the nine academy addresses returns `0`.** None is
   a function replacement, so Syringe runs all of them.
2. **Every consumer applies its bonus raise-only** — the shape is invariably
   `if (computed > current) current = computed;`. Antares seeds its accumulator
   at `0.0`, so a negative INI value cannot pull a rank down.

Together these make promotion **commutative**: the final rank is the maximum over
every consumer's answer, independent of load order. A second implementation that
also only ever raises therefore composes rather than conflicts, and one whose
answer is provably `>=` another's makes the other's handler a no-op underneath it.

Two consequences follow, and they cut in opposite directions:

- **Safe:** you can layer an alternative promotion model on top of a framework's
  without disabling it, and without controlling load order.
- **Limiting:** you cannot build a *reducing* effect this way. A "cap",
  "override" or "demote" academy is unreachable from a chained hook, because
  whichever consumer wants the lower value is overruled by whichever wants the
  higher. The only lever a chained hook has is to raise.

**Confirmed via.** Antares source (`HouseExt::ApplyAcademy`,
`src/Ext/House/Body.cpp:856-902`) for the raise-only shape and the `0.0` seed;
`Hooks.Academy.cpp` for all nine `return 0`s; registry `hooks.csv` for consumer
lists. **Unverified:** no runtime experiment with two independent promotion DLLs
loaded simultaneously is recorded here yet.

---

## Related engine facts (not hooks)

- **`Unsorted::ScenarioInit`** (`Unsorted.h:734`, `0xA8E7AC`, an `int`) is used as
  a mutex by Antares' academy code: `ApplyAcademy` returns immediately while it is
  set. This is why **preplaced map objects receive no academy bonus**, and it also
  suppresses re-application during in-game "conversions" such as deploy. Any
  parallel implementation that omits this check will diverge visibly — preplaced
  units gain ranks the framework would never grant, and deploying a unit can
  re-promote it.
- **`RulesClass::VeteranCap`** (`RulesClass.h:461`, a `double`) is the ceiling
  applied after the bonus is computed. Vanilla read site `0x66EF87`.
- **`Trainable=yes`** (`TechnoTypeClass.h:395`) gates promotion on the receiving
  type.
- **Whitelist/blacklist convention.** Antares' `Academy.Types=` / `Academy.Ignore=`
  follow the usual shape: an *empty* whitelist means "all types", and the
  blacklist always wins over the whitelist.
- **Academy state is not readable across DLLs.** Antares keeps its list of owned
  academies in `HouseExt::ExtData::Academies` inside its own extension map, with
  no exported API — the same situation as `std::bitset<32> StolenTech` noted in
  [Buildability-Prerequisites.md](Buildability-Prerequisites.md). A third-party
  DLL wanting academy behaviour must track membership itself using the four
  bookkeeping addresses above; it cannot extend the framework's list.
