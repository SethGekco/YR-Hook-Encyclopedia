# BuildingClass::Grand_Opening — free units and pad aircraft

Everything a finished building hands out lives in one function. It is crowded:
seven known framework hooks across Antares/Ares/Phobos sit inside it, and the two
vanilla blocks it contains are back-to-back with no clean seam between them.

**Function.** `BuildingClass::Grand_Opening(bool captured)` — `thiscall`, `ret 4`.

**Frame.** Locals `0x58` + 4 saved registers (`ebx`/`ebp`/`esi`/`edi`) = `0x68` to
the return address, so the `captured` argument is at `[ESP+0x6C]` wherever ESP is
at the frame base. `EBP` holds `BuildingClass* this` throughout.

**Epilogue** at `0x446FB6`:

```
446fb6  5f              pop edi
446fb7  5e              pop esi
446fb8  5d              pop ebp
446fb9  5b              pop ebx
446fba  83 c4 58        add esp, 0x58
446fbd  c2 04 00        ret 4
```

**Layout.**

| Range | Block |
|---|---|
| `0x446AA9`–`0x446EE1` | FreeUnit — one VehicleType, one unit, `NearByLocation` placement |
| `0x446EE2`–`0x446FB5` | Pad aircraft — one aircraft from `Rules->PadAircraft[0]` |
| `0x446FB6` | epilogue |

---

### `0x446AAF` — Grand_Opening, free-unit block entry

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Place_SkipFreeUnits` | 0x6 | src/Ext/SWType/Hooks.Legacy.cpp |
| Ares | `BuildingClass_Place_SkipFreeUnits` | 0x6 | src/Ext/SWType/Hooks.Legacy.cpp |

**What it does.** This is the **once-only guard**. Antares/Ares set
`BuildingExt::FreeUnits_Done` on first visit and return `0x446FB6` on every visit
after, so a building that re-opens cannot hand out its free units twice.

**What it does *not* do — easily mistaken.** It is not a general "free unit"
extension point. It returns `0x446FB6` — the function epilogue — which skips
**both** the free-unit block *and* the pad-aircraft block. A third-party hook
chained here that assumes it only guards free units will silently lose pad
aircraft on the second visit.

**Useful consequence.** A DLL that wants to extend free units should sit *below*
this address rather than replacing it: the duplicate-delivery protection then
comes for free, with no need for a `BuildingClass` instance extension just to
remember "already delivered".

**Confirmed via.** Antares source (`Hooks.Legacy.cpp`, hook body read directly);
`registry/hooks.csv`. Vanilla layout from objdump of `gamemd.exe`.

---

### `0x446AB5` — free-unit null test (unhooked by any framework)

```
446ab5  85 c0                 test eax, eax          ; eax = pType->FreeUnit
446ab7  0f 84 25 04 00 00     je   0x446ee2
```

`EBP` = `BuildingClass*`, `EAX` = `UnitTypeClass*`, `ECX` = `BuildingTypeClass*`.

**Why it matters.** Vanilla parses `FreeUnit=` into a **single
`UnitTypeClass*`** (`BuildingTypeClass` +0xEA0). Anything that is not a
VehicleType — infantry, aircraft, a comma list — leaves that pointer NULL and the
**entire block is skipped here**, before any later hook in the block can run.

So any extension that wants `FreeUnit=` to accept infantry or a list must
intervene at or above this test. A hook of size `0x8` swallows both instructions
and can re-implement the branch. `EAX` is dead afterwards — the spawn code at
`0x446B78` re-reads `[ecx+0xEA0]` fresh — so overriding the branch does not
require preserving it.

**Confirmed via.** objdump of vanilla `gamemd.exe`; `BuildingTypeClass.h:136`
(`UnitTypeClass* FreeUnit`). Used by FreeUnitExt; **not yet exercised in-game.**

---

### `0x446B16` — after the full free-unit guard chain (unhooked)

```
446b16  8b 45 00     mov eax, [ebp]
446b19  8d 4c 24 1c  lea ecx, [esp+0x1c]
```

**What is above it.** Every guard vanilla applies to free units:

| Address | Guard |
|---|---|
| `0x446AAF` | Antares/Ares once-only `FreeUnits_Done` |
| `0x446ABD` | `Unsorted::ScenarioInit` — nothing spawns during map load |
| `0x446ACA` | the `captured` argument — a captured building gives nothing |
| `0x446AD6` | global `0xA8ED6B` (**unidentified**) |
| `0x446AE3`–`0x446B10` | house check (`0x50B730`) + `[ebp+0x300]` vs type vtable `+0xAC` (**not fully decoded**) |

**Why it is the good seam.** A hook here inherits all of the above rather than
re-deriving it, which matters because two of those guards are still not fully
understood. Returning `0x446EE2` from here skips the vanilla spawn and lands on
the pad-aircraft block.

**What that skips.** Phobos' `NearByLocation` fixes at `0x446BF4` / `0x446D42`,
Antares' `Harvester ? Harvest : Area_Guard` mission fix at `0x446E9F`, and
Phobos' `FreeWeeder` mission at `0x446EAD`. A replacement spawner must reproduce
the mission behaviour or free harvesters will sit idle.

**Confirmed via.** objdump; Phobos + Antares sources for the bypassed hooks.
**Unverified in-game.**

---

### `0x446EE2` — pad-aircraft block entry / InitialPayload

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Place_InitialPayload` | 0x6 | src/Ext/Techno/Hooks.cpp |
| Ares | `BuildingClass_Place_InitialPayload` | 0x6 | src/Ext/Techno/Hooks.cpp |

