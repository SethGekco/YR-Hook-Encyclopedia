# Techno Deactivation & Power (`Deactivate` / `Reactivate`)

How the engine powers a techno down and back up: robot tanks without a Robot
Control Center, EMP'd units, vehicles whose operator has left, and anything a
mod turns off.

The one fact that matters most is at the top, because it is the mistake this
page exists to prevent.

---

## ⚠ `TechnoClass::Deactivated` is a plain field, but writing it is NOT powering a unit down

`TechnoClass::Deactivated` is byte **`+0x1C8`** (YRpp names it, comment
*"Robot Tanks without power for instance"*). `TechnoClass::IsDeactivated()` is
**`0x70FBD0`** and just reads that byte; Antares tests the same byte.

Because it is a plain field with no accessor required, it is tempting — and
wrong — to write it from any seat you already own. The engine maintains that
byte **through a pair of functions**, and the byte is the *least* of what they
do:

| | address | YRpp |
|---|---|---|
| `TechnoClass::Deactivate()` | **`0x70FC90`** | declared, `JMP_THIS` |
| `TechnoClass::Reactivate()` | **`0x70FBE0`** | declared, `JMP_THIS` |

Both are **plain members with real addresses**, not the `R0`/`RX`/`RT` stubs
that silently no-op on a qualified call. There has never been a reason to write
the byte instead.

**VERIFIED (2026-11-07, IntelExt)** — writing the byte directly instead of
calling `Deactivate()` produced four distinct field bugs at once, all of them
downstream of the three things the byte write skips plus the one thing it
overrides:

1. units that **never powered back on** (nothing clears the byte),
2. units left **hovering mid-move** instead of parking,
3. units **frozen in the war factory door**,
4. a **selected-while-deactivated** state that fed the `0x740805` click crash
   (see [_TRAPS-READ-FIRST.md](_TRAPS-READ-FIRST.md) and
   [Building-GrandOpening-FreeUnits.md](Building-GrandOpening-FreeUnits.md)).

---

## `TechnoClass::Deactivate()` — `0x70FC90`, reconstructed

```
// ── the refusal, FIRST, before anything is touched ──
if (this->[0x418])                                  // link-related flag
    if (this->GetNthLink(0))                        // RadioLinks[0]
        if (CellClass::GetBuilding(this->GetCell()) == this->GetNthLink(0))
            return;                                 // ⚠ RETURNS, byte UNTOUCHED

call this->vtable[0x3D0]       // 0x70F850 — stop & park  (also in Reactivate)
call this->vtable[0x150]       // 0x5F44A0 — ObjectClass::Unselect

if (this && (this->[0x14] & 4))
    this->[0x674]->vtable[0x5C](this->[0x674])      // +0x5C (Reactivate: +0x58)

if (!this->Deactivated) {                           // sound on TRANSITION only
    type = this->vtable[0x84]();                    // GetTechnoType, 0x6F3270
    if (type->[0x5AC] != -1)
        PlaySoundAt(type->[0x5AC], this->Coords);   // 0x7509E0, coords at +0x9C
}

this->Deactivated = true;                           // 0x70FD62
```

### The refusal is the part nobody expects

`0x65AD30` is **`RadioClass::GetNthLink(int)`** — `return this->RadioLinks[idx]`,
`RadioLinks` at **`+0xE4`**. MSVC emitted it **twice, byte-identical**, at
`0x65AD30` and `0x65AD40` (COMDAT folding of the inline accessor); the named
`RadioClass::ContainsLink` follows immediately at `0x65AD50`, which is how the
identification is anchored. `0x47C520` is **`CellClass::GetBuilding()`**, and
`vtable+0x1BC` (`0x5F6960` on `UnitClass`) is the object's `GetCell`.

So: **vanilla refuses to deactivate a unit that is in radio contact with the
building standing on its own cell** — a unit docked at, or being produced by and
exiting, that building. Bypassing this by writing the byte freezes a unit in the
factory door, because it is deactivated while it still has an exit sequence to
run.

⚠ `TechnoClass +0x418` is **not identified**; it gates the refusal and is
plausibly a link count or "has links" flag. Treat the refusal as conditional on
an unknown, not as unconditional.

### The two virtuals

| slot | `UnitClass` target | what it does |
|---|---|---|
| `+0x3D0` | `0x70F850` | **stop & park.** `[this+0x218] = 0`, then `vtable[0x480](0,1)`, `vtable[0x3C8](0)`, `vtable[0x1F0](5)` — the last being a mission force to **`Mission::Guard` (5)**. Called by `Deactivate` **and** `Reactivate`. |
| `+0x150` | `0x5F44A0` | **`ObjectClass::Unselect`.** Walks `ObjectClass::CurrentObjects` (**`0xA8ECB8`**, count at `0xA8ECC8`) after testing byte **`+0x83` = `IsSelected`**. |

`+0x3D0` is what actually *parks* a unit: without it the locomotor keeps the
unit's last move, which is why a hover unit whose byte was written directly
keeps hovering instead of settling.

