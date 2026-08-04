# Subsystem: Map cell indexing (coordinate → cell)

How the engine turns a world coordinate into a `CellClass*`. This is the single
most load-bearing piece of arithmetic for any **map-resize** work, because the
row stride (`512`) is a hardcoded power-of-two shift **duplicated hundreds of
times** across `gamemd.exe` *and* inlined again inside every framework DLL's YRpp
copy. Entries sorted by address.

The global map object is `MapClass` at **`0x87F7E8`** (a global instance, not a
pointer to one — engine code does `MOV ECX, 0x87F7E8` to get `this`). Two fields
matter here:
- `[MapClass+0x13C]` = base pointer of the `CellClass` array.
- `[MapClass+0x140]` = cell-count bound (max valid cell index), set at map alloc.

**No mainline framework hooks these addresses** — but Phobos, Antares and Kratos
each ship their **own inlined** `GetCellIndex` (YRpp `MapClass::GetCellAt`,
`index = (Y>>8)<<9 + (X>>8)`, `MaxCells 0x40000`) compiled into their `.text`, so
a map-resize DLL that rescales the stride must patch **all** of them, not just
`gamemd.exe`.

---

### `0x565730` — MapClass::CellAt(CoordStruct) / coordinate → cell lookup

**Framework names.** None hook this address. (Frameworks inline an equivalent;
see the intro.)

**What it does.** `__thiscall`, `ECX = MapClass*` (`0x87F7E8`), one stack arg =
`CoordStruct*` (three dwords `{X, Y, Z}` in leptons). It converts the coordinate
to a flat cell index and returns the `CellClass*`:

```
X' = (X + roundbias) >> 8            ; leptons → cells (256 leptons / cell)
Y' = (Y + roundbias) >> 8
index = (Y' << 9) + X'               ; << 9  ⇒ ROW STRIDE 512   (@0x565757)
if (index < 0) bail                  ; js
if (index >= [MapClass+0x140]) bail  ; cmp against the cell-count bound (@0x56575E)
return [MapClass+0x13C] + index * sizeof(CellClass)
```

Key sub-addresses:
- **`0x565757`** — `SHL EDX, 9` — the row-stride multiply. This is the byte a
  map-resize DLL rewrites (`9 → 0xA` for stride 1024, etc.).
- **`0x56575E`** — `CMP EDX, [ECX+0x140]` — the bound check against the runtime
  cell count.
- **`0x565766`** — `MOV ECX, [ECX+0x13C]` — loads the cell-array base.

**What it does *not* do — easily mistaken (this is where map-resize crashes come
from).**
- The stride at `0x565757`, the bound at `[+0x140]`, the array allocation behind
  `[+0x13C]`, and the caller's own `sizeof(CellClass)` stepping are **four
  independent facts that must all agree.** Patch the stride to 1024 but leave the
  backing allocation or a sibling stride site at 512, and an index that *passes*
  the `[+0x140]` bound check still resolves to memory **outside the real cell
  array** → the function returns a wild `CellClass*`, and the caller faults on the
  first field read. Observed failure signature: the returned "pointer" is
  actually **ASCII string bytes** (e.g. a unit/anim ID like `YAPPET_F`), because
  the mis-strided address landed in the string/type tables. A crash of the form
  `MOV reg,[eax+0x??]` where `eax` looks like text is this bug.
- The stride is **not** in one place. `gamemd.exe` has ~435 `SHL reg,9` stride
  sites plus the cell-array *population* row stride at `0x566437`
  (`ADD ECX,0x200`, not a shift — easy to miss) and 32 full-map *iterator*
  byte-stride sites (`SHL reg,0xB`). Patching only the obvious `SHL ,9` sites
  leaves subtler subsystems (locomotion cell lookups, occupation lists, iso
  render) on the old stride — those are the "works at 512, breaks at 1024"
  residuals.
- The bound `[+0x140]` is the **runtime cell count**, not the hardcoded
  `0x40000` (= 512×512). Several inlined copies bounds-check against a *literal*
  `0x40000`/`cmp eax,0x40000` instead — those are separate sites a resize must
  also raise.

**Used by / interactions.** Called from many hot paths, notably locomotion and
render (a crash here has been seen under a flying-unit update: the Antares
HunterSeeker/Fly locomotion process at `0x4CCB84` walks objects and looks up the
cell under each). A map-resize Syringe DLL (incidental consumer) patches
`0x565757` here and the sibling sites listed above; if any is missed at stride >
512 this lookup is where it surfaces.

**Register / calling convention.** `ECX = MapClass* (0x87F7E8)`; arg0 =
`CoordStruct*`; returns `CellClass*` in `EAX` (or a bail value — do not assume
non-null/valid on an out-of-range coordinate).

**Confirmed via.** objdump of vanilla `gamemd.exe` (imagebase 0x400000): the
shift/bound/array arithmetic at `0x565730`–`0x565766` read directly. The
duplicated-stride counts (435 gamemd `SHL,9`; `0x566437` population stride; 32
iterator sites; Phobos 48 / Antares 73 inlined `SHL` copies) are from a
map-resize DLL's own patch report and are **framework-version-specific** — treat
the counts as indicative, re-derive per build. **Lookup mechanics confirmed;
per-DLL counts indicative.**

---

### `0x5656EA` — MapClass operator[] / cell-by-index (stride sibling)

**Framework names.** None.

**What it does.** The index-based cousin of `0x565730`: given a cell index (or a
`CellStruct` it flattens), returns the `CellClass*`. Shares the same row-stride
assumption, so it is one of the sites a resize DLL patches alongside `0x565757`.

**What it does *not* do — easily mistaken.** Same four-facts-must-agree caveat as
`0x565730`. Being index-based, it is *also* where an already-wrong index (built
elsewhere with a stale stride) gets dereferenced — the wrong stride may originate
far from here.

**Confirmed via.** objdump of vanilla `gamemd.exe`; identified as a stride site
by a map-resize DLL's patch pass. **Confirmed as a stride site; full body not
re-derived here.**

---

### `0x566437` — cell-pointer array population, row stride (`ADD ECX,0x200`)

**Framework names.** None.

**What it does.** During map setup the engine fills the per-row cell-pointer
array, advancing one row with `ADD ECX, 0x200` (= 512 pointers). This is a row
stride expressed as an **immediate add, not a shift**, so a naive "rewrite every
`SHL ,9`" resize pass **misses it** — and missing it means cells are populated at
the wrong pitch, which shows up as units unable to deploy/move on cells past the
first 512-stride row.

**What it does *not* do — easily mistaken.** It is not a coordinate lookup; it is
one-time population. But it must use the *same* stride as `0x565757`/`0x5656EA`
or every later lookup disagrees with how the array was laid out.

**Confirmed via.** objdump of vanilla `gamemd.exe`; cross-referenced to a
map-resize DLL that patches exactly this immediate (`0x200 → stride`) and logged
the deploy/move fix it produced. **Confirmed.**
