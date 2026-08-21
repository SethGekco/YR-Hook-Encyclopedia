# Gap Generators & Vision Denial

The gap generator subsystem: `TechnoClass::CreateGap` / `DestroyGap`, the cell
counters they maintain, and the framework hooks that live inside them.

The single most important structural fact is at the top, because it changes what
any gap feature *can* be.

---

## Structural note — gap is client-side, and is computed against `CurrentPlayer` only

`TechnoClass::CreateGap` opens with `mov eax, ds:0xA83D4C` (`HouseClass::CurrentPlayer`)
and bails if it is null. Every subsequent per-cell decision asks whether the cell
belongs to, or is allied with, **`CurrentPlayer`** — never "which houses should
this gap hide from".

Consequences:

* There is **no per-house gap state**. The engine computes exactly one thing:
  "what the player at *this* machine cannot see". Each client computes its own.
* A feature like "faction X can see through faction Y's gap" is therefore a
  **rendering** decision, not a simulation one. Changing the ally test inside
  `CreateGap` cannot desync by itself — but any *timer* or flag driving that
  decision is game state and must be synced and serialised like any other.
* Conversely, **never branch game logic on gap state.** Two clients legitimately
  hold different cell shroud counters for the same cell.

**Confirmed via** objdump of vanilla `gamemd.exe` (`0x6FB170`–`0x6FB460`), plus
Antares `src/Ext/Techno/Hooks.Gap.cpp`, which reads `HouseClass::CurrentPlayer->SpySatActive`
in the same code path.

---

## Structural note — `CellClass +0x13C` is the friendly-gap counter

YRpp names this field `unknown_13C` (`CellClass.h`, after `VisibilityChanged`).
It is not unknown: `CreateGap` increments it for every cell that falls inside a
gap **the current player owns, is allied to, or can see via `SpySatActive`** —
the branch at `0x6FB3F9`:

```
0x6FB3C5  call [vt+0x3C]         ; get the cell
0x6FB3CA  call 0x50B6F0          ; cell belongs to CurrentPlayer?
0x6FB3E0  call 0x4F9A50          ; ... or is Owner allied with CurrentPlayer?
0x6FB3EF  mov al,[edx+0x1F5]     ; ... or CurrentPlayer->SpySatActive
0x6FB3F9  <cell> + 0x13C, inc    ; yes -> count it, do NOT shroud it
```

The shrouding branch (`0x6FB306`) instead touches `ShroudCounter` (`+0x130`),
`GapsCoveringThisCell` (`+0x134`) and clears two `AltFlags` (`+0x12C`) bits.

So the engine **already tracks which cells a friendly gap covers** and then does
nothing with the number. Anyone implementing "show the player the footprint of
their own gap generator" can read this counter instead of recomputing coverage.

**Caveat:** it is a single counter shared by *all* friendly gap generators, so it
answers "is this cell inside some friendly gap" and not "whose". Per-generator
display needs its own bookkeeping.

**Confirmed via** objdump. **Unverified:** whether anything else in the engine
reads `+0x13C` (no reader was found in the `0x6FB000`–`0x6FB700` range; a
whole-binary xref sweep has not been done).

---

## Structural note — the gap shape is hard-coded

The cell loop is a square scan over `[-r-1, r+1]²` gated by an inline
`x*x + y*y < (r+1)*(r+1)` test (`0x6FB25C`–`0x6FB2AE`). Radius comes from
`this->GapRadius` (`TechnoClass +0x26C`), defaulted from `TechnoTypeClass +0xCD2`
— a **signed byte** (`movsbl`), which is what limits vanilla gap radius to 127
and why Antares/Ares replace that read to support larger gaps.

There is no parameter that changes the *shape*: a non-circular or partial gap
means replacing the loop.

---

### `0x6FB170` — TechnoClass::CreateGap

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | (entry not hooked; hooks `0x6FB1B5` and `0x6FB306` inside) | — | `src/Ext/Techno/Hooks.Gap.cpp` |

