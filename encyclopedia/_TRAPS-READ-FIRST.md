# Cross-cutting traps — read this before hooking anything

Every entry here cost a real debugging round, and **most of them cost it more than
once**, because the knowledge lived on a page nobody thought to open. They are
collected here precisely because they are *not* about any single address.

This page is deliberately short. Each item states the trap, the tell, and where
the full write-up lives.

---

## 1. The framework may have replaced the whole function

An Ares-lineage framework or Phobos frequently **replaces** a function outright:
its handler computes a value, writes `EAX`, and `return`s an address past the
vanilla body. Anything you hook *inside* that body is **dead code**, and nothing
warns you — your handler simply never fires.

**Known full replacements in the buildability/production path alone:**

| Address | Function | Owner |
|---|---|---|
| `0x4F7870` | `HouseClass::CanBuild` | Antares / Ares |
| `0x5F7900` | `ObjectTypeClass::FindFactory` | Antares |
| `0x6F47A0` | `TechnoClass::GetBuildTime` | Antares / Ares |
| `0x711EE0` | `TechnoTypeClass::GetBuildSpeed` | Antares / Ares |
| `0x500910` | `HouseClass::GetFactoryCount` | Phobos |
| `0x50B370` | `HouseClass::ShouldDisableCameo` | Antares / Ares |

**The tell:** your feature parses correctly and then does nothing at all.

**The remedy:** hook the framework's own **jump target** (the epilogue) and
post-process there. `0x4F8361` and `0x6F4955` are working examples. But check the
epilogue's geometry first — see trap 3.

⚠ **A replacement also means the framework's readers are the live ones, not
vanilla's.** Counting `test eax,eax` sites in `gamemd.exe` will mislead you if
several of them sit inside a replaced function. Read the framework's source.

Pages: [Buildability-Prerequisites.md](Buildability-Prerequisites.md),
[Production-Queues-Factories.md](Production-Queues-Factories.md).

---

## 2. One function can be gated by a *different* function

Getting a function's return value right is not the same as changing the outcome.
`CanBuild` can correctly answer "no" while the cameo stays clickable, because
whether a cameo is *disabled* is decided by `ShouldDisableCameo` — a separate
function that never calls `CanBuild` at all.

**The tell:** the effect is half-applied. Something greys but still works;
a preview turns red but the action still commits.

**The remedy:** find *every* consumer of the decision, not just the obvious one.
Placement needed two seats for the same reason (preview and commit).

Pages: [Buildability-Prerequisites.md](Buildability-Prerequisites.md).

---

## 3. `return 0` is often a bug

The stub re-runs the **copied original bytes** after your handler. That is only
safe if those bytes are still valid to run. Three shapes break it — a stolen
relative branch, a stolen read of a register you just wrote, and a stolen `ret`
sitting in NOP padding (returning 0 walks into the next function).

⚠ In all three the hook's **geometry is perfect**, so size, boundary and overlap
checkers all pass it. The defect is control flow.

