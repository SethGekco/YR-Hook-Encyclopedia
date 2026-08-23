# Subsystem: Building Occupancy — Garrison, Battle/Tank Bunker, and Open-Topped

Everything about **infantry (and units) held inside a building and firing out**.
The single most important thing to understand here is that the engine has **three
distinct, independently-hooked systems** that look similar on screen but share
almost no code:

1. **Garrison / Urban Combat (UC)** — infantry occupy a `CanBeOccupied=yes`
   structure (classically neutral civilian buildings). Occupants live in
   `BuildingClass::Occupants` (a `DynamicVectorClass<InfantryClass*>`) and fire
   through a **single shared** occupy-weapon slot arbitrated by
   `FiringOccupantIndex`. Entry is the `FindGarrisonStructure` path.
2. **Battle Bunker / Tank Bunker** — a YR addition: a friendly unit (typically a
   tank) parks inside a bunker structure and fires out. Entry is the
   `FindBattleBunker` / `FindTankBunker` path; update is
   `BuildingClass::UpdateTankBunker`.
3. **Open-Topped** — the transport system: passengers in
   `FootClass::Passengers` are marked `InOpenToppedTransport`, added to the
   **logic layer** via `TechnoClass::EnteredOpenTopped`, and **each fires its own
   weapon** at its own ROF/range/target. Vanilla restricts this to Vehicle /
   Aircraft transports.

**Why this page exists / the practical payoff.** A modder or DLL author who wants
"infantry inside a building, each firing its own weapon" is choosing between #1
(shared weapon → *Internal Error* when occupants have different ROF or range, and
mind-control breaks the arbitration) and #3 (per-passenger firing, no such
issues). Buildings do **not** run the open-topped firing loop today because their
infantry are in `Occupants`, not `Passengers` — see the "bridge" note below.

Entries sorted by address.

---

### `0x442D97` / `0x44DBA9` / `0x51A320` / `0x73A2F4` — Open-Topped **buildings** (Phobos PR #1879, unmerged)

**Framework names**
| Framework | Function name | Stolen | Channel | Source file |
|---|---|---|---|---|
| Phobos | `BuildingClass_DropDebris_DisableOpenTopped` | 0x6 | PR#1879 | src/Misc/Hooks.BugFixes.cpp |
| Phobos | `BuildingClass_MissionUnload_DisableOpenToppedForUnloading` | 0x6 | PR#1879 | src/Misc/Hooks.BugFixes.cpp |
| Phobos | `InfantryClass_PerCellProcess_SubmitToOpenToppedOnBuildingEnter` | 0x7 | PR#1879 | — |
| Phobos | `UnitClass_PerCellProcess_SubmitToOpenToppedOnBuildingEnter` | 0x6 | PR#1879 | — |

**What it does.** PR #1879 ("Implement open-topped building support and fix
building self-attack issue", @Metadorius) makes a building act as an open-topped
transport. The core move is at the **infantry/unit `PerCellProcess`
building-enter** point (`0x51A320` / `0x73A2F4`): when the occupier enters a
building flagged open-topped, it is *submitted to the open-topped system* — i.e.
registered as an open-topped passenger (added to the logic layer via
`EnteredOpenTopped`), so the ordinary per-passenger open-topped firing machinery
(`0x6FC5C7`, `0x6FE43B`, threat evals) then applies to it. The two disable hooks
suppress open-topped while the building is dropping debris / unloading so it does
not fire or mis-eject during those transitions.

**What it does *not* do — easily mistaken.**
- This is the **open-topped** route, **not** the garrison route. It does not touch
  `Occupants` / `FiringOccupantIndex`; it routes building infantry through
  `Passengers` + the logic layer instead. The two are mutually exclusive per
  building.
- It is an **open, unmerged PR** — these addresses are harvested from the PR, not
  from released Phobos. Do not assume a stock Phobos build has them.

