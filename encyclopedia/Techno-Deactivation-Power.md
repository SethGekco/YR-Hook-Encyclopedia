# Techno Deactivation & Power (`Deactivate` / `Reactivate`)

How the engine powers a techno down and back up: robot tanks without a Robot
Control Center, EMP'd units, vehicles whose operator has left, and anything a
mod turns off.

The one fact that matters most is at the top, because it is the mistake this
page exists to prevent.

---

## ⛔ READ FIRST: Antares replaces BOTH of these functions completely

An earlier revision of this page reconstructed both functions from
`gamemd-spawn.exe` and presented the result as what happens. **It is not, in any
Antares game.** This is trap 1 ([_TRAPS-READ-FIRST.md](_TRAPS-READ-FIRST.md)),
and the page walked straight into it.

**VERIFIED (2026-11-07)** by parsing `.syhks00` in the deployed `Antares.dll`
(record stride **16** bytes: `addr, size, name*, pad` — not 12):

| hook | size | Antares name |
|---|---|---|
| `0x70FBE0` | 6 | `TechnoClass_Activate` |
| `0x70FC90` | 6 | `TechnoClass_Deactivate` |

Both are size-6 hooks **at the function entry**, and both are commented
`// complete replacement` in Antares' own source
(`src/Ext/Techno/Hooks.Deactivated.cpp`). No other injected DLL in the game
folder hooks either address, nor `0x70FBD0` / `0x70F850` / `0x5F44A0`.