`+0x150` means **the engine deselects a unit it powers down.** That is a
load-bearing safety property, not cosmetics: "a deactivated unit is selected
with the cursor over the map" is precisely the state that reaches Antares'
`UnitClass_GetActionOnCell_Deactivated` and crashes. A mod that sets the byte
without unselecting manufactures the crash precondition.

---

## `TechnoClass::Reactivate()` — `0x70FBE0`, reconstructed

```
call this->vtable[0x3D0]       // 0x70F850 — same stop & park, UNCONDITIONAL
                               //            ⚠ no refusal check at all

if (this && (this->[0x14] & 4))
    this->[0x674]->vtable[0x58](this->[0x674])      // +0x58

if (this->Deactivated) {                            // sound on TRANSITION only
    type = this->vtable[0x84]();
    if (type->[0x5A8] != -1)
        PlaySoundAt(type->[0x5A8], this->Coords);
}

this->Deactivated = false;                          // both exits, 0x70FC6D / 0x70FC7A
```

Differences from `Deactivate()` worth knowing:

* **No refusal path.** `Reactivate()` always takes.
* It does **not** call `+0x150`, so it does not touch selection.
* It **still calls the stop-and-park virtual, unconditionally.** So calling
  `Reactivate()` on a unit that is already powered is not free — it forces
  `Mission::Guard` and will yank a live order. Guard the call on
  `IsDeactivated()`.

### Sound indices

| field | meaning |
|---|---|
| `TechnoTypeClass +0x5A8` | reactivate / power-up sound index, `-1` = none |
| `TechnoTypeClass +0x5AC` | deactivate / power-down sound index, `-1` = none |

Both are played through `0x7509E0` with the object's coords (`+0x9C`), and both
are gated on an actual state transition, so a per-frame re-assert that goes
through the functions will not spam audio — but see the idempotency note below.

---

## Neither function is idempotent

The **sound** is transition-guarded. Nothing else is. `Deactivate()` runs
`Unselect` and the stop-and-park virtual on **every** call, and `Reactivate()`
runs stop-and-park on every call.

Consequences for a mod that wants to hold a unit powered down across frames:

* **Do not call `Deactivate()` every frame.** The unit becomes permanently
  unselectable, because every frame removes it from `CurrentObjects` again.
* **Do** re-test `IsDeactivated()` every frame and call `Deactivate()` only on
  the transition. That keeps the ordering property a post-logic seat needs
  (anything that powers the unit up mid-object-loop still gets a full, proper
  power-down post-loop) without the per-frame side effects.

⚠ Antares' `PoweredUnitClass` rescans every 15 frames and calls its power-up on
a `Deactivated` unit whose power source still exists, from inside
`TechnoClass::Update` — i.e. **during** the object loop. A post-loop seat
(e.g. `0x55B6B3`) therefore wins on ordering. This is why the transition test
has to be re-evaluated per frame rather than latched once.

## Who turned it off?

There is **no record in the engine of why** a unit is deactivated — one byte
serves robot tanks without a control center, EMP, missing operators and mod
features alike. A mod that powers units down must track its own claim, and must
only reactivate units it actually turned off; otherwise it will power up a robot
tank whose Robot Control Center is genuinely gone.

Claim the restore only if the call **took** — i.e. re-read `Deactivated` after
`Deactivate()` returns, because of the refusal path above.

---

## Field offsets referenced

| offset | field |
|---|---|
| `ObjectClass +0x9C` | `Coords` (passed to the sound call) |
| `ObjectClass +0x83` | `IsSelected` (tested by `Unselect`) |
| `RadioClass +0xE4` | `RadioLinks[]` |
| `TechnoClass +0x1C8` | `Deactivated` |
| `TechnoClass +0x218` | cleared by stop-and-park, unidentified |
| `TechnoClass +0x418` | gates the `Deactivate` refusal, **unidentified** |
| `TechnoClass +0x674` | object passed to vtable `+0x58`/`+0x5C`, unidentified |
| `TechnoTypeClass +0x5A8` / `+0x5AC` | power-up / power-down sound index |

## Globals & helpers

| address | what |
|---|---|
| `0x70FBD0` | `TechnoClass::IsDeactivated()` |
| `0x70FBE0` | `TechnoClass::Reactivate()` |
| `0x70FC90` | `TechnoClass::Deactivate()` |
| `0x70F850` | stop & park (`vtable +0x3D0`) |
| `0x5F44A0` | `ObjectClass::Unselect` (`vtable +0x150`) |
| `0x5F6960` | `ObjectClass::GetCell` on `UnitClass` (`vtable +0x1BC`) |
| `0x6F3270` | `GetTechnoType` on `UnitClass` (`vtable +0x84`) |
| `0x65AD30` | `RadioClass::GetNthLink(int)` (folded; second copy `0x65AD40`) |
| `0x47C520` | `CellClass::GetBuilding()` |
| `0x7509E0` | play sound at coords |
| `0xA8ECB8` | `ObjectClass::CurrentObjects`, count at `0xA8ECC8` |

## No hooks needed

Nothing on this page requires a Syringe seat. Both entry points are callable
directly from any seat you already own, which is the whole point: the reason to
reach for the byte was never that the functions were unreachable.