**Confirmed via.** PR title + hook addresses from the Encyclopedia PR sweep
(`registry/pr-hooks.md`, PR#1879). PR body/source **not** read — mechanism above
is inferred from the hook names + the release-Phobos open-topped mechanism below,
and is **unverified against the PR diff**.

---

### `0x4DFD92` / `0x4DFED2` / `0x4E0024` — FootClass enter-validity: BattleBunker / GarrisonStructure / TankBunker

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `FootClass_FindBattleBunker_CheckValid` | 0x8 | src/Misc/Hooks.BugFixes.cpp |
| Phobos | `FootClass_FindGarrisonStructure_CheckValid` | 0x6 | src/Misc/Hooks.BugFixes.cpp |
| Phobos | `FootClass_FindTankBunker_CheckValid` | 0x8 | src/Misc/Hooks.BugFixes.cpp |

**What it does.** Three *separate* "find me a structure to enter" routines — one
per system (Battle Bunker, Garrison/UC, Tank Bunker). Their existence as three
distinct addresses is the clearest proof that the three occupancy systems are
independent in the binary. Phobos hooks each to add validity checks (bugfixes).

**What it does *not* do.** Sharing a validity fix across all three requires
hooking all three — a fix at one does not cover the others.

**Confirmed via.** Registry (release Phobos, `Hooks.BugFixes.cpp`). Function
intent inferred from names; bodies not quoted here.

---

### `0x447F10` — BuildingClass::CanFire: occupancy gates the building's OWN weapon ★ trap

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_CanFire_PrismForward` (`0x447FAE`, later in the same fn) | 0x6 | src/Ext/Building/Hooks.Prism.cpp |
| Phobos | `BuildingClass_CanFire_OmniFire` (`0x447FED`, PR#2104) | 0x7 | src/Ext/Techno/Hooks.Firing.cpp |

**What it does.** The head of `BuildingClass::CanFire` decides, *before any weapon
logic*, whether an occupiable building may fire at all:

```asm
447F15  mov  eax,[this+0x520]      ; ->Type
447F1B  mov  cl,[eax+0x157B]       ; CanBeOccupied
447F23  je   0x447F45              ; not occupiable -> normal path
447F25  mov  cl,[eax+0x157C]       ; CanOccupyFire
447F2D  je   0x44805A              ; occupiable + CanOccupyFire=no -> CANNOT FIRE
447F37  call [vtable+0x408]        ; GetOccupantCount()
447F3F  je   0x44805A              ; occupiable + zero occupants -> CANNOT FIRE
447F45  ...                        ; normal checks continue
```

**The trap (cost a full in-game test round).** `CanBeOccupied=yes` combined with
`CanOccupyFire=no` produces a building that **can never fire, at all** — not its
own weapon, not anything. It is easy to assume `CanOccupyFire` only governs
whether *occupants* shoot out; it does not, it also gates the building's own
`CanFire`. Symptom: a defensive structure that silently never shoots even when
fully garrisoned, with no error anywhere.

**Corollary — vanilla already implements "needs a crew".** With
`CanOccupyFire=yes`, line `0x447F3F` *is* "this building cannot fire while
empty", and `0x6FD17B` (see below) *is* "it fires faster with more men". Both are
stock RA2 behaviour; a DLL re-implementing them will duplicate, and a ROF hook
placed after `0x6FD183` will divide a **second** time.

**What vanilla will NOT do** is let an occupied building fire its *own* weapon —
see `BuildingClass::GetWeapon` `0x4526F0`, which routes to the occupant's
`OccupyWeapon` whenever `CanOccupyFire()` is true, and to the building's own
weapon only when it is false. Since `CanOccupyFire=no` also kills firing outright,
**no INI configuration yields "garrisoned building shoots its own Primary="**.
That specific gap is what a DLL has to supply, by forcing the `0x4527B4` branch.

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` for every branch above,
plus an in-game observation (2026-08-22) of a `CanBeOccupied=yes` +
`CanOccupyFire=no` pillbox that would not fire when fully occupied.

---

### `0x457CE0` / `0x4581F0` / `0x458DD0` — the garrison entry gate and the two occupancy virtuals

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares / Ares | `BuildingClass_CanBeOccupied_SpecificOccupiers` (`0x457D58`) | 0x6 | src/Ext/Building/Hooks.Trenches.cpp |
| Antares / Ares | `BuildingClass_CanBeOccupied_SpecificAssaulters` (`0x457DB7`) | 0x6 | src/Ext/Building/Hooks.Trenches.cpp |

**What it does.** `BuildingClass::CanBeOccupiedBy(InfantryClass*)` at `0x457CE0`
(`ECX` = building, `[ESP+0x18]` = infantry → `ESI` = building, `EDI` = infantry)
decides whether a given infantryman may garrison a given building:

```asm
457CF9  mov  cl, [Type+0x157B]     ; CanBeOccupied
457D01  je   fail
...
457D79  call [vtable+0x408]        ; live GetOccupantCount()
457D7F  mov  ecx, [building+0x520] ; -> BuildingTypeClass
457D85  cmp  eax, [Type+0x1580]    ; MaxNumberOccupants
457D8B  je   fail                  ; count == max -> full
```

**Verified `BuildingTypeClass` field offsets:** `+0x157B` = `CanBeOccupied`,
`+0x157C` = `CanOccupyFire`, `+0x1580` = `MaxNumberOccupants`. Building instance:
`+0x520` = `Type`, `+0x694` = `Occupants.Count`.

**The two virtuals** (BuildingClass vtable at `0x7E3EBC`):
- **`+0x408` → `0x4581F0` `GetOccupantCount()`** is exactly
  `mov eax,[ecx+0x694] / ret` — the **live** occupant count read off the building
  *instance*, not the Type.
- **`+0x400` → `0x458DD0` `CanOccupyFire()`** =
  `CanBeOccupied && CanOccupyFire && GetOccupantCount() > 0`.

**What it does *not* do — easily mistaken.**
- The capacity test is `count == MaxNumberOccupants → reject`, **not** `count >=`.
  So leaving `MaxNumberOccupants` at 0 rejects even an *empty* building
  (`0 == 0`), meaning nobody can ever enter. It must be > 0.
- Entry does **not** check `CanOccupyFire`. That flag only gates vanilla's
  occupy-*firing* (and the `0x6FD150` ROF block); infantry can still garrison a
  building with `CanOccupyFire=no`.
- `GetOccupantCount()` has nothing to do with `Passengers=` /
  `FootClass::Passengers.NumPassengers` — a completely separate container. This is
  the same garrison-vs-transport split described at the top of this page.
- The second `call [vtable+0x408]` at `0x457DCB` (requiring count **> 0**) is on
  the *assault* branch, not the occupy branch — which is why Antares hooks
  `0x457DB7` as `SpecificAssaulters`: you can only assault a building that has
  someone inside.

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` for every byte sequence
above; vtable base read out of the `BuildingClass` ctor (`0x43B740`,
`movl $0x7E3EBC,(%esi)`) and slots dereferenced from the image. Field *names* are
mapped from YRpp's declaration order (`BuildingTypeClass.h:215-217`) onto the
observed offsets — self-consistent across three independent call sites, but not
cross-checked against a symbol dump.

---

### `0x6FD150`–`0x6FD183` — TechnoClass::RearmDelay: the vanilla "more occupants = faster" divisor

**Framework names.** *Unhooked by any framework* in the region `0x6FD150`–`0x6FD17F`
(Phobos's hooks start at `0x6FD183`). Documented here because it is the engine
behaviour everyone means by "RA2 garrison buildings fire faster with more men."

**What it does.** Inside `TechnoClass::RearmDelay`, a clean `gamemd.exe` runs:

```asm
6FD150   call [vtable+0x400]   ; TechnoClass::CanOccupyFire()
6FD15A   test al, al
6FD15C   je   0x6FD1B1         ; NOT occupy-firing -> skip the ENTIRE bonus block
6FD15E   call [vtable+0x408]   ; TechnoClass::GetOccupantCount()
6FD168   test eax, eax
6FD16A   jle  0x6FD183         ; count <= 0 -> skip the divide
6FD170   call [vtable+0x408]   ; count again (not cached)
6FD17B   idiv ecx              ; rof = rof / occupantCount
6FD17F   mov  [esp+0x14], ebp
6FD183   ...                   ; then flat RulesClass::OccupyROFMultiplier (+0xF44)
```

So the rearm delay is **integer-divided by the live occupant count**, then divided
again by the flat `OccupyROFMultiplier`. Two `TechnoClass` virtuals drive it:
**`+0x400` = `CanOccupyFire()`**, **`+0x408` = `GetOccupantCount()`** (both
declared in YRpp `TechnoClass.h`, both `R0`).

**What it does *not* do — easily mistaken.**
- The bonus is gated on **`CanOccupyFire()`**, not on "has occupants". A building
  that merely has its own `Primary=` and some infantry inside does **not** reach
  this code and gets no scaling.
- The weapon fired on this path is the **occupant's** `InfantryTypeClass::OccupyWeapon`
  / `EliteOccupyWeapon` (cycled via `BuildingClass::FiringOccupantIndex`) — *not*
  the building's own weapon. "Building has a weapon, crew makes it fire" therefore
  needs extra work; only the ROF half is vanilla.
- `GetOccupantCount()` is called **twice** in a row without caching — harmless,
  but do not assume a cached value if you hook between them.

**Useful join point.** `0x6FD1B1` is where all paths reconverge, *after* the whole
occupy block and *before* the bunker block at `0x6FD1C7`. It is **unhooked by every
framework**, and on every incoming path `EBP` holds the current rearm delay,
mirrored at `[ESP+0x14]` (Phobos's bunker hook reads that stack slot, so write
both). Stolen bytes there are exactly `8B 86 E4 02 00 00` (`mov eax,[esi+0x2E4]`),
`ESI` = `TechnoClass*`. This is the clean place to add your own ROF scaling
without arbitrating Phobos at `0x6FD183`/`0x6FD1C7`.

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` (all bytes/branches above);
virtual names from YRpp `TechnoClass.h:305,307`; occupy-weapon fields from
`InfantryTypeClass.h:81-82`. Vtable slot→name mapping is *inferred* from the call
sites plus YRpp declaration order, **not** confirmed against a vtable dump.
**Used by** PayloadExt for a crewed-building weapon (gate + divisor); not yet
in-game verified.

---

### `0x6FD183` / `0x6FD1C7` / `0x6FE3F1` / `0x6FE421` — Garrison/Bunker firing modifiers (ROF & damage)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_RearmDelay_BuildingOccupyROFMult` | 0xC | src/Ext/BuildingType/Hooks.cpp |
| Phobos | `TechnoClass_RearmDelay_BuildingBunkerROFMult` | 0xC | src/Ext/BuildingType/Hooks.cpp |
| Phobos | `TechnoClass_FireAt_OccupyDamageBonus` | 0xB | src/Ext/BuildingType/Hooks.cpp |
| Phobos | `TechnoClass_FireAt_BunkerDamageBonus` | 0xB | src/Ext/BuildingType/Hooks.cpp |

**What it does.** The garrison ("Occupy") and Battle/Tank-Bunker firing paths get
their own **rate-of-fire** (`RearmDelay`) and **damage** multipliers, applied
inside `TechnoClass::FireAt` / `RearmDelay`. That there are *distinct* Occupy vs
Bunker variants again shows garrison ≠ bunker.

**What it does *not* do — easily mistaken.** These modify the **shared**
occupy/bunker weapon path. They are **not** the open-topped damage multiplier
(`0x6FE43B`, `InOpenToppedTransport`). An open-topped building would bypass these
entirely and use each passenger's own weapon/ROF.

**Confirmed via.** Registry (release Phobos, `Ext/BuildingType/Hooks.cpp`).

---

### `0x6FC5C7` — TechnoClass::CanFire (open-topped gate)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_CanFire_OpenTopped` | 0x6 | src/Ext/Techno/Hooks.Firing.cpp |

**What it does.** The gate that decides whether an open-topped **passenger** may
fire. Phobos extends it with per-transport options
(`OpenTopped_AllowFiringIfDeactivated`,
`OpenTopped_AllowFiringIfAttackedByLocomotor`,
`OpenTopped_CheckTransportDisableWeapons`). Keys on `pThis->InOpenToppedTransport`
and the transport's state.

**What it does *not* do.** Nothing to do with garrison `Occupants`; a garrisoned
building's shared-weapon fire is decided elsewhere. Enabling a building as
open-topped is what routes its infantry through *this* gate.

**Confirmed via.** Release Phobos source read directly
(`Ext/Techno/Hooks.Firing.cpp`, the `pTransport`/`pTypeExt` checks).

---

### `0x6FE43B` — TechnoClass::FireAt (open-topped damage multiplier)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_FireAt_OpenToppedDmgMult` | 0x8 | src/Ext/Techno/Hooks.Firing.cpp |

**What it does.** When the firer has `InOpenToppedTransport` set, applies
`RulesClass::OpenToppedDamageMultiplier` (overridable per-transport via Phobos
`OpenTopped_DamageMultiplier`). This is the open-topped analogue of the
Occupy/Bunker damage bonuses above.

**Confirmed via.** Release Phobos source read directly (the `InOpenToppedTransport`
branch reading `OpenToppedDamageMultiplier`).

---

### `0x6F7EC2` / `0x6F89F4` / `0x6F8FD7` / `0x6FA33C` — Threat-eval / target scan routed through the open-topped owner

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_ThreatEvals_OpenToppedOwner` | 0x5–0x6 | src/Ext/Techno/Hooks.Transport.cpp |

**What it does.** Four call sites (EvaluateObject / EvaluateCell / AI /
Greatest_Threat) that make an open-topped passenger's target evaluation defer to
its transport's position/owner, so passengers acquire sane targets from inside the
transport. This is what makes per-passenger open-topped firing actually pick
targets; a building put on the open-topped route inherits it.

**Confirmed via.** Registry + release Phobos (`Hooks.Transport.cpp`); the four
addresses share one function via `DEFINE_HOOK_AGAIN`.

---

### `0x6F72D2` / `0x6F7294` / `0x4D9510` / `0x71A82C` — Open-topped range/movement/temporal extras

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_IsCloseEnoughToTarget_OpenTopped_RangeBonus` | 0xC | src/Ext/Techno/Hooks.Transport.cpp |
| Phobos | `TechnoClass_InRange_OccupyRange` | 0x5 | src/Ext/Techno/Hooks.WeaponRange.cpp |
| Phobos | `FootClass_SetDestination_OpenToppedFireWhileMoving` | 0x6 | src/Ext/Techno/Hooks.Transport.cpp |
| Phobos | `TemporalClass_AI_Opentopped_WarpDistance` | 0xC | src/Ext/Techno/Hooks.Transport.cpp |

**What it does.** Open-topped range bonus (`OpenToppedRangeBonus`), fire-while-
moving, and temporal/warp-distance handling for passengers. Note `0x6F7294`
`TechnoClass_InRange_OccupyRange` is a separate **Occupy** range hook — occupy and
open-topped even have distinct range code.

**Confirmed via.** Registry (release Phobos).

---

### `0x6FC339` — TechnoClass::GetFireError (open-topped gunner temporal) — Antares/Ares

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_GetFireError_OpenToppedGunnerTemporal` | 0x6 | src/Misc/Bugfixes.cpp |
| Ares | `TechnoClass_GetFireError_OpenToppedGunnerTemporal` | 0x6 | src/Misc/Bugfixes.cpp |

**What it does.** Antares/Ares fix for an open-topped **gunner** (IFV) interaction
with temporal weapons at the fire-error check. Relevant to anyone combining
open-topped with `Gunner=yes`.

**Confirmed via.** Registry (Antares/Ares release). *(Antares ≠ Ares — see repo
README; both rows recorded because both frameworks hook it.)*

---

### `0x702A38` — TechnoClass::ReceiveDamage (open-topped) — Antares/Ares

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_ReceiveDamage_OpenTopped` | 0x7 | src/Ext/Techno/Hooks.cpp |
| Ares | `TechnoClass_ReceiveDamage_OpenTopped` | 0x7 | src/Ext/Techno/Hooks.cpp |

**What it does.** Damage routing/handling for open-topped passengers when the
transport takes damage. Useful when reasoning about survivability of infantry in
an open-topped building.

**Confirmed via.** Registry (Antares/Ares release).

---

### `0x7012DF` — TechnoClass::In_WeaponRange (open-topped) — Kratos

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Kratos | `TechnoClass_In_WeaponRange_OpenTopped` | 0x6 | src/Hooks/TechnoExtHook.cpp |
| Kratos | `TechnoClass_In_WeaponRange_OpenTopped_Passenger` | 0x6 | src/Hooks/TechnoExtHook.cpp |

**What it does.** Kratos's own open-topped weapon-range handling (two functions at
one address). Flag for potential collision with Phobos range hooks under a
Phobos+Kratos load.