**What it does.** Marks the techno as generating a gap (`+0x269 = 1`), resolves
the radius, and walks the circle applying per-cell shroud (enemy view) or the
friendly counter (own/allied view). Exits at `0x6FB45C`–`0x6FB460`
(`pop esi; add esp,0x20; ret`).

**What it does *not* do — easily mistaken.**
* It does **not** hide anything from a specific house — see the structural note.
* It is **not** idempotent-safe to call twice: the `GeneratingGap` flag at
  `+0x269` guards re-entry, so a second `CreateGap` without a `DestroyGap` is a
  no-op, and code that changes radius must `DestroyGap()` → set radius →
  `CreateGap()` (this is exactly what Antares does at `0x44E2B0` for
  `SuperGapRadiusInCells`).
* `TechnoClass::CreateGap` / `DestroyGap` are declared **`RX` in YRpp** — stubs
  with no address. Calling them through a qualified non-virtual call silently
  does nothing. Call the addresses directly, or go through the vtable. (Same
  footgun as `ObjectClass::Select`; see `Selection-Mouse.md`.)

**Register / calling convention.** `ECX = TechnoClass*`, no arguments,
`__thiscall`. At `0x6FB1B5` (Antares' hook): `ESI = TechnoClass*`,
`EAX = TechnoTypeClass*`.

**Confirmed via** objdump of vanilla `gamemd.exe`; the PDB symbol map names
`0x6FB1B5` / `0x6FB306` / `0x6FB4A3` as `TechnoClass_CreateGap_*`, which brackets
the function. Antares' hooks corroborate the register layout.

---

### `0x6FB306` — TechnoClass::CreateGap, per-cell shroud apply

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_CreateGap_Optimize` | 0x6 | `src/Ext/Techno/Hooks.Gap.cpp:142` |

**What it does.** Antares replaces the vanilla per-cell sequence (which
re-fetches the cell four times via `MapClass::GetCellAt`) with a single-fetch
version and returns `0x6FB3BD`.

**What it does *not* do — easily mistaken.** It is *not* a general "a cell got
gapped" event: it is only the **enemy-view** branch. Cells covered by a friendly
gap never reach this address (they take the `+0x13C` branch instead).

**Interactions — do not co-hook.** Because Antares returns a jump target here, a
second DLL hooking the same address is a load-order coin flip: both handlers run,
but the first non-zero return wins and the loser's control flow assumption is
silently wrong. A third-party DLL wanting a custom gap should wrap the **function
entry** (`0x6FB170`) and take over completely for opted-in types, leaving
untagged types on the vanilla+Antares path.

**Register / calling convention.** `EAX = CellClass*`.

**Confirmed via** Antares source (`develop`), corroborated by objdump.

---

### `0x6FB470` — TechnoClass::DestroyGap

**What it does.** Clears `GeneratingGap` (`+0x269 = 0`), re-resolves the radius
the same way `CreateGap` did, and walks the same circle decrementing what was
incremented.

**What it does *not* do — easily mistaken.** It **recomputes the cell set from
the radius**; it does not remember which cells were actually modified. Any hook
that makes `CreateGap` cover a *different* set of cells (a pattern, a partial
fill, a radius that changed in between) must also take over `DestroyGap`, or the
cell counters leak and areas stay shrouded forever.

**Register / calling convention.** `ECX = TechnoClass*`. Inner hook `0x6FB4A3`:
`ESI = TechnoClass*`, `EAX = TechnoTypeClass*`. Inner hook `0x6FB5F0`:
`EAX = CellClass*`, returns `0x6FB69E`.

**Confirmed via** objdump; Antares hooks `0x6FB4A3` and `0x6FB5F0`.

---

## Related

* `Map-Reveal-Sight.md` — `MapClass::RevealArea0/1/2`, the other half of the
  visibility system.
* `Map-Cell-Indexing.md` — the 512 stride, which the cell fetch in this loop uses.