Full write-up: [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

---

## 4. Legal ≠ live (same-address co-hooks)

Syringe installs a second handler at an address without complaint. Whether it
**runs** is a separate question, and this repository holds two contradicting
in-game observations about it — see the ⚠ UNRESOLVED section of
[Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

**The rule that survives either answer:** emit a log line as the handler's
**first statement, before every bail**, and confirm you see it. A handler that
only logs on its success path is indistinguishable from a dead hook.

**The tell:** parsed correctly, then nothing — same tell as trap 1, which is why
you must be able to rule this out cheaply.

---

## 5. Verify the register at *that exact address*

Registers are not stable across a function. Copying `ECX = this` from a
neighbouring entry in the same function is how three separate silent failures
happened in one project. Read the reference implementation's handler **for the
address you are hooking**.

At an *epilogue* reached via a framework's `return`, the incoming registers are
the framework handler's **entry** registers, because YRpp's `REGISTERS` is a
`PUSHFD`/`PUSHAD` frame and the stub restores everything the handler did not
write. That is what makes `ECX` readable at `0x4F8361` and `0x6F4955` — but it
holds *only* while a framework really does replace the entry.

---

## 6. YRpp shapes that silently do nothing

- **`DEFINE_REFERENCE` globals are references, not pointers.** `HouseClass::Array`,
  `BuildingClass::Array`, `MapClass::Instance` — use `.`, not `->`. Three separate
  compile failures in one session; it reads as a pointer everywhere else.
  The second shape of the same mistake is **calling one**: `RulesClass::Instance()`
  or `CCINIClass::INI_Art()` parses as a call on the referenced pointer, and MSVC
  reports `C2064: term does not evaluate to a function taking 0 arguments`
  *followed by a misleading* `C2737: const object must be initialized` on the
  variable you were assigning. Drop the parens. Both shapes have now cost four
  CI rounds across three different subsystems.
- **`R0`/`RX` virtuals have no address.** Calling one *qualified* silently no-ops;
  it only works through vtable dispatch on an object. `GetFoundationData` is one.
- **`R->ESP()` cannot move the stack.** `POPAD` discards the ESP slot, so the write
  is accepted and thrown away. See shape 3 of
  [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

---

## 7. Sentinel values and inverted enums

- **`CanBuildResult`: `-1` is truthy.** `TemporarilyUnbuildable = -1` blocks at
  signed comparisons (`jle`, `<= 0`) and **passes** at `test eax,eax / jne`. It
  greys a cameo; it does not reliably refuse. Three bugs in one project traced to
  this split.
- **`AIDifficulty` is INVERTED: `Hard=0, Normal=1, Easy=2`.** Never do arithmetic
  on it; switch on the names. Any INI key exposing difficulty should take names,
  not numbers, or authors will write `0` meaning Easy and get Hard.
- **Watch for a sentinel the *next* instruction tests for.** If vanilla does
  `cmp eax,0xFFFFFFFF; je` right after, that value is expected — and your handler
  will produce it.

---

## 8. Counters that look interchangeable are not

`OwnedBuildingTypes` (produced/gained, includes under-construction) and
`ActiveBuildingTypes` (physically present) diverge in both directions:

- pre-placed map objects never pass through `RegisterGain`, so `ownedNow` reads 0
  for a house that plainly owns them;
- a building under construction counts in `ownedNow` but not in `present`.

The engine's own prerequisite check reads `ActiveBuildingTypes`. Taking
`max()` of the two to paper over the first problem silently buys the second.

---

## 9. A hook must not cover a branch target

A patch is `E9 rel32` plus NOPs. If any instruction elsewhere jumps to an address
*inside* the patch, after its first byte, the CPU decodes a byte of the rel32 as
an instruction. Size, overlap and stolen-byte checkers all pass these seats.

**The tell:** a crash that depends on the launch rather than the code. The byte the
CPU runs is part of `stub − next_ip`, and the stub address moves with what other
DLLs allocate at start-up. So adding or removing an *unrelated* DLL turns the crash
on or off, and the same DLL list can crash on one map and not another. Seen so far:

- `C0000005 at 00000000` with a **segment selector in a register** (`ESI = 0x2B`):
  the byte was `06`, `push es`, which leaves ESP 4 bytes low until the `ret`.
  See [Tooltip-GetToolTip.md](Tooltip-GetToolTip.md) (`0x4AE66C`).
- `C0000096`, or an AV at the target address, or a wild jump: see
  [Scenario-Smudge-Read.md](Scenario-Smudge-Read.md) (`0x6B4DBA`) and
  [Production-Queues-Factories.md](Production-Queues-Factories.md) (`0x500960`).

- **Another DLL's hook can be the branch.** A handler that returns an address
  continues there, so a return value that lands inside a *different* DLL's patch
  is a mid-patch entry too; gamemd's own code never jumps there. **VERIFIED**
  (2026-11-07, crash dump): Antares `UnitClass_GetActionOnCell_Deactivated`
  (`0x7404B9`) sets EAX = 0 and returns `0x740805` for a deactivated unit, and
  FreeUnitExt hooks `0x740801` with 5 stolen bytes (`mov eax,[esp+0x30]`;
  `pop edi`), so `0x740805` is the top byte of its rel32. Byte `0F` then decoded
  `0F 5E 5D 5B` = `divps xmm3,[ebp+0x5B]`, a misaligned 16-byte access:
  `C0000005 at 00740805`, "read from FFFFFFFF". It fires when a deactivated unit
  (no operator, no Robot Control Center, EMP) is selected with the cursor over
  the map (stack: DisplayClass `0x692300`/`0x692610`).
  **FIXED 2026-11-07** (FreeUnitExt `d24657c`): the seat moved to `0x740805`
  itself, size 7 (`pop edi; pop esi; pop ebp; pop ebx; add esp,0x1C`, then
  `ret 0xC` at `0x74080C`), so Antares' return now lands on the patch's first
  byte. The hook sets EAX, because on Antares' path `[esp+0x30]` still holds the
  cell argument, and it skips deactivated units (gamemd `0x70FBD0`, byte
  `+0x1C8`, the same byte Antares tests). Nothing in gamemd branches into
  `0x740806`–`0x74080B`, and no DLL in the game folder holds a constant there.
  Phobos' DisallowMoving `ReturnResult` still jumps to `0x740801`, which now
  runs the original `mov eax` and falls into the new seat. Deployed md5
  `0ed9455a` (backup `FreeUnitExt.dll.bak-20261107-184242`). **Unverified
  in-game**: no deactivated unit has been selected with this build yet. Details:
  [Building-GrandOpening-FreeUnits.md](Building-GrandOpening-FreeUnits.md),
  appendix.

**The check:** for every address strictly inside `(seat, seat + stolen)`, search the
disassembly for a direct branch to it (`j.. 0x<addr>`, `call 0x<addr>`). Also
look at the switch tables, which objdump does not resolve, and at every other
DLL's code for a returned constant (`B8 imm32`, `mov eax, <addr>`). A sweep of
the 32 launch-list DLLs on 2026-11-07 found only the Antares/FreeUnitExt pair
above. Branching to the seat itself is fine.

**A 2026-11-07 sweep of 3,483 deployed hooks (31 DLLs) found these framework seats
covering a direct branch target.** ⚠ Reachability unchecked: a handler that never
returns 0, or a loop it replaces whole, can make the inner branch dead. Read the
handler before trusting or blaming one.

| Seat (stolen) | Framework | Name | Covered target ← branch |
|---|---|---|---|
| `0x41CE7E` (6) | Phobos | `AircraftTypeClass_Load` | `0x41CE80` ← `0x41CE32 jl` |
| `0x523932` (8) | Antares | `InfantryTypeClass_CTOR_Initialize` | `0x523934` ← `0x52396E jl` |
| `0x524B53` (5) | Phobos | `InfantryTypeClass_Load` | `0x524B57` ← `0x524994 jl` |
| `0x528BAC` (0xA) | Phobos | `INIClass_GetString_Inheritance_NoEntry` | `0x528BB2` ← `0x528A5A je` |
| `0x5A5C6A` / `0x5A5D6F` / `0x5A6464` (9) | Antares | `MapSeedClass_Generate_PlacePavedRoads_RoadEnd{NE,SW,SE}` | `+4` ← a `ja` just after each |
| `0x685354` (9) | Phobos | `ClearLotsOfShit_GlobalVariable` | `0x685358` ← `0x68538D jl` |
| `0x6AC02F` (8) | Antares | `sub_6ABD30_Strip3` | `0x6AC031` ← `0x6AC047 jl` |
| `0x6B73BE` (6) | Phobos | `SpawnManagerClass_AI_SpawnTimer` | `0x6B73C1` ← `0x6B73B0 jmp` |
| `0x74809E` (9) | Phobos | `UnitTypeClass_Load` | `0x7480A0` ← `0x74802B jl` |

---

## 10. A plain field the engine maintains through a function is the function's business

Reaching a field needs no address, so a field write looks like the cheap way to
change state from a seat you already own. Ask first whether the engine ever
*writes that field anywhere but inside one function*. If it does not, that
function is the API, and the field is its implementation detail.

**VERIFIED (2026-11-07, IntelExt)** — `TechnoClass::Deactivated` (byte `+0x1C8`)
is the worked example. It is a plain `bool`, and YRpp even documents it
(*"Robot Tanks without power for instance"*). Writing it directly instead of
calling `TechnoClass::Deactivate()` (`0x70FC90`) skipped:

* `ObjectClass::Unselect` (vtable `+0x150`) — so the unit stayed **selected
  while deactivated**, which is the documented precondition for the `0x740805`
  click crash in trap 9 above,
* `FootClass::Locomotor->Power_Off()` — so hover units never settled and a
  "deactivated" tank kept drifting (⚠ corrected: this lives in **Antares'**
  replacement of the function, not in vanilla's `+0x3D0` stop-and-park, which
  only forces `Mission::Guard`),
* the power-down sound (`TechnoTypeClass +0x5AC`),
* and a **refusal path** that returns without touching the byte for a unit
  docked at the building on its own cell — bypassing it froze units in the war
  factory door.

Four field-visible bugs, one of them a crash, from one byte write. `Deactivate`
and `Reactivate` had real addresses in YRpp the entire time.

The tell is asymmetry: if your code writes a field that the engine only ever
writes at the end of a longer routine, you are re-implementing that routine
badly.

⚠ And once you have found the routine, apply **trap 1 to it as well**. Both
`Deactivate` and `Reactivate` are completely replaced by Antares (size-6 entry
hooks at `0x70FC90` / `0x70FBE0`), so a reconstruction from `gamemd.exe` is not
what runs — the first revision of the page below made exactly that mistake and
mis-attributed the hovering to a vanilla virtual. Disassembling the original is
how you learn the slots; the framework's source is how you learn the behaviour. Also check the inverse — nothing clears a field you latch unless you
clear it, and `Deactivated` had **no** code path writing `false`, which is how
"powers off and never comes back" shipped.

Details: [Techno-Deactivation-Power.md](Techno-Deactivation-Power.md).

---

## How much to trust a claim on any page

See [_CONVENTIONS.md](_CONVENTIONS.md). In short: look for the status marker.
`VERIFIED` means someone observed it; `⚠ Unverified` / `⚠ DISPUTED` mean they did
not. Nothing here is archived for being wrong without saying so first.