Calling `Deactivate()` / `Reactivate()` therefore runs **Antares'** versions.
That is a good thing — they are strictly more careful than vanilla — but the
vanilla reconstruction further down is the *fallback* behaviour, useful for
understanding the slots and offsets, **not** a description of the running game.
Read [the Antares section](#what-antares-actually-does) first.

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

## VANILLA `TechnoClass::Deactivate()` — `0x70FC90`, reconstructed

⚠ This is plain gamemd. Antares replaces it; see [What Antares actually does](#what-antares-actually-does).

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

`TechnoClass +0x418` is **`IsTether`** — Antares' replacement writes the refusal
as `if(pThis->IsTether) { auto pLink = pThis->GetNthLink(0); if(pLink &&
pThis->GetCell()->GetBuilding() == pLink) return; }`, which matches the vanilla
disassembly instruction for instruction. (An earlier revision of this page
marked `+0x418` unidentified.)

### The two virtuals

| slot | `UnitClass` target | what it does |
|---|---|---|
| `+0x3D0` | `0x70F850` | **stop & park.** `[this+0x218] = 0`, then `vtable[0x480](0,1)`, `vtable[0x3C8](0)`, `vtable[0x1F0](5)` — the last being a mission force to **`Mission::Guard` (5)**. Called by `Deactivate` **and** `Reactivate`. |
| `+0x150` | `0x5F44A0` | **`ObjectClass::Deselect`** (YRpp's name; declared `virtual void Deselect() RX`, i.e. an addressless stub — a *qualified* call no-ops, a virtual call through a live object dispatches fine). Walks `ObjectClass::CurrentObjects` (**`0xA8ECB8`**, count at `0xA8ECC8`) after testing byte **`+0x83` = `IsSelected`**. |

`+0x3D0` is `TechnoClass::Guard()` — Antares calls `pThis->Guard()` in exactly
this position in its replacement, which is what anchors the identification.

⛔ **SUPERSEDED**: an earlier revision of this page said `+0x3D0` "is what
actually parks a unit", and attributed a hover unit's failure to settle to
skipping it. That is wrong. Forcing `Mission::Guard` stops the unit taking new
steps; it does **not** power the locomotor down. The thing that lands a hover
unit is `FootClass::Locomotor->Power_Off()`, which exists **only in Antares'
replacement** — vanilla's `Deactivate` never touches the locomotor. See
[the Antares section](#what-antares-actually-does). Corrected 2026-11-07 after a
side session read the Antares source; the original claim was an inference from
the vanilla disassembly alone and was never tested.

`+0x150` means **the engine deselects a unit it powers down.** That is a
load-bearing safety property, not cosmetics: "a deactivated unit is selected
with the cursor over the map" is precisely the state that reaches Antares'
`UnitClass_GetActionOnCell_Deactivated` and crashes. A mod that sets the byte
without unselecting manufactures the crash precondition.

---

## VANILLA `TechnoClass::Reactivate()` — `0x70FBE0`, reconstructed

⚠ This is plain gamemd. Antares replaces it; see [What Antares actually does](#what-antares-actually-does).

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
| `TechnoTypeClass +0x5A8` | `ActivateSound`, `-1` = none |
| `TechnoTypeClass +0x5AC` | `DeactivateSound`, `-1` = none |

Both are played through `0x7509E0` with the object's coords (`+0x9C`), and both
are gated on an actual state transition, so a per-frame re-assert that goes
through the functions will not spam audio — but see the idempotency note below.

---

## What Antares actually does

Both handlers live in Antares' `src/Ext/Techno/Hooks.Deactivated.cpp` and are
marked `// complete replacement`. Reproduced in structure, not verbatim:

### `TechnoClass_Activate` (`0x70FBE0`)

```
if (pThis->IsUnderEMP() || !pExt->IsPowered() || !pExt->IsOperated())
    return;                                 // ⚠ refuses; Deactivated UNTOUCHED

pThis->Guard();
if (auto pFoot = abstract_cast<FootClass*>(pThis))
    pFoot->Locomotor->Power_On();           // ← not in vanilla

if (std::exchange(pThis->Deactivated, false)) {
    play pType->ActivateSound   (+0x5A8)    // skipped while ScenarioInit
    add spotlight if Is_Spotlighted
    BuildingExt::UpdateFactoryQueues if a building
}
```

**The three guards are the useful part for a mod.** `IsPowered()` covers *both*
powering schemes:

* vanilla **`PowersUnit=`** (`TechnoTypeClass::PoweredUnit`): walks
  `pThis->Owner->Buildings` for a building whose `PowersUnit` is this type,
  with `RegisteredAsPoweredUnitSource` set and not EMP'd. This is the Robot
  Control Center ↔ Robot Tank relationship.
* Antares **`PoweredBy=`** (`#617`): delegates to `PoweredUnitClass::IsPowered`.

So **calling `Reactivate()` is safe even if you do not know why a unit is off**:
it will decline to power up a robot tank whose Robot Control Center is gone,
unpowered or EMP'd, and will decline for a vehicle with no operator. A mod that
disabled a unit itself can simply call `Reactivate()` on release and let these
guards arbitrate.

⚠ `Guard()` runs **before** the `Deactivated` test and therefore on *every*
call, including on an already-powered unit. It resets the unit's mission. Guard
your call on `IsDeactivated()` if that matters.

### `TechnoClass_Deactivate` (`0x70FC90`)

```
if (pThis->IsTether) {                      // +0x418
    auto pLink = pThis->GetNthLink(0);      // RadioLinks[0], +0xE4
    if (pLink && pThis->GetCell()->GetBuilding() == pLink)
        return;                             // ⚠ refuses; Deactivated UNTOUCHED
}

pThis->Guard();
pThis->Deselect();
if (auto pFoot = abstract_cast<FootClass*>(pThis))
    pFoot->Locomotor->Power_Off();          // ← not in vanilla

if (!std::exchange(pThis->Deactivated, true)) {
    play pType->DeactivateSound (+0x5AC)    // skipped while ScenarioInit
    remove spotlight if Is_Spotlighted
}
```

Antares **keeps** vanilla's tether refusal and the deselect, and **adds**
`Locomotor->Power_Off()`.

**`Locomotor->Power_Off()` is what lands a hover unit.** Nothing in vanilla's
`Deactivate` touches the locomotor, so on plain gamemd a deactivated hover unit
is parked by `Guard()` but does not settle. This is the single most important
reason to call the function rather than write the byte: the byte write produces
a "deactivated" tank that keeps drifting.

### `PoweredUnitClass` exists only for `PoweredBy=`

**VERIFIED** (Antares `src/Ext/Techno/Hooks.cpp`, the `#617 powered units`
block): the per-instance `PoweredUnitClass` — the one whose `Update()` runs
inside `TechnoClass::Update`, i.e. inside the object loop — is created **only
when `PoweredBy=` is non-empty**.

A type using vanilla **`PowersUnit=`** therefore gets **no periodic rescan at
all**. Its reactivation is **event-driven**, from a `PowersUnit=` building
coming online (`BuildingClass::UpdatePowered`, near `0x4549D1`).

⚠ This narrows a claim made elsewhere. "Antares re-powers deactivated units
every 15 frames, so a post-loop seat is needed to win on ordering" is true
**only for `PoweredBy=` types**. For a vanilla Robot Tank there is no race to
win — and, correspondingly, nothing that will undo a mod's deactivation either,
which is why a mod that forgets to clear its own flag leaves the tank dead until
a Control Center power-on event.

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

Under Antares the arbitration is much better than it sounds: `Reactivate()`'s
own `IsUnderEMP` / `IsPowered` / `IsOperated` guards already cover EMP, a missing
or unpowered `PowersUnit=` / `PoweredBy=` source, and a missing operator. What
they do **not** cover is *another DLL*, or a second overlapping field from your
own feature. So the claim is still needed — but it is protecting against mods,
not against the engine's own reasons.

---

## Field offsets referenced

| offset | field |
|---|---|
| `ObjectClass +0x9C` | `Coords` (passed to the sound call) |
| `ObjectClass +0x83` | `IsSelected` (tested by `Unselect`) |
| `RadioClass +0xE4` | `RadioLinks[]` |
| `TechnoClass +0x1C8` | `Deactivated` |
| `TechnoClass +0x218` | cleared by stop-and-park, unidentified |
| `TechnoClass +0x418` | `IsTether` — gates the `Deactivate` refusal |
| `TechnoClass +0x674` | object passed to vtable `+0x58`/`+0x5C`, unidentified |
| `TechnoTypeClass +0x5A8` / `+0x5AC` | `ActivateSound` / `DeactivateSound` |

## Globals & helpers

| address | what |
|---|---|
| `0x70FBD0` | `TechnoClass::IsDeactivated()` |
| `0x70FBE0` | `TechnoClass::Reactivate()` |
| `0x70FC90` | `TechnoClass::Deactivate()` |
| `0x70F850` | `TechnoClass::Guard()` (`vtable +0x3D0`) |
| `0x5F44A0` | `ObjectClass::Deselect` (`vtable +0x150`; YRpp declares it `RX`) |
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

⚠ But do **not** co-hook `0x70FBE0` or `0x70FC90`. Antares already owns both
with a size-6 entry hook and a complete replacement, so a second hook there is
the same-address co-hook problem (trap 4) on a function whose original body no
longer runs. Call them instead.