**What it does.** Delivers `InitialPayload=` and **returns 0**, letting the
vanilla aircraft block run afterwards.

**What it does *not* do — easily mistaken.** It does **not** take over the
aircraft block. Because it returns 0, a third-party hook that claims this address
and returns non-zero, *or* that jumps past `0x446EE2` from the free-unit block,
will silently kill `InitialPayload` — with no error and no crash. The symptom is
"InitialPayload stopped working" long after the change that caused it.

**Safe alternative.** Hook `0x446EE8` instead (see below): one instruction later,
unclaimed, and by then the payload has already been delivered.

**Confirmed via.** Antares source, hook body read directly; `registry/hooks.csv`.

---

### `0x446EE8` — `Rules->SeparateAircraft` test (unhooked)

```
446ee8  8a 81 e8 17 00 00     mov al, [ecx+0x17e8]   ; ecx = RulesClass::Instance
```

`EBP` = `BuildingClass*`, `ECX` = `RulesClass::Instance`, `[ESP+0x6C]` =
`captured`. `RulesClass::SeparateAircraft` is at **+0x17E8**.

**Vanilla behaviour from here.** Bail if `Rules->SeparateAircraft`; bail if
`!Type->Helipad` (`BuildingTypeClass` +0x154E); bail if `captured`; otherwise
create exactly **one** aircraft:

```
ScenarioInit++
pAircraft = new AircraftClass(Rules->PadAircraft[0], pBld->Owner)   ; ALWAYS index 0
pAircraft->Unlimbo(pBld->GetCoords(), PoseDir())
pAircraft->QueueMission(Mission::Guard /*5*/, false)
pAircraft->SendCommand(RadioCommand::RequestLink /*2*/, pBld)
pBld->SendCommand(RadioCommand::RequestTether /*0x18*/, pAircraft)
ScenarioInit--
```

**Three things worth knowing.**

1. **`PadAircraft[0]` only.** Vanilla reads `Rules->PadAircraft` (a
   `TypeList<AircraftTypeClass*>` at `RulesClass` +0xB5C) and takes index 0
   unconditionally — it is *not* per-house or per-dock. `NumberOfDocks` has no
   effect here; a four-pad structure still gets one aircraft.
2. **The two radio commands are the pad attachment.** Skipping
   `RequestLink`/`RequestTether` yields an aircraft that never rearms. Any
   replacement spawner must reproduce both.
3. **The `ScenarioInit` bracket spans the whole spawn**, not just the allocation
   (`0x446F21` increments, `0x446FB0` decrements). `Unlimbo` would otherwise
   refuse a cell occupied by the building itself.

**Interaction.** Phobos hooks `0x446F57` for pose-dir context and replaces the
`PoseDir` call at `0x446F67` via `DEFINE_FUNCTION_JUMP(CALL, …)`, which is what
makes `AircraftDockingDirs=` work. A hook at `0x446EE8` that returns `0x446FB6`
bypasses both, so per-dock landing directions must be supplied another way.

**Confirmed via.** objdump of vanilla `gamemd.exe` (`0x446EE2`–`0x446FBD`);
YRpp offsets (`RulesClass.h:558,905`, `BuildingTypeClass.h:270,317`);
`GeneralDefinitions.h` for `RadioCommand`/`Mission` values. Phobos source for the
`0x446F67` call replacement. **Not yet exercised in-game.**

---

## Cross-cutting note: this function is a chaining minefield

Three separate "skip to the end" behaviours coexist here — Antares'
`0x446FB6` return at `0x446AAF`, the vanilla `je 0x446EE2` at `0x446AB7`, and the
vanilla bails throughout the aircraft block. `registry/conflicts.md` cannot see
any of it, because these are *different addresses in the same function* rather
than address-equality collisions.

The general rule that fell out of writing FreeUnitExt against it: **hook below
the guards you want, not at the block entry.** Every entry point in this function
is either claimed or load-bearing.
