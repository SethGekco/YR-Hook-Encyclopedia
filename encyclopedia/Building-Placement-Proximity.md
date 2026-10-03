# Building placement — the proximity / adjacency check

Where the engine decides whether a proposed building site is close enough to
something you already own. This is the `Adjacent=` consumer; the registry only
records where `Adjacent` is *read at load* (`0x45FFB6`), never who uses it.

**Status:** disassembly below is verified by objdump of `gamemd-spawn.exe`. The
in-game interpretation at the end is **an open question**, flagged as such.

---

## `DisplayClass::PassesProximityCheck` — `0x4A8F20`

Signature, from Phobos' two hooks inside it
(`Phobos/src/Ext/BuildingType/Hooks.cpp:202, 235`):

```cpp
bool DisplayClass::PassesProximityCheck(
    BuildingTypeClass* pType,     // ESI at entry
    int houseArrayIndex,          // [ESP+0x08] (STACK_OFFSET(0x30, 0x8))
    CellStruct* foundationData,   // [ESP+0x0C]
    CellStruct* currentPosition); // [ESP+0x10]
```

`ret 0x10` at `0x4A9059`; the result is a byte accumulated in `[ESP+0x3C]` and
loaded to `AL` at `0x4A904E`.

### The radius is `Adjacent + 1`, not `Adjacent`

```
4a8f35:  movsx ebp,WORD PTR [edi]        ; currentPosition->X
4a8f38:  movsx ebx,WORD PTR [edi+0x2]    ; currentPosition->Y
4a8f3e:  mov   eax,DWORD PTR [esi+0xeb4] ; pType->Adjacent     <- ESI = pType
4a8f44:  mov   esi,DWORD PTR [esp+0x34]  ; ESI REASSIGNED here
4a8f48:  inc   eax                       ; radius = Adjacent + 1
4a8f4f:  sub   ecx,eax                   ; startX = X - radius
4a8f51:  lea   edx,[edx+eax*2]           ; width + 2*radius
4a8f58:  add   edx,ecx                   ; endX
4a8f5a:  sub   ebx,eax                   ; startY = Y - radius
```

So the scanned rectangle is the foundation grown by `Adjacent + 1` on every
side. ⚠ **`Adjacent=0` therefore does not mean "must overlap" — it means
"exactly one cell of slack".** That off-by-one is the whole reason the field is
worth documenting: an observed slack of *N* cells implies `Adjacent == N-1`.

⚠ **`ESI` changes meaning mid-function** (`0x4A8F44`). It is `pType` at
`0x4A8F3E` and a `BuildingClass*` by `0x4A8FD7`. Phobos' two hooks declare
exactly that, and reading the wrong one yields a plausible garbage pointer.

### What counts as an anchor — two accept paths

Per scanned cell, `CellClass::GetBuilding` (`call 0x47C520` at `0x4A8FCC`); null
→ next cell.

```
4a8fd7:  mov   ecx,[esi+0x21c]           ; pCellBuilding->Owner
4a8fe1:  cmp   DWORD PTR [ecx+0x30],eax  ; Owner->ArrayIndex == houseArrayIndex?
4a8fe4:  jne   0x4a8ffa                  ; not ours -> try the ally path
4a8fe6:  mov   edx,[esi+0x520]           ; pCellBuilding->Type
4a8fec:  cmp   BYTE PTR [edx+0x154f],0x0 ; Type->BaseNormal
4a8ff3:  je    0x4a8ffa                  ; BaseNormal=no -> NOT an anchor
4a8ff5:  mov   BYTE PTR [esp+0x3c],0x1   ; ACCEPT
```

**Own building:** anchors only if **`BaseNormal=yes`**. A `BaseNormal=no`
building does not extend your build area at all.

**Allied building** (`0x4A8FFA`–`0x4A9027`): requires the global byte at
`0xA8B264` (ally-build enabled), `call 0x4F9A50` on the house from
`HouseClass::Array` (`0xA8022C`) to confirm the alliance, and then
`Type->[0x1550]` — `EligibileForAllyBuilding` — before accepting.

Offsets `0x154F` / `0x1550` are adjacent bytes, matching YRpp's declaration
order (`YRpp/BuildingTypeClass.h:193` `bool BaseNormal`).

### Known hooks here

| Address | Owner | Note |
|---|---|---|
| `0x4A8F3E` | **Phobos** (size `0x6`) | replaces the `Adjacent` read; writes EAX and jumps `0x4A8F44`, so the `inc eax` at `0x4A8F48` **still runs** — a replacement that pre-increments would double-count |
| `0x4A8FD7` | **Phobos** (size `0x6`) | per-anchor filtering (`Adjacent.Allowed/Disallowed`, `NoBuildAreaOnBuildup`) |
| `0x4A8FF5` | **Antares** | `MapClass_CanBuildingTypeBePlacedHere_Ignore` — sits exactly on the ACCEPT write, i.e. it can refuse an anchor the engine would have taken |

Three-way traffic on one short function: **treat as contended**. Phobos'
`ProximityTemp` state is file-global and its `Adjacent_Disallowed_Prohibit`
branch calls `PassesProximityCheck` **recursively**, so a hook here can observe
reentrancy.

---

## ⚠ OPEN: a 1-cell build radius with no Construction Yard

**Observed in game 2026-10-02** (BuildQueueExt `AlwaysAvailable`): with the
Construction Yard gone and a single owned barracks as the anchor, a
`BuildingType` declaring `Adjacent=8` could only be placed **directly touching**
the barracks — roughly one cell of slack rather than nine.

Facts established, which make this genuinely puzzling:

- the anchor (`YABRCK`) has `BaseNormal` at its default **yes**, so it is a valid
  anchor by the test above;
- the placed type declares `Adjacent=8`, so the radius should be **9**;
- the radius arithmetic above is unconditional — nothing in this function scales
  it by base size, factory presence, or ConYard ownership.

Per the `Adjacent + 1` arithmetic, a 1-cell slack implies **`Adjacent` read as 0
at runtime**, regardless of the INI text. Candidate explanations, none yet
confirmed:

1. `Adjacent` genuinely holds 0 at runtime — an INI-parse or load-order issue.
   The mod writes `Adjacent=8;4 Edit by AI script ; vanilla=4`; `;` opens a
   comment so the value should read `8`, but this is unverified at runtime.
2. Antares' hook at the ACCEPT write (`0x4A8FF5`) refuses the anchor, and
   placement is succeeding at 1 cell through a *different* path than this
   function.
3. The limiter is not this function at all — e.g. shroud/explored-cell or
   passability constraints around an isolated building.

**Next step:** log `pType->Adjacent` at runtime. If it reads 8, this function is
exonerated and the limiter is elsewhere; if it reads 0, the question becomes why.
Do not assume (1) — it is the most appealing explanation and the least evidenced.

**Confirmed via.** objdump of `gamemd-spawn.exe` `0x4A8F20`–`0x4A9059`; Phobos
`src/Ext/BuildingType/Hooks.cpp:195-265`; Antares symbol dump
(`gamemd_names_from_antares_pdb.txt:382`).
