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
