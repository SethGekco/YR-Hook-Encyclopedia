# Map Reveal / Sight (shroud reveal)

Cross-references the three `MapClass::RevealArea` entry points and — more
importantly — a **framework-wide gotcha** that bites anyone trying to enlarge the
cell grid: YRpp-based DLLs hardcode the 512-cell map stride at **compile time**,
so patching only `gamemd.exe` is not enough.

---

### `0x5673A0` — MapClass::RevealArea0
### `0x5678E0` — MapClass::RevealArea1
### `0x567DA0` — MapClass::RevealArea2

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | MapClass_RevealArea0 / 1 / 2 | 0x5 | src/Ext/Techno/Hooks.Sight.cpp |
| Ares    | MapClass_RevealArea0 / 1 / 2 | 0x5 | src/Ext/Techno/Hooks.Sight.cpp (inherited) |

**What it does.** These are the engine's shroud-reveal entry points (reveal a
radius around a coord; RevealArea2 is the shroud-frame/occlusion refresh).
**Antares fully REPLACES all three** with its own `MapRevealer` class
(`src/Misc/MapRevealer.{h,cpp}`): each hook reads the stack args, constructs a
`MapRevealer`, calls `Reveal0/1` or `UpdateShroud`, and **returns to the vanilla
function's tail** (`0x5678D6`, `0x567D8F`, `0x567F61`) — i.e. the original
vanilla reveal body never executes when Antares (or Ares) is loaded.

**What it does *not* do — easily mistaken.** If you're reverse-engineering the
reveal from `gamemd.exe`, **the vanilla RevealArea body is dead code** under
Antares/Ares. Do not spend time patching the vanilla reveal's cell-index `shl`
sites for a bigger map — they never run. The live logic is in `Antares.dll`
(`MapRevealer`), which does its own cell lookups via `MapClass::GetCellAt`.

**Register / calling convention.** `ECX = MapClass*` (`this`). Stack (stdcall-ish,
Antares reads): `[esp+4]=CoordStruct* coords, +8=radius/start, +C=house/radius,
+10=onlyOutline/fog, +14=a6, +18=fog, +1C=allowRevealByHeight, +20=add`
(RevealArea2 has the shorter `coords,start,radius,fog`).

**Confirmed via.** Antares source `Hooks.Sight.cpp` + `MapRevealer.cpp` (clone
of Phobos-developers/Antares, 2026-08); registry `hooks.csv`; objdump of vanilla
`gamemd.exe` for the tail return targets.

---

## ⚠ The big-map trap: YRpp hardcodes stride 512 at COMPILE time

**Symptom.** With a runtime patch that enlarges the cell grid to stride 1024 in
`gamemd.exe` (so `MapClass::operator[]` and the cell-pointer array use
`Y*1024+X`), shroud reveal comes out as **stripes / every-other-row** — reveal
touches only cells whose `Y` matches the unit's `Y`-parity, scattered.

**Cause.** Antares's `MapRevealer` gets each cell with
`MapClass::Instance.GetCellAt(cell)`. In YRpp (`MapClass.h`) that is:

```cpp
int GetCellIndex(const CellStruct& c) const { return (c.Y << 9) + c.X; }   // Y*512, HARDCODED
CellClass* TryGetCellAt(const CellStruct& c) const {
    int idx = GetCellIndex(c);
    return (idx >= 0 && idx < MaxCells) ? Cells[idx] : nullptr;             // MaxCells = 0x40000 = 512², HARDCODED
}
```

Both `Y << 9` and `MaxCells = 0x40000` are **inlined into `Antares.dll` at
compile time**. A runtime byte-patch of `gamemd.exe` does not touch them. So on a
1024-strided array, Antares reads `Items[Y*512+X]` — the **wrong cell**
(even `Y` → `(X, Y/2)`; odd `Y` → off to the side), which is exactly the
every-other-row scatter.

**Scope (measured).** `Antares.dll` `.text` (v21.352.1218) contains **73**
`shl reg,9` sites and **2** `cmp reg,0x40000` sites — the inlined `GetCellIndex`
copies and `MaxCells` bounds. **This is not Antares-specific: every YRpp-based
DLL (Antares, Phobos, Kratos, any Syringe ext) has the same compile-time 512.**

**Implications for a map-size extension.**
- Patching `gamemd.exe` is necessary but **not sufficient**. Any feature a
  framework *reimplements* (reveal, and likely lighting/palette, some movement)
  uses the DLL's own 512 indexing and will misbehave on big maps.
- Fix options: (a) runtime-patch the DLL's `.text` (`shl 9 → shl 0xA`,
  `cmp 0x40000 → 0x100000`) the same way you patch `gamemd`, classifying which
  `shl 9` are cell strides vs legit `*512`; (b) rebuild the framework from source
  against a stride-aware YRpp; (c) upstream a runtime-configurable stride into
  YRpp/Antares. Only (b)/(c) are clean long-term.

**Confirmed via.** YRpp `MapClass.h` (`GetCellIndex`, `MaxCells`); byte-scan of
`Antares.dll` `.text`; in-game testing on a RA2/YR map at stride 1024 (MapSizeExt
project) showing every-other-row reveal while the gamemd-path deploy/build works.
Unverified: exact count of the 73 that are cell-stride vs other `*512`.