**Confirmed via.** Registry (Kratos release). Interaction with Phobos range hooks
**not** analysed here — check `registry/conflicts.md` before stacking.

---

## Antares "Trenches" — the garrison-extension surface (release)

Antares (open-source Ares reimplementation) extends the **garrison** system in
`src/Ext/Building/Hooks.Trenches.cpp`. These are the hooks to layer on (never
fork) when *improving* the garrison path rather than replacing it with
open-topped:

| Address | Function | Stolen |
|---|---|---|
| `0x457D58` | `BuildingClass_CanBeOccupied_SpecificOccupiers` | 0x6 |
| `0x457DB7` | `BuildingClass_CanBeOccupied_SpecificAssaulters` | 0x6 |
| `0x4581CD` | `BuildingClass_UnloadOccupants_AllOccupantsHaveLeft` | 0x6 |
| `0x4586CA` | `BuildingClass_KillOccupiers_EachOccupierKilled` | 0x6 |
| `0x458729` | `BuildingClass_KillOccupiers_AllOccupantsKilled` | 0x6 |
| `0x52297F` | `InfantryClass_GarrisonBuilding_OccupierEntered` | 0x5 |

(Ares hooks the same addresses with the same names — both recorded.) `0x52297F`
`OccupierEntered` is the garrison analogue of PR#1879's open-topped
`SubmitToOpenToppedOnBuildingEnter` — i.e. the two systems' "an occupier just
entered" seams sit at *different* addresses, which is exactly how a DLL could
offer **both** garrison and open-topped as per-building toggles.

