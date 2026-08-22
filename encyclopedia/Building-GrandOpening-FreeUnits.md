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

### `0x446AE3` — ⚠ free units are SILENTLY SUPPRESSED for human players

```
446ae3  8b 8d 1c 02 00 00     mov ecx, [ebp+0x21c]   ; pThis->Owner
446ae9  e8 42 4c 0c 00        call 0x50b730          ; HouseClass::IsControlledByHuman
446aee  84 c0                 test al, al
446af0  74 24                 je   0x446b16          ; NOT human -> spawn
446af2  8b 85 00 03 00 00     mov  eax, [ebp+0x300]
446af8  85 c0                 test eax, eax
446afa  74 1a                 je   0x446b16          ; zero -> spawn
446afc  8b 8d 20 05 00 00     mov  ecx, [ebp+0x520]  ; pThis->Type
446b04  ff 92 ac 00 00 00     call [edx+0xac]        ; BuildingTypeClass virtual
446b0a  39 85 00 03 00 00     cmp  [ebp+0x300], eax
446b10  0f 8e cc 03 00 00     jle  0x446ee2          ; SKIP free units
```

In C:

```c
if (Owner->IsControlledByHuman()
    && pThis->[0x300] != 0
    && pThis->[0x300] <= pType->vtable[0xAC]())
    goto no_free_units;
```

**`0x50B730` is `HouseClass::IsControlledByHuman()`** = `IsHumanPlayer ||
IsInPlayerControl`. YRpp carries the address in a comment at
`HouseClass.h:492`, so this one needs no reverse engineering — just look it up.

**Why this matters more than it looks.** The condition is gated on the owner
being *human*. An AI house skips the whole test at `0x446AF0` and always gets its
free unit. So a `FreeUnit=` that works perfectly when you watch an AI base can
produce **nothing at all** for the player, with no error, no log, and no crash.

Observed directly while building FreeUnitExt: across a full skirmish, every
free-unit delivery logged `owner=Germans` or `owner=Russians` and never the
human player — while the player's *Refinery* still delivered its harvester. So
the guard is conditional, not a blanket human block; `[ebp+0x300]` differs
between building types in a way that lets Refineries through.

**Still unidentified:** `BuildingClass+0x300`, and the `BuildingTypeClass`
virtual at vtable slot `0xAC`. Naming these would explain exactly which
buildings vanilla intends to suppress.

**Consequence for extensions.** If you are replacing the free-unit spawn and you
want it to work for the player, hook at or above `0x446AE3` and bypass this
guard. Hooking below it (e.g. at `0x446B16`, which otherwise looks like the
ideal seam because every guard sits above it) inherits the suppression. That is
a real mistake that was made and then corrected in FreeUnitExt.

The guards you probably DO want are all above `0x446AE3`: Antares' once-only
guard (`0x446AAF`), `ScenarioInit` map-load suppression (`0x446ABD`), and the
`captured` argument (`0x446ACA`).

**Confirmed via.** objdump of vanilla `gamemd.exe`; `HouseClass.h:492` for the
`0x50B730` identification; and **in-game logging** of the owning house for every
delivered unit, which is what exposed the AI/human split. Behaviour after
bypassing the guard confirmed in-game: four infantry per barracks for the human
player.

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

### `0x417FD0` — `AircraftClass::PoseDir` — and the `[General]PoseDir=` trap

The whole function:

```
417fd0  a1 e0 71 88 00     mov eax, [0x8871e0]   ; RulesClass::Instance
417fd5  8b 40 44           mov eax, [eax+0x44]   ; Rules->PoseDir
417fd8  c3                 ret
```

It returns the field **raw** and the caller hands it straight to `Unlimbo` as a
`DirType`.

**The trap.** `rulesmd.ini` documents the tag as
`PoseDir=2 ; aircraft landing facing (0=N, 1=NE, 2=E, etc)`, which reads like an
8-step compass index. **It is not.** The parser at `0x669262` stores it with no
scaling at all:

```
669258  mov ecx, [esi+0x44]      ; existing value as the default
669262  push "PoseDir"
66926a  call ReadInteger
66926f  mov [esi+0x44], eax      ; stored RAW
```

Contrast the very next field at `+0x48`, which *is* an 8-step index and is
visibly scaled on both sides of the same read:

```
669272  mov eax, [esi+0x48]
66927b  sar eax, 5               ; /32 to produce the default
...     call ReadInteger
66928c  shl eax, 5               ; *32 on store
```

So stock `PoseDir=2` produces `DirType` 2 — about 3 degrees off north — not east.
The INI comment describes an encoding the code does not implement. Anyone
reimplementing the pad-aircraft spawn should pass `Rules->PoseDir` through
unscaled (which is what Phobos' `AircraftExt::GetLandingDir` does), and should
not "fix" it by multiplying by 32.

**Confirmed via.** objdump of vanilla `gamemd.exe` at `0x417FD0` and `0x669262`
(the `PoseDir` string ref from `registry/vanilla-tags.csv` → `0x83abb8`);
cross-checked against Phobos `AircraftExt::GetLandingDir`. The *consequence*
(aircraft face north, not east) is derived from the code and **not yet visually
confirmed in-game**.

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
