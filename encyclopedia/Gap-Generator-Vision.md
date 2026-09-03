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

⚠ **Also disputed:** the `SpySatActive` term in the listing above, and the
addresses attributed to the three tests. In-game behaviour and Antares' destroy
gate both argue the friendly test is owner/ally only. See *UNRESOLVED — is
`SpySatActive` a term in the create-side friendly test?* below, which carries the
experiment that settles it.

---

## Structural note — BOTH loops apply the friendly test, and it is load-bearing

The friendly/shroud split above is not a create-side quirk. `DestroyGap` applies
the **same** test at the top of its own per-cell body and skips the friendly
cells outright — it does not even decrement `+0x13C`.

(Whether `SpySatActive` is one of the terms in that test is **disputed** — see
the unresolved note below. Everything in this section holds either way; only the
*reachability* of the trap changes.)

That matters because it is easy to read the `+0x13C` asymmetry (incremented,
never decremented) as "the two loops disagree" and conclude that the destroy side
is a free-for-all. It is the opposite: `+0x13C` is the *only* thing they disagree
about. On the two counters that drive rendering they agree exactly, and the
agreement is what keeps them safe.

**How you can tell without reading the branch.** Antares' destroy replacement at
`0x6FB5F0` opens with a bare decrement, no guard:

```cpp
--pCell->GapsCoveringThisCell;
if(HouseClass::CurrentPlayer->SpySatActive
    && static_cast<int>(pCell->GapsCoveringThisCell) <= 0) { ... }
```

`GapsCoveringThisCell` is a **DWORD** (`CellClass +0x134`). A friendly-arm cell
reaching that line would wrap to `0xFFFFFFFF`. The code can only be correct if
the friendly arm is filtered out upstream — so it is.

### The trap for third-party hooks

The natural seam for a custom gap is the cell-staging instruction at the top of
each loop body (`0x6FB2AE` on create, `0x6FB598` on destroy), because both stage
into the same stack slot and both have an easy loop-continue target. But that
seam is **ahead of the friendly test**. A hook that takes over cell bookkeeping
there sees every in-field cell, including the ones vanilla was about to hand to
`+0x13C` and never shroud.

Decrementing there is not a no-op even when it is floored against underflow:

* `ShroudCounter` (`+0x130`) is **shared with every other shroud source** on the
  cell — unexplored ground, re-shrouded ground, other generators. Taking it down
  reveals terrain the viewer never scouted.
* `GapsCoveringThisCell` is shared with **every other gap generator** covering
  the cell, so the decrement cancels coverage someone else paid for.

Any hook at those two addresses must reproduce the test and defer the friendly
arm back to vanilla. Reproduce it **once**, and consult the one copy from both
sides: two copies drift, and the drift is invisible until cells stop replenishing
their shroud.

Residual hazard, which vanilla shares and which no stateless hook can close: the
arm is evaluated live on each pass, so an input that changes *between* a create
and its destroy still mismatches. Closing it needs per-cell memory of the arm
taken.

**Confirmed via** Antares `src/Ext/Techno/Hooks.Gap.cpp` (`0x6FB306`, `0x6FB5F0`)
read against YRpp's `CellClass` field widths.

---

## UNRESOLVED — is `SpySatActive` a term in the create-side friendly test?

Two accounts, each with real evidence, and they cannot both be right. **They have
opposite consequences for anyone hooking `0x6FB598`, so settle this before
writing a destroy-side hook.** Recorded here rather than silently picking a
winner.

### Reading A — SpySat selects the friendly arm

The `+0x13C` note above, taken from objdump, lists three tests (`0x50B6F0`,
`0x4F9A50`, then `mov al,[edx+0x1F5]` = `SpySatActive`) feeding the increment at
`0x6FB3F9`. DESIGN-level notes in IntelExt record the same three-way condition.

**Predicts:** a spy satellite makes you *immune to gap generators* — a satellite
viewer is never shrouded by the create pass at all.

**Consequence if true:** a destroy-side hook placed at `0x6FB598`, ahead of the
test, will decrement `ShroudCounter` and `GapsCoveringThisCell` on cells whose
create never incremented them, for **any** viewer holding a satellite. With an
animated field that repeats every rebuild tick and walks the whole radius to
zero, revealing unscouted ground.

### Reading B — SpySat only gates the destroy-side restore

Two independent objections to A:

1. **Antares' destroy gate would be dead code.** `0x6FB5F0` reads
   `CurrentPlayer->SpySatActive` to decide whether to give vision back:
   `if (SpySatActive && GapsCoveringThisCell <= 0) --ShroudCounter;`. Under
   Reading A a satellite viewer never *has* a gapped cell, so that branch could
   never fire. It reads naturally as vanilla's actual rule — *destroying a gap
   returns your vision only if you have a satellite* — which requires satellite
   viewers to be shrouded normally on create.
2. **In-game observation contradicts A.** The VERIFIED section below records that
   before `Gap.Temporary`, an animated pattern "appears to work only when the
   viewer has `SpySatActive`". Under Reading A that viewer sees no gap darkness
   whatsoever, so there would be nothing to observe.

**Predicts:** gap blinds satellite holders like anyone else; the create-side
friendly test is owner/ally only.

