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

### `0x710470` / `0x7104A0` — TechnoClass::Entered/ExitedOpenTopped: how a passenger keeps firing

**Framework names.** Unhooked by any framework; documented because it is the
mechanism behind every "make X fire out of Y" feature.

**What it does.** `EnteredOpenTopped(pWho)` @`0x710470` is only three steps:

```asm
71047D  mov byte [pWho+0x82],1   ; ObjectClass::InOpenToppedTransport = true
710484  call [pWho_vtable+0x3D0] ; virtual on the passenger
71048D  mov ecx,0x87F778         ; LogicClass::Instance
710492  call 0x55BAA0            ; AddObject(pWho)
```

The essential part is the **logic-layer registration**: a passenger is limboed
inside its transport and would otherwise stop receiving `Update()` ticks, so the
engine adds it to `LogicClass::Instance` to keep it alive and firing. The flag at
`+0x82` is what the open-topped firing/targeting hooks key on (`0x6FC5C7`
CanFire, `0x6FE43B` damage multiplier, the `ThreatEvals_OpenToppedOwner` sites).
`ExitedOpenTopped` @`0x7104A0` reverses it.

**What it does *not* do — easily mistaken.**
- It does **not** set `Transporter`. The passenger's `Transporter` must be
  assigned separately or the open-topped paths have no transport to reason about
  (Phobos's own type-conversion path sets it explicitly alongside these calls).
- The `this` pointer is **unused** — YRpp notes *"this should be the transport,
  but it's unused"*. That is genuinely useful: exit handling can be driven from
  the passenger alone, using its stored `Transporter` as the receiver, without
  having to recover the transport from a register.
- It is not restricted to vehicles in any way; it works on any techno. Buildings
  simply never call it, because their infantry live in `BuildingClass::Occupants`
  rather than `Passengers`.

**Used successfully by** PayloadExt to give BuildingTypes BFRT-style open-topped
behaviour: call it on each occupant at the garrison-entry site `0x52297F`
(EBP = building, ESI = the infantry just appended to the vector) and reverse it in
the unload loop at `0x4580BD` (`EDI` = `Occupants.Items[EBP]`, loaded at
`0x4580B1`). Note `0x458197` is **only** the "nowhere to place it" failure branch
of that loop, so hooking there misses normal exits.

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` for all bytes above.
Not yet in-game verified.

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

## The complete `Occupier=` gate map — every site that can refuse entry

**Source.** PayloadExt, 2026-09-14. Exhaustive: found by disassembling
`gamemd.exe` and grepping every access to `InfantryTypeClass+0xEB4` (`Occupier=`)
and `+0xEB5` (`Assaulter=`). Offsets objdump-verified.

Widening garrison admission needs **all** of these, not just `CanBeOccupiedBy`.
They are independent gates at different stages, and the later ones are never
reached if an earlier one refuses.

| Address | Function (vtable slot) | Role | Bail target | Proceed target |
|---|---|---|---|---|
| `0x457D4E` | `BuildingClass::CanBeOccupiedBy` (`0x457CE0`) | the nominal decision | `0x457DAD` assault branch | `0x457D58` |
| `0x51F489` | `InfantryClass::Mission_Attack` (slot `+0x210`) | per-frame: convert "attack this building" into garrisoning | — | `0x51F49D` |
| `0x519698` | `InfantryClass::UpdatePosition` | arrival | — | `0x5196A6` |
| `0x522920` | `InfantryClass::GarrisonBuilding` | the actual entry | — | `0x52292C` |
| `0x4D4B96` | `FootClass::Mission_Capture` (slot `+0x214`) | sets the Destination — but only reachable when Destination is null (see below) | `0x4D4BC7` | `0x4D4BB4` |
| `0x51F576` | `InfantryClass::Mission_Hunt` (slot `+0x228`) | AI: objective → `ForceMission(Capture)` | `0x51F5C0` | `0x51F58A` (→`CanBeOccupiedBy`) / `0x51F59A` (skip) |
| `0x4D9A83` | near `SelectAutoTarget` (`0x4D9920`) | destination retention while `mission==8` | falls through to generic set at `0x4D9ABD` | — |
| `0x6F8322` | `TechnoClass` threat/target eval | AI scoring of garrisonable targets | `0x6F833C` | calls `0x457CE0` |

### `0x4D4B96` — a real gate, but usually UNREACHABLE (corrected 2026-09-14)

⚠ **First published here as "the one that bites". That was wrong; corrected after
testing.** It IS a genuine gate, but only when `Destination` is null. The player
path sets the destination first — `Mission_Attack`'s success path at `0x51F4AD` does
**`SetDestination(building,1)` then `ForceMission(8)`** — and Mission_Capture branches
away at `0x4D4B5F` (`mov eax,[esi+0x5A4]; test eax,eax; jne 0x4D4C14`) whenever a
Destination already exists. Verified empirically: a garrison that WORKS (E1 into a
Battle Bunker) produces no trace through `0x4D4B96` at all.

Note also that the `0x4D4C14` branch is nearly inert — with a live target it falls
straight to `0x4D4C71` and only returns a delay. The walking is driven by the
Destination in the FootClass update, not by Mission_Capture.

**Garrisoning runs as `Mission::Capture` (=8), not `Mission::Enter`.**
`ActionOnObject` merely force-missions Capture and stores the objective;
`FootClass::Mission_Capture` does the walking. Its gate:

```
4d4b43  mov ecx,[esi+0x2B4]        ; objective
4d4b4f  call [edx+0x2C]            ; WhatAmI() == 6 (Building)?
4d4b57  mov eax,[esi+0x5A4]        ; already have a Destination -> 4d4c14
4d4b96  mov al,[edi+0xEB4]         ; Occupier   -> jne 4d4bb4
4d4ba0  mov al,[edi+0xEB5]         ; Assaulter  -> jne 4d4bb4
4d4baa  mov al,[edi+0xEBE]         ;            -> je  4d4bc7   BAIL
4d4bb4  SetDestination(objective, 1)          ; THE WALK
```

Bailing skips `SetDestination`, so the infantry keeps the Capture mission with a
**null Destination and simply stands still**. Symptom: the cursor offers "enter",
the order is accepted with its confirmation, and the unit never moves. Every
other gate above is downstream, so none of them ever fire — which makes this
failure mode look like "the order is being silently dropped".

**Registers at `0x4D4B96` — read carefully.** The prologue is a branchless
`abstract_cast<InfantryClass*>`:

```
mov edi,eax / sub edi,0xF / neg edi / sbb edi,edi / not edi / and edi,esi
```

`EDI = (WhatAmI()==Infantry) ? this : NULL`, null-rejected at `0x4D4B67`. But
`0x4D4B86` **reassigns EDI to the Type**, so at `0x4D4B96` `EDI` is an
`InfantryTypeClass*` and the instance is **`ESI`**. Taking EDI as the infantry
here silently reads garbage. Stolen bytes = the whole 6-byte `mov`.

### Identifying the mission slots

`InfantryClass` vtable = **`0x7EB058`** (assigned in the ctor at `0x517ACC` /
`0x521A11`; `0x7EB03C` is the secondary/vector-deleting table). Anchoring
`MissionClass`'s declared virtual order at `+0x204 = Mission_Sleep` gives
`+0x214 = Mission_Capture` and `+0x228 = Mission_Hunt`. Corroborated
independently: `0x51F540` (slot `+0x228`) ends in `SetDestination(building,1)` +
`ForceMission(8)`, and `Mission::Capture == 8`.

### Field notes

- `InfantryTypeClass+0xEBE`, `+0xEC2`, `+0xEC3` are additional unnamed entry
  flags tested alongside `Occupier`. `+0xEBE` is notable because at `0x51F574`
  the engine uses it to jump **past** `CanBeOccupiedBy` entirely — so anything
  setting it bypasses every occupancy whitelist.
- `Occupier`'s INI default **cannot be read statically**: `0x5244CE` does
  `mov al,[esi+0xEB4]` and passes that as the default to the read, so the value
  is whatever the ctor or an inheritance pass left. Log it at runtime instead of
  inferring it from rules.

## ★ The gate that actually decides player-ordered garrisoning: `C4=`

**Source.** PayloadExt, 2026-09-19, in-game A/B verified in both directions.
This is the single most load-bearing fact on this page for anyone widening
garrison admission, and it is *not* `Occupier=`.

**`InfantryTypeClass::C4` = `+0xEC2`** (INI key `"C4"` at `0x825978`; read at
`0x524545`, stored at `0x524559`).

It guards the whole "convert my building target into garrisoning it" branch, at
the **top** of both mission handlers — before the target is even examined:

```
Mission_Attack   0x51F3E9  mov cl,[Type+0xEC2]       ; C4?
                 0x51F3F1  jne 0x51F400              ; yes -> consider garrison
                 0x51F3F3  push 0xE / call 0x70D0D0  ; else HasAbility(14)?
                 0x51F3FE  je  0x51F456              ; neither -> never looks
Mission_Capture  0x4D4B6F  same shape   -> 0x4D4BB4 (SetDestination)
```

`0x70D0D0` is `HasAbility` (reads the veterancy struct at `techno+0x150` via
`0x74FF90`/`0x750010`), so the vanilla rule is **"C4 or the ability"**.

**Why this matters more than it looks.** `CanBeOccupiedBy` (`0x457CE0`),
`Mission_Attack`'s occupier test (`0x51F489`), `Mission_Capture`'s (`0x4D4B96`),
`UpdatePosition` (`0x519698`) and `GarrisonBuilding` (`0x522920`) **all sit
INSIDE this branch**. An extension that forces admission at any of them will see
its own logic report "admitted" and still observe nothing happen, because for a
non-C4 infantry the branch is never entered. Open this gate too.

**Verified in game, both directions:** a Navy SEAL (`C4=yes`, `Occupier` absent
⇒ 0 at runtime) garrisons happily; comment out its `C4=` and it stops. Add
`C4=yes` to a Guardian GI (`Occupier=no`) and it starts. A sniper with neither
never does. `Occupier=` is independently disproven as the differentiator: an
`Occupier=0` unit was logged entering and being appended to `Occupants`.

**The AI is unaffected** — `Mission_Hunt` (`0x51F540`, InfantryClass vtable slot
`+0x228`) has **no** C4 gate, which is why AI-hunted infantry garrison fine while
the same type refuses a player's click. If you are debugging this, make sure your
repro is a *player order*, not AI behaviour; they take different paths.

**Not the order-event path.** Worth recording to save the search: the dispatcher
at `0x4C73A5` obtains the mission via `call [vtable+0x4A4]` then queues it at
`0x4C73B9`, and for infantry that virtual (`0x4DF0E0`) only reads the mission
byte out of the event (`movsbl 0xC(%edi),%ebp`). Nothing type-specific happens
there, so it is not where units diverge.

## ★★ POST-MORTEM: forcing a non-Occupier to garrison on a PLAYER order — UNSOLVED

**Source.** PayloadExt, 2026-09-08 → 2026-09-24. Roughly twenty build/test rounds,
three vanilla regressions, then a deliberate rewind. Written up in full because
the *negative* result and the mechanism map are worth far more than another
attempt from scratch — and because everything that looked like the answer along
the way was wrong for a reason that is now explainable.

**The goal.** Let a BuildingType declare, in INI, that infantry without
`Occupier=yes` may garrison it, and have a player able to order such a unit in by
clicking. Admission itself was never the hard part.

### What is actually true (all verified in game, not inferred)

| Fact | Evidence |
|---|---|
| **Admission works.** `CanBeOccupiedBy` can be made to say yes for any type. | Overriding at `0x457D58` yields `ADMITTED` for a unit with `Occupier=0`. |
| **The whole downstream chain works once entry begins.** | A non-Occupier (Navy SEAL, `Occupier=0`, `C4=yes`) walks in, is appended to `Occupants`, is limboed, and fires. Log: `occupants=2/4 appended=1 inLimbo=1`. |
| **The AI path works and needs nothing.** | `Mission_Hunt` (`0x51F540`, vtable `+0x228`) has **no** `C4=` gate, so AI-hunted infantry garrison regardless of `Occupier=`. |
| **The player path is the only broken one.** | Same unit, same building: AI reaches `GarrisonBuilding`, a player order does not. |
| **`C4=` is the real player-side gate**, not `Occupier=`. | See the starred `C4=` section above — A/B verified in both directions. |

### Why the player path dies

`Mission_Capture` (`0x4D4B20`) is the mission a garrison order runs under
(`Mission::Capture == 8`, **not** `Mission::Enter`). For a non-Occupier it bails
before it ever reaches its own `SetDestination` at `0x4D4BB4`:

```
0x4D4B43  mov ecx,[this+0x2B4]   ; Target
0x4D4B4B  je  0x4D4BC7           ; null -> bail
0x4D4B6F  C4 || HasAbility(14)   ; else -> 0x4D4BB4
0x4D4B96  Occupier               ; else -> 0x4D4BB4
0x4D4BA0  Assaulter              ; else -> 0x4D4BB4
0x4D4BAA  +0xEBE                 ; none of the above -> 0x4D4BC7
0x4D4BB4  SetDestination(target,1)   ; THE ONLY CALL THAT STARTS THE WALK
0x4D4BC7  ... [vtable+0x484] -> re-derives the mission -> Guard
```

**Nothing else in the player path ever calls `SetDestination` for that unit.** The
order arrives with the mission correct and the `Destination` *field* sometimes
already populated, but the field being right is not the same as the move having
been dispatched — and the unit simply stands still. `Occupier` units move because
vanilla makes that call for them.

### Four approaches tried, and exactly how each failed

1. **Open the `Occupier`/`C4` gates** (`0x457D48`, `0x51F489`, `0x519698`,
   `0x522920`, `0x4D4B96`, `0x51F576`, `0x51F3E9`, `0x4D4B6F`).
   Read-only, harmless, still shipped — and **insufficient**: `0x4D4B43` bails on a
   null `Target` 0x2C bytes *before* the `C4` gate, so the gate is unreachable on
   the path that matters.
2. **Inject `Target`.** Worked mechanically; **broke the game**. `Target`
   (`+0x2B4`) is read by the attack logic *and* the order-line renderer, so the
   unit rendered an attack line and **shot the building it was sent to occupy**.
   A raw write also skips the bookkeeping the engine's `SetTarget` does
   (`0x51B2A2` resets `+0x5E0`; `0x51B25D`–`0x51B26D` relinks the targeting chain),
   leaving stale attack state that discharged one round before entry.
3. **Inject `Destination` instead.** Cleaner, and it got units in — but
   `Mission_Capture`'s cancel path (`0x4D4BC7` → `[vtable+0x484]`) drops the mission
   again, so the order had to be re-asserted every frame, which is a fight rather
   than a fix.
4. **Raise the engine's own garrison-seek flag, `FootClass+0x691`.**
   The dispatcher at `0x4D5070`, reached from `Mission_Guard` (`0x51F62F`), calls
   `FindGarrisonStructure` (`0x4DFE00`) while the flag is set; that function
   consults `CanBeOccupiedBy`, so a forced occupant *is* accepted. This is the most
   vanilla-shaped route and it did produce entries. It still failed, twice over:
   - **`FindGarrisonStructure` picks the NEAREST valid structure, not the one
     clicked.** Units ordered into one building walked to another; unsupervised, they
     shopped around whenever the intended one filled or was sold.
   - **`GarrisonBuilding` clears both seek flags on entry** (`0x5229F4` for `+0x691`,
     `0x5229FA` for `+0x690`). Re-asserting the flag past that boundary made units
     **walk straight back out of the building they had just entered.**

### The three vanilla regressions, and the rule that prevents them

Each was introduced by a fix for the previous one — the signature of a wrong
approach rather than an incomplete one.

| Regression | Cause |
|---|---|
| Infantry shot the building they were sent to occupy | wrote `Target`, which is also the attack field |
| `E1` could no longer garrison **civilian** buildings at all | an intent record naming an ungoverned building made a state machine **cancel the player's order** |
| `E1` ignored orders and entered whichever building was **nearest** | a per-frame destination pin fighting `FindGarrisonStructure` |

> **RULE. A hook may ANSWER QUESTIONS — return a branch target, report a verdict —
> but must not WRITE state the engine owns.**
>
> In PayloadExt every feature that works obeys this (the permission matrix,
> RA2-mode garrison, open-topped buildings, the per-entry ROF/Firepower/Range
> modifiers). Every vanilla break violated it. `Target`, `Destination` and
> `+0x691` are all owned by the engine, are all read by more systems than they
> appear to be, and are all cleared at lifecycle boundaries you must know about
> before writing them.

### Two traps that cost whole rounds and are not obvious

- **`CanBeOccupiedBy` has NINE callers, and one is an exhaustive engine search.**
  `FindGarrisonStructure` walks the entire building array asking about every
  candidate (`0x4DFE54`). Recording "the building we were asked about" therefore
  gets clobbered by the engine's own scan within a frame. If intent matters, gate
  on the caller's return address — `0x51E699` is the call inside
  `InfantryClass::WhatAction`, i.e. the cursor query, the only caller that means
  "a human pointed at this".
- **Setting a state field is not invoking the action that consumes it.**
  `Destination` reading back correct proves nothing; something must *call*
  `SetDestination` to start the locomotor. Verify the side effect fired, not that
  the value looks right.

### Diagnostic method, for the next attempt

The investigation only converged once one run could answer everything. Three
properties did it, and their absence is what wasted the earlier rounds:

1. **Per-subject budgets.** A global log budget is spent by common types (`E1`,
   `E2`) before the unit under test ever moves.
2. **Log on change.** Sample every frame, emit only on transition — a timeline,
   not thousands of duplicates.
3. **An automatic control.** Key tracking on "was asked about a governed building"
   and a *working* unit is captured in the same run as the failing one. The answer
   here was visible in two lines side by side:
   `E2 … seekGarrison=1` surviving 219 frames against `GGI … seekGarrison=0` wiped
   the next frame.

Corollary: **absence of a log line is only evidence when the run is known to
contain the event.** Three wrong conclusions in this investigation came from
reading silence as a finding.

### Where to start next time

Do **not** supply the missing `SetDestination` from outside — that is approach 3
and 4, and both fight the engine every frame. Look instead for a way to make
**vanilla itself** make the call: i.e. get a non-Occupier past `0x4D4B43`'s
null-`Target` bail *with a Target the engine set*, so the existing `C4`/`Occupier`
gates at `0x4D4B6F`/`0x4D4B96` (already hooked and harmless) carry it into
vanilla's own `SetDestination` at `0x4D4BB4`. The unanswered question that blocks
this is **why a player-issued Capture order arrives with a null `Target` at all**,
when the dispatcher at `0x4C7467` does call `SetTarget` with the event's decoded
target. Two attempts to name the responsible site (the event's mission byte at
`0x4DF0E0`; `SetTarget` at `0x51B1F0`) were both wrong, so treat that as open.

**Status.** Shipped as: permission matrix + `Deny=` blacklist, RA2-mode garrison,
open-topped buildings, per-entry modifiers — all working. Forced non-Occupier
entry on a player order: **removed, unsolved, documented here.**

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

## ★ Garrisoned infantry physically do not exist (Rex, 2026-09-21)

**Source.** Rex, from play; corroborated in YRpp + Phobos source the same day.

Once an occupier reaches the building it is **limboed and removed from the
map**, not merely hidden or moved inside the footprint. It survives only as a
pointer in `BuildingClass::Occupants`
(`DynamicVectorClass<InfantryClass*>`, BuildingClass.h:314), which is what
re-spawns the squad when the building is sold/undeployed or
`KillOccupants` (0x457xxx region, BuildingClass.h:193) runs.

**Consequences, all of which bite silently:**

- **They cannot be targeted or hit by anything position-based.** There is no
  object at those cells to find. A CellSpread sweep over a garrisoned building
  affects the *building*, never its occupants.
- **They cannot receive warhead effects at all**, including Phobos
  AttachEffects: `WarheadTypeExt::ExtData::DetonateOnOneUnit`
  (src/Ext/WarheadType/Detonate.cpp:200) early-returns on
  `pTarget->InLimbo` before any effect is applied. Both the CellSpread route
  and the bullet-target route end there.
- **Do not use "infantry in a garrison" as a test case for cell-overlap
  bugs** — it proves nothing, because the infantry are not on the map. Use
  units sharing a cell, units on a bridge, or aircraft over a structure
  instead.
- Anything iterating technos to apply per-unit state (stances, hold-fire
  flags, buffs) will **skip garrisoned infantry entirely**. If that state must
  survive garrisoning, it has to be stored against the infantry object and
  re-applied on exit, not swept over the map.

See also [[yr-hunt-is-an-ai-mission]] for the other "the order is accepted and
nothing happens" failure shape.

## Appendix: the click-mode system (beacon / waypoint / sell / repair)

**Source.** CommandBarExt, 2026-09-24, while designing a map-drawing tool.
Recorded here because it is the template for ANY "click the bar, then click
the battlefield" feature.

YRpp already names the entry points on MapClass/DisplayClass (`0x87F7E8`):

| Address | YRpp name |
|---|---|
| `0x4AC960` | `SetPlaceBeaconMode(int mode)` |
| `0x4AC700` | `SetWaypointMode(int mode, bool)` |
| `0x4AC660` | `SetSellMode(int mode)` |
| `0x4AC8C0` | `SetRepairMode(int mode)` |
| `0x4AC820` | `SetTogglePowerMode(int mode)` |

`mode` is **-1 = toggle, 0 = off, 1 = on** (decoded from 0x4AC960's prologue).

**Mode flags are bytes on the display class:**
`+0x11B0` beacon, `+0x11B1` repair, `+0x11B2` sell, `+0x11B8` (dword, -1 when
idle), `+0x11A8` (dword). `0x4AC310` is the "is any special click mode
active?" predicate and tests all of them in sequence — a good place to make a
custom mode visible to the rest of the UI.

**Command plumbing:** `BeaconPlacementCommandClass::Execute` is `0x5370A0`; it
guards on session type (`0xA8B238`) then calls `0x731A30`, which is the shared
"enter beacon mode" thunk that the AdvancedCommandBar's Beacon button also
calls (from the Update dispatcher at `0x6D0742`). So a bar button and a hotkey
command converge on one routine — mirror that shape for custom modes.

**Drag capture** (for a paint/drag tool rather than a single click) lives in
`DisplayClass::LeftPressAndDragging`; Phobos PR#1993 takes `0x4AC4B9` (drag
start), `0x4AC411` (drag update) and `0x4ABCA7` (drag end) for its distribution
range. Those seats are unmerged, so free — but note the open problem: a drag
on the tactical map also runs band-box selection, so a drawing tool must
suppress that while its mode is active.

### Where a click in a special mode is consumed

`DisplayClass::LeftMouseButtonUp` = **0x4AC20C** (PDB-named; the neighbouring
`0x4ABFBE DisplayClass_LeftMouseButtonUp_ExecPowerToggle` shows each special
mode dispatching from here). This is the seat for consuming a click while a
custom mode is active.

**Beacon placement is EVENTED, and that is the template to copy.** At 0x4AC22C
the handler builds an `EventClass` of type **0x12** via `0x4C6B60` and pushes
it onto `OutList` — complete with the same `cmp OutList.Count,0x80` drop check
and the `and edx,0x7f` ring mask documented in
[[yr-outlist-128-event-ceiling]]. So a player placing a beacon does not mutate
game state locally; it travels as an event.

Any custom map-placement tool that changes SIMULATION state (a pathfinding
no-go zone, for instance) must do the same or it desyncs — see
[[yr-iscelloccupied-is-the-per-unit-path-gate]].
