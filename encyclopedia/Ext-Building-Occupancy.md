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