## The bridge: why buildings can't be open-topped without help

Release Phobos, `src/Ext/Techno/Body.Update.cpp` (~line 1234), comments:
> "OpenTopped does not work properly with buildings to begin with which is why
> this is here rather than in the Techno update one."

The mechanism it shows: `EnteredOpenTopped(passenger)` **adds the passenger to
the logic layer** (`LogicClass::Instance`) and sets `passenger->Transporter`, so
the passenger receives update ticks and fires. `ExitedOpenTopped` reverses it.
This only runs for units in `Passengers`. Buildings keep their infantry in
`Occupants`, so the loop never fires for them — hence PR#1879 must explicitly
submit building occupiers to the open-topped system at enter time.

**Confirmed via.** Release Phobos source read directly (`Body.Update.cpp`
passenger loop calling `EnteredOpenTopped`/`ExitedOpenTopped`). PR#1879's use of
this is inferred (PR diff not read).

## Related garrison/bunker update & unload hooks (release Phobos, reference table)

| Address | Function | Note |
|---|---|---|
| `0x458060` | `BuildingClass_ClearOccupants_Redraw` | occupant clear |
| `0x458180` | `BuildingClass_RemoveOccupants_CheckWhenNoPlaceToUnload` | unload safety |
| `0x458623` | `BuildingClass_KillOccupiers_Replace_MuzzleFix` | occupier muzzle fix |
| `0x459069` | `BuildingClass_UpdateTankBunker_CheckOccupants` | tank-bunker update |
| `0x459101` | `BuildingClass_UpdateTankBunker_RotateToTrack` | tank-bunker aim |
| `0x4593C7` | `BuildingClass_DestroyTankBunker` | tank-bunker destroy |
| `0x4596EC` | `BuildingClass_UnloadTankBunker` | tank-bunker unload |
| `0x447BE3` | `BuildingClass_DockingCoord_TankBunker` | tank-bunker docking |
| `0x44C976` | `BuildingClass_Mission_Repair_TankBunker` | tank-bunker repair |
| `0x70FB73` | `FootClass_IsBunkerableNow_Dehardcode` | de-hardcodes bunkerable check |
| `0x6FC3A1` / `0x6FC3AE` | `TechnoClass_CanFire_InBunkerRangeCheck` / `_TankInBunker_LocomotorWarhead` | bunker fire gating |

All from release Phobos unless a Channel says otherwise. Addresses are ⚠ until
re-derived from vanilla `gamemd.exe` in Ghidra; names/subsystems are from the
registry (harvested from upstream source).
