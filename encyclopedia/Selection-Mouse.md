# Selection & mouse-picking

How a click becomes a selection: `ObjectClass::Select` (the vtable slot everyone
wraps to change selection behavior) and `TacticalClass::SelectAt` (the routine
that decides which object under the cursor gets picked). Both are common wrap
targets for "select the parent instead" / "this object is transparent to the
mouse" features.

---

### `0x6FBFA0` — ObjectClass::Select  ⚠ YRpp R0 stub, not a JMP_THIS trampoline

**What it is.** The real engine `ObjectClass::Select` (marks the object selected,
adds it to the current-objects set, plays the select sound, etc.). It is the
function sitting in the `Select` vtable slot of Unit/Infantry/Building/Aircraft —
none of those classes override it, so **all four vtables point here** (a useful
cross-check that you've found the right slot: the Select slots at
`0x7F5DBC` UnitClass / `0x7EB1A4` InfantryClass / `0x7E4008` BuildingClass /
`0x7E23F0` AircraftClass all hold `0x6FBFA0`).

**Easily mistaken — the R0-stub footgun.** When you replace the Select vtable slot
with a wrapper and want to call the original, the natural code is a qualified
non-virtual call `pThis->TechnoClass::Select()`. **That silently no-ops.** Unlike
most YRpp virtuals — which are declared `{ JMP_THIS(0xADDR); }` and really jump to
the game function even when called non-virtually — YRpp declares
`ObjectClass::Select()` with the **`R0` stub macro** (`#define R0 {return 0;}`).
It has **no game address at all**, so a qualified call binds to `{ return 0; }`
and the object is never actually selected. No crash, no `except.txt` — just dead
selection. Confirmed in the field: a standalone DLL wrapped these four slots and
**no unit could be player-selected** (the AI issues orders directly and never
calls Select, so AI-controlled units still worked — the tell was "AI can deploy
its MCV but the player can't select theirs").

**Correct pattern.** Call the address directly:
`reinterpret_cast<bool(__thiscall*)(ObjectClass*)>(0x6FBFA0)(pThis)`. Before
wrapping *any* virtual, grep its YRpp declaration — `JMP_THIS` is safe to call
qualified, `R0`/`R1`/`RX` stubs are not. An in-Phobos PR can mask this (Phobos may
carry a real impl), so ports of a PR into a standalone DLL are especially exposed.

**Confirmed via.** YRpp `ObjectClass.h` (`virtual bool Select() R0;`),
`YRPPCore.h` (`#define R0 {return 0;}`); objdump of `gamemd.exe` at `0x6FBFA0`
(reads the `+0x41b` flag, adds to current-objects); in-game test (fix restored
selection).

---

### `0x6DA3FF` — TacticalClass::SelectAt, per-object pick filter  ⚠ multi-consumer (Kratos)

**What it does.** Inside `SelectAt`, as the routine walks candidate objects under
the cursor, this breakpoint (size 0x6, over `mov cl,[eax+0x41a]` with `EAX` = the
candidate techno) lets a consumer veto/keep a candidate. Return the "skip this
object" branch (`0x6DA440`) to make an object unpickable, or continue (0x0) to
re-run the stolen `mov` and fall through to the normal check.

**Used by / interactions.** **Kratos hooks this same address** (`SelectAt_VirtualUnit`,
size 0x6). Two size-6 breakpoints at one address **chain** — safe *iff* each
returns "continue" for cases it doesn't own, so a well-behaved TransparentToMouse
filter (skip only its own transparent attachments, else continue) composes with
Kratos's virtual-unit handling. Do not convert this to a full replacement.

**Confirmed via.** objdump of `gamemd.exe` (`EAX`=techno, `[+0x41a]` flag,
skip-branch `0x6DA440`); registry (Kratos consumer at this address); Syringe
chaining semantics.

---

### `0x6DA4FB` — TacticalClass::SelectAt, cell-occupier fetch

**What it does.** After resolving the clicked cell (`EAX` = `CellClass*`, returned
by `MapClass::GetCellAt` `0x5657A0`, which does `cellArray[y*512+x]`), the vanilla
reads `[cell+0xE4]` = `CellClass::FirstObject` as the object to select. A wrapper
(size 0x6, returning `0x6DA501`) can re-pick here — e.g. walk `FirstObject`→
`NextObject` and return the first object that *isn't* flagged transparent-to-mouse,
via `R->EAX`.

**Easily mistaken.** `[cell+0xE4]` is `FirstObject` specifically (not `AltObject`
`0xE8`, used for bridges). A reimplementation must reproduce the same occupier the
vanilla `mov eax,[eax+0xE4]` would return, only skipping the objects it means to
hide; returning null when it shouldn't kills selection on that cell.

**Confirmed via.** objdump of `gamemd.exe` (`0x5657A0` index math; `[cell+0xE4]`);
YRpp `CellClass.h` (`FirstObject`); reasoning about the SelectAt path.

---

### `0x692300` — DisplayClass::ProcessClickCoords  ⚠ the only correct screen-point → cell

**Framework names.** None — unhooked by every framework in the registry. Listed
here because it is a *function to call*, not a seam to hook.

**What it does.** Converts a **view-relative** screen point into the cell the
player is actually looking at, walking the terrain so that height and bridges
are accounted for. It is what the engine's own mouse handler uses.

```
bool __thiscall ProcessClickCoords(Point2D* src, CellStruct* cellOut,
                                   CoordStruct* coordOut, ObjectClass** targetOut,
                                   BYTE* a5, BYTE* a6)
```

Called on `DisplayClass::Instance` (`0x87F7E8`). Four call sites: `0x4AACD4`
(the mouse handler), `0x4AE571`, `0x4FB470`, plus internal uses around
`0x692FFC`-`0x693301`.

**⚠ What it does *not* do — and the trap people hit instead.** The obvious
alternative, `TacticalClass::ClientToCoords` (`0x6D2280`), maps a screen point to
world coordinates **as if the ground were flat**. It never receives a Z and
cannot infer one, so on raised terrain the cell it returns is displaced toward
the **north** by roughly one cell per height level. `TacticalClass::CoordsToScreen`
shows the forward transform it is failing to invert:

```cpp
return Point2D { x, y - AdjustForZ(coord.Z) };
```

Observed in play as a target landing 1-4 cells "too high", varying with terrain —
and completely invisible on flat ground, so a flat-map test will pass.

**⚠ The view origin is `DSurface::ViewBounds` (`0x886FA0`)**, not the rectangle at
`0xB0CE28`. They are different rectangles; using the wrong one adds a constant
offset on top of any height error. (YRpp gotcha: `ViewBounds` is declared inside
`class DSurface`, not `class Surface`.)

**Canonical sequence**, copied from the engine's mouse handler at
`0x4AAC60`-`0x4AACD4` — mirror it rather than doing the isometric maths by hand:

```
WWMouseClass::Instance->GetCoords(&pt)      // screen-absolute
pt.X -= DSurface::ViewBounds.X              // -> view-relative
pt.Y -= DSurface::ViewBounds.Y
DisplayClass::Instance.ProcessClickCoords(&pt, &cell, ...)
```

**Determinism note.** Mouse and view state are per-client and unsynced. Resolving
a cell from them is safe **only** if the resolved cell is then placed inside a
queued `EventClass` and consumed on execution — the same shape as a normal click.
Reading the mouse during event *execution* would desync.

**Confirmed via.** objdump of `gamemd.exe` (the `0x4AAC60`-`0x4AACD4` sequence,
call-site census, `ClientToCoords` at `0x6D2280` taking the raw point);
YRpp `DisplayClass.h`, `TacticalClass.h`, `Surface.h`; **in-game** — switching a
superweapon's hotkey targeting from `ClientToCoords` to `ProcessClickCoords`
removed a reproducible 1-4 cell northward error on sloped terrain.

---

### `0x4AACD4` — the mouse handler's call to `ProcessClickCoords`  ✅ unhooked

**What it is.** The `call 0x692300` inside the mouse handler at `0x4AAC60`. Its
fourth parameter is an `ObjectClass**` out-param: on return it holds **the object
the cursor is over**, and that object is what the cursor's shape/action is derived
from.

**Why it matters — the two mouse paths are different.** It is easy to assume
`TacticalClass::SelectAt` (above) governs "what the mouse interacts with". It does
not: `SelectAt` is **click-to-select** only. The **cursor** resolves its object
through `ProcessClickCoords`. Filtering one does not filter the other, and the
symptom of getting this wrong is precise and confusing: clicks work correctly and
select the right object, while the *cursor* still shows "no action here" for an
object the mod believes is mouse-transparent.

**Wrapping it.** `DEFINE_FUNCTION_JUMP(CALL, 0x4AACD4, wrapper)` with the
`__thiscall` shape of `ProcessClickCoords`, call the original, then post-process
the out-param. Writing `nullptr` back into it makes the cursor fall through to the
cell underneath — the object is simply not seen by the cursor logic. Wrapping the
**call site** rather than the function leaves `ProcessClickCoords`' other three
callers (`0x4AE571`, `0x4FB470`, and its internal uses) untouched, which is
usually what you want.

**Determinism.** Cursor/mouse state is per-client and unsynced, so filtering here
is render/UI-only and cannot desync — provided the filter reads only type/config
data and does not mutate synced game state.

**Used by / interactions.** Both `0x4AACD4` and `0x692300` are unhooked by Phobos,
Antares and Kratos (registry-checked 2026-09-01).

**Confirmed via.** objdump of `gamemd.exe` (the six pushes at
`0x4AACB9`-`0x4AACCE` feeding `call 0x692300` at `0x4AACD4`); YRpp
`DisplayClass.h` (`ProcessClickCoords(Point2D*, CellStruct*, CoordStruct*,
ObjectClass** Target, BYTE*, BYTE*)`); **in-game** — an attachment flagged
mouse-transparent still captured the cursor until this call was filtered, even
though the `SelectAt` filters were already in place and clicking behaved correctly.

---

### ⚠ Isometric projection is NOT conformal — right angles do not survive it

Not a hook; a geometry fact that bites anyone laying out positions in cell space
and expecting them to *look* that way.

`TacticalClass::AdjustForZShapeMove` (inlined in the engine, reproduced in YRpp
`TacticalClass.h`) projects cell coordinates to screen as:

```
screenX = (CellWidthInPixels  * (x - y) / 2) / LeptonsPerCell
screenY = (CellHeightInPixels * (x + y) / 2) / LeptonsPerCell
```

With the stock 2:1 tile ratio that makes the two cell axes:

```
cell +X  ->  screen (+2, +1)
cell +Y  ->  screen (-2, +1)      dot = -3  ->  ~127 degrees apart, NOT 90
```

**Consequence.** Two directions that are perpendicular in cell space appear ~127°
(or ~53°) apart on screen, depending on orientation. A formation, spread, line of
objects or offset pattern built "perpendicular" in cell space therefore looks
*skewed* — and skewed differently depending on which way it is oriented, because
the two cases are not symmetric.

Observed concretely: a paradrop line built perpendicular to the flight path in
cell space read as "abreast" from two map edges and "trailing behind each other"
from the other two. The cell-space maths was correct throughout; it was simply
the wrong space for a decision the player judges visually.

**Fix.** Project the reference direction to screen, do the rotation *there*, then
convert back through the inverse of the 2×2 isometric matrix:

```
given screen (sx, sy),  cellX = (sx + 2*sy) / (2 * CellHeightInPixels)
                        cellY = (-sx + 2*sy) / (2 * CellHeightInPixels)
```

For a 2:1 projection, the cell-space direction that appears perpendicular to a
north-approach flight vector is `(1.25, 0.75)`; for an east approach,
`(0.75, 1.25)`. Keep these as integer numerators over a small denominator if the
result feeds a synced calculation — see the determinism note on `0x692300` above.

**Rule of thumb.** Cell space for anything the *simulation* judges (ranges,
distances, occupancy). Screen space for anything a *player* judges (formations,
visual spacing, "does that look straight"). They are not interchangeable, and the
error is invisible on any test that only checks cell coordinates.

**Confirmed via.** YRpp `TacticalClass::AdjustForZShapeMove`; arithmetic on the
projected axes; **in-game** — switching a paradrop formation's sideways axis from
cell-perpendicular to screen-perpendicular made it read as abreast from every
approach edge, where before it alternated between abreast and trailing.