**Consequence if true:** there is no create/destroy asymmetry to fix, and a hook
that *adds* a SpySat term to its own mirror of the test introduces one — it will
skip cells it did in fact conceal.

### The address discrepancy underneath it

The two records also disagree on *where* the create test sits. The `+0x13C`
listing places the tests at `0x6FB3C5`–`0x6FB3EF`, i.e. **after** the shroud
block at `0x6FB306`, which cannot be a branch selecting between them. IntelExt
treats the tests as ending before `0x6FB2F7` and jumps there to force a cell down
the shroud arm — and that jump demonstrably shrouds owner/allied cells in game,
which is behavioural evidence the tests precede it. `0x6FB3C5`–`0x6FB3F9` is
therefore most likely the friendly *block* (cell fetch + increment), and the
`SpySatActive` read attributed to the test may belong to something else in that
block. This is the single most likely source of the error in Reading A.

### How to settle it — decisive, no code required

**T1 — the one that decides it.** Skirmish, stock rules, no mod DLL. Give an
enemy AI a plain gap generator and let it cover ground you have scouted. Build a
Spy Satellite Uplink and keep it powered.

* Gap area **stays visible** → Reading A.
* Gap area **goes black anyway** → Reading B.

**T2 — confirms the destroy gate independently.** Destroy that gap generator
*without* a satellite: the area should stay shrouded (vanilla does not hand back
vision). Repeat *with* a satellite up: it should clear. If T2 behaves this way
while T1 says "stays visible", the two readings are still in conflict and the
objdump is wrong somewhere.

**T3 — the definitive read.** `objdump` `0x6FB2AE`–`0x6FB416` and record whether
`[edx+0x1F5]` is read *before* the branch that chooses between `0x6FB2F7` and the
`+0x13C` block, or only inside the latter. Note the exact address of every
conditional jump. Nobody has done this pass with the branch structure in mind.

Until T1 or T3 is done, treat the third term as **unknown** and keep a
destroy-side hook's mirror to owner/ally only — the conservative choice, because
it errs toward doing the bookkeeping you might own rather than skipping
bookkeeping you definitely own.

---

## VERIFIED — gap shroud is permanent because create clears `Mapped`, and that is what hides animated patterns

The shrouding branch clears two `AltFlags` bits, and *which* two turns out to
matter more than it looks. The pair is `AltCellFlags::Clear = Mapped | NoFog`,
and `Mapped` (`0x8`) is the engine's **"this cell has been explored"** bit.

Dropping it is what makes gap shroud **permanent**: the viewer must physically
re-scout the ground, rather than the cell reverting to what they already knew.

**The non-obvious consequence.** This silently defeats *any* animated or
patterned gap field. The first pass of a pattern clears `Mapped` across the
whole radius, so every later band paints black on black and the pattern becomes
invisible **to the one house it is aimed at**. It appears to work only when the
viewer has `SpySatActive`, because a spy satellite keeps the terrain revealed
underneath, giving the darkness something to contrast against.

Anyone building moving gap patterns will hit this and reasonably conclude their
pattern code is broken. It is not — the pattern is drawing correctly onto an
already-black map.

**The fix is one bit.** Preserve the explored state across the field's lifetime
and a second, distinct *class* of shroud falls out: identical in appearance
while it covers a cell, but restoring exactly the prior explored state when it
leaves. Scouted ground darkens and returns; never-scouted ground stays black, so
it reveals nothing.

Two implementation notes that cost real debugging time:

* **Snapshot on entry, do not infer on exit.** A viewer can legitimately scout a
  cell while it is concealed. Reading `Mapped` at destroy time cannot separate
  that from a cell the field darkened.
* **The restore must also run outside a pattern rebuild.** Gating it on rebuild
  frames restores the moving bands but leaves the field's final radius black
  forever — a failure that only appears when the generator dies or browns out.

**Confirmed via** objdump for the flag clear, and **in-game verification**
(IntelExt `Gap.Temporary`, 2026-09-02): a ripple field with the explored bit
preserved animates visibly for the targeted house with no spy satellite, and
leaves no permanent shroud behind. Before the change the same field went solid
black after one pass.

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

**What it does *not* do — easily mistaken.**
* It **recomputes the cell set from the radius**; it does not remember which
  cells were actually modified. Any hook that makes `CreateGap` cover a
  *different* set of cells (a pattern, a partial fill, a radius that changed in
  between) must also take over `DestroyGap`, or the cell counters leak and areas
  stay shrouded forever.
* It does **not** decrement every cell in the circle. Friendly-arm cells
  (own/allied/`SpySatActive`) are filtered out before the counter block, exactly
  as on the create side — see the structural note on the friendly test, and the
  trap it describes for hooks placed at `0x6FB598`.

**Register / calling convention.** `ECX = TechnoClass*`. Inner hook `0x6FB4A3`:
`ESI = TechnoClass*`, `EAX = TechnoTypeClass*`. Inner hook `0x6FB5F0`:
`EAX = CellClass*`, returns `0x6FB69E`.

**Confirmed via** objdump; Antares hooks `0x6FB4A3` and `0x6FB5F0`.

---

## Related

* `Map-Reveal-Sight.md` — `MapClass::RevealArea0/1/2`, the other half of the
  visibility system.
* `Map-Cell-Indexing.md` — the 512 stride, which the cell fetch in this loop uses.
