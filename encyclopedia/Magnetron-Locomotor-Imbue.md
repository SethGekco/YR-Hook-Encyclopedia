# Subsystem: Magnetron — locomotor imbue, hold & release

How YR's Magnetron actually works, and why every attempt to swap its
`Locomotor=` for a different CLSID leaves the victim permanently paralysed.

Addresses are for the standard YR `gamemd.exe`, imagebase `0x400000`, read with
objdump on 2026-10-10. The binary was validated first against an independently
established landmark (`TechnoClass::Fire` @ `0x6FDD50` with `and esp,0xFFFFFFF8`
at `0x6FDD53`, from `Projectile-Scatter.md`) so these offsets share that
provenance. Field names are YRpp's own, not invented here.

## The headline: there is no magnetron locomotor

`[LocomotorBeam]`, the stock Magnetron warhead, reads:

```ini
IsLocomotor=yes
Locomotor={92612C46-F71F-11d1-AC9F-006008055BB5}
```

That CLSID is **`JumpjetLocomotionClass`** (documented on line 1 of YRpp's
`JumpjetLocomotionClass.h`; ctor `0x54AC40`, which calls the
`LocomotionClass` base ctor `0x55A6C0` exactly as YRpp declares it).

So the Magnetron is not a locomotor. It is a warhead that **imbues the jumpjet
locomotor onto its victim** and parents it to the firer. Everything that looks
like "magnetron behaviour" — the lift, the drag, the drop, and crucially the
*hand-back of control* — is jumpjet code.

## The state: two pointers and two bools

| Field | Offset | Set on | Meaning (YRpp's own comment) |
|---|---|---|---|
| `TechnoClass::LocomotorTarget` | `+0x2AC` | firer | "mag->LocoTarget = victim" |
| `TechnoClass::LocomotorSource` | `+0x2B0` | victim | "victim->LocoSource = mag" |
| `FootClass::IsAttackedByLocomotor` | `+0x6AD` | victim | "the unit's locomotor is jammed by a magnetron" |
| `FootClass::IsLetGoByLocomotor` | `+0x6AE` | victim | "a magnetron attacked this unit and let it go. falling, landing, or sitting on the ground" |
| `TechnoClass::BeingManipulatedBy` | `+0x428` | victim | set to the firer **during release**; "the pointee will be marked as the killer of whatever the victim falls onto" |
| `TechnoClass::ChronoWarpedByHouse` | `+0x42C` | victim | set to `firer->Owner` during release — that is the fall-kill credit |

`+0x6AD`/`+0x6AE` offsets are pinned by their neighbour `unknown_bool_6AC` in
YRpp's `FootClass.h`.

## `TechnoClass::ImbueLocomotor(FootClass* target, CLSID)` — `0x710000`

**Exactly one caller in the whole binary: `0x4696FB`** (inside
`BulletClass::Logics`, the `IsLocomotor=yes` detonation path). Thiscall,
`ECX` = firer; `target` arrives at `[esp+0x2C]`; the 16-byte CLSID is copied by
value from `WarheadTypeClass+0x15C`.

What it does, in order:
1. If the **firer** already holds a victim → `ReleaseLocomotor` (`0x7102A6`).
   If the **victim** is itself holding someone → release that too (`0x7102B7`).
2. Creates the new locomotor via the COM path at `0x5233A0`, then **overwrites
   `victim->Locomotor` (`FootClass+0x674`) and `Release()`s the old one**
   (`0x7102E5`–`0x7102F6`).
   ⚠ **The victim's original locomotor is destroyed, not saved anywhere.**
3. `firer->LocomotorTarget = victim` (`0x710307`),
   `victim->LocomotorSource = firer` (`0x710318`).
4. `victim->IsAttackedByLocomotor = 1` (`0x710352`).
5. Clears the victim's current mission/target (`0x6EA870(victim, -1, 0)`).

### The pre-grab gate chain (`0x4695EB`–`0x4696CE`, all skipping to `0x469AA4`)
- firer's previous victim released first (`0x4695FD`)
- target non-null, `+0x14 & 0x4` (is-a-Foot), plus two `WhatAmI` compares
- vtable `[+0x160]` on the target must return false
- **`victim->IsAttackedByLocomotor` must be 0** (`0x4696A2`) — an already-grabbed
  unit cannot be re-grabbed by anything
- a float compare `fild [bullet+0x6C]` vs `[victimType+0x380]` (`0x4696BA`);
  ⚠ *unverified* reading: a weight/liftability threshold

## `TechnoClass::ReleaseLocomotor(bool setTarget)` — `0x70FEE0`

Thiscall on the **holder** (`ECX` = firer), not the victim. Bails immediately if
`firer->LocomotorTarget` is null. Clears `victim->LocomotorSource`, then takes
one of two branches on vtable `[+0x1C8]`:
- `> 0`: sets `victim+0x425 = 1`, `IsBeingManipulated (+0x427) = 1`,
  `BeingManipulatedBy (+0x428) = firer`, `ChronoWarpedByHouse (+0x42C) =
  firer->Owner`, then vtable `[+0x3A0]` and `[+0x480](0,1)`.
- `<= 0`: vtable `[+0x480](0,1)`, `IsLetGoByLocomotor (+0x6AE) = 1`, `[+0x480]`
  again.

Finally clears `firer->LocomotorTarget`, and if `setTarget` calls firer vtable
`[+0x3C8](0)`.

Note it does **not** restore a locomotor — see the warning above. The victim is
left with the imbued locomotor still installed.

## Why alternate `Locomotor=` CLSIDs paralyse the victim — the root cause

`ReleaseLocomotor` has **11 callers**:

| Address | Context | Nature |
|---|---|---|
| `0x4695FD` | `BulletClass::Logics` | firer grabs a *new* victim |
| `0x7102A6`, `0x7102B7` | inside `ImbueLocomotor` | same reason |
| `0x707B70`, `0x707B97` | `TechnoClass` pointer-expiry | either party destroyed/detached |
| `0x44250C`, `0x454B5A` | `BuildingClass` | teardown |
| `0x4D9509`, `0x4DE5F0` | `FootClass` | teardown / ownership change |
| `0x7389BF` | `UnitClass` | teardown |
| **`0x54C1CB`** | **inside `JumpjetLocomotionClass`** | **the only "job finished" release** |

Every release except `0x54C1CB` is either *"something died"* or *"a new grab
replaced this one"*. The one that represents **"I have finished carrying this
unit, give it its controls back"** lives inside the jumpjet locomotor:

```
54c1a6   mov  eax,[esi+0xc]            ; LinkedTo (the victim)
54c1a9   mov  cl,[eax+0x6ad]           ; IsAttackedByLocomotor
54c1b1   je   0x54c1dc                 ; not magnetron'd -> normal jumpjet path
54c1b3   mov  [esi+0x80],0x0           ; clear jumpjet state
54c1bd   mov  eax,[eax+0x2b0]          ; victim->LocomotorSource (the magnetron)
54c1c7   push 0x1 / mov ecx,eax
54c1cb   call 0x70fee0                 ; captor->ReleaseLocomotor(true)
54c1d0   mov  [esi+0x50],0x4           ; jumpjet state := 4 (landed/done)
```

That the enclosing function belongs to `JumpjetLocomotionClass` is settled by
its private field: `[esi+0x50]` is initialised to `0` by the jumpjet ctor at
`0x54AC6D` and set to `4` here. ⚠ *Unverified* which jumpjet method it is
(`Process` is the obvious candidate).

**Consequence.** Set `Locomotor=` to Drive / Hover / Teleport / Tunnel /
Walker / Missile / DropPod and the engine happily imbues it — the imbue path is
CLSID-agnostic — but **no code anywhere in that locomotor calls
`ReleaseLocomotor`**. Therefore:

- `victim->IsAttackedByLocomotor` stays `1` forever → the unit never regains
  control, and (by the `0x4696A2` gate) can never be grabbed again either;
- `firer->LocomotorTarget` stays set → the firer believes it is still holding
  something. Its *next* shot releases the stale link at `0x4695FD`, which is
  why the paralysis sometimes appears to clear by itself;
- the victim's original locomotor was already `Release()`d, so there is nothing
  to restore.

There is **no beam-stop detection anywhere in this subsystem.** Vanilla never
needs one: the jumpjet locomotor decides when the job is done. A
"release when the weapon stops firing" feature therefore has to be built from
scratch, and must *construct* a replacement locomotor (the COM path at
`0x5233A0`, as `ImbueLocomotor` does) rather than restore a saved pointer.

## Where vanilla disables a grabbed victim

`IsAttackedByLocomotor` has **47 access sites**; the bulk cluster in
`0x54Axxx`–`0x54Dxxx` (the jumpjet locomotor itself). Three sit in
`TechnoClass`'s firing/targeting region and are the natural seats for a
"can the victim still shoot?" override:

| Address | Shape |
|---|---|
| `0x6FBF6B` | reads `LocomotorSource` at `0x6FBF57`, then the flag → `xor al,al; ret` (a bool capability gate returning **false**) |
| `0x6FC1A8` | flag set → jumps to the abort path `0x6FC86A` |
| `0x6FCD71` | flag set → skips a block that clears `[techno+0x2D0]` (function starts `0x6FCD40`, immediately before `SetTarget` `0x6FCDB0`) |

⚠ *Unverified*: the exact method identities of these three. `0x6FBF6B` sits
after `IsReadyToCloak` (`0x6FBDC0`) and `ShouldNotBeCloaked` (`0x6FBC90`) but
its own entry point was not pinned.

Four `FootClass` sites (`0x4DA934`, `0x4DA9AF`, `0x4DA9C1`, `0x4DA9F3`) sit in
the per-frame `FootClass` AI region (`0x4DA59F` is a known Phobos
`FootClass_AI` hook), which is the most promising seat for a per-frame
"is the beam still on me?" check.

## ⚠ VERIFIED TRAP: Phobos replaces the imbue path, killing every seat after it

**Do not hook anything between `0x4696CE` and `0x469AA4` and expect it to run.**
Phobos's release handler at `0x4696CE`
(`BulletClass_Detonate_ImbueLocomotor`, `Ext/WarheadType/Hooks.cpp`) is a
**full replacement**:

```cpp
DEFINE_HOOK(0x4696CE, BulletClass_Detonate_ImbueLocomotor, 0x6)
{
    enum { SkipGameCode = 0x469AA4 };
    ...
    pBullet->Owner->ImbueLocomotor(pTarget, pWH->Locomotor);
    return SkipGameCode;          // jumps past 0x4696FB AND 0x469700
}
```

It performs the imbue from C++ and returns `0x469AA4`, so the vanilla
`call ImbueLocomotor` at `0x4696FB` and everything up to `0x469AA4` never
execute when Phobos is loaded.

**VERIFIED** (2026-10-03): WeaponExt hooked `0x469700` — the instruction
immediately after the vanilla call — to post-process a magnetron grab. The
seat had perfect geometry, no registry overlap, and the hook-overlap and
hook-bounds checkers both passed it. It ran **zero times** in a live skirmish;
the only evidence was the complete absence of its log lines. Moving to
`ImbueLocomotor`'s own entry (`0x710000`, stolen bytes
`83 EC 1C | 53 | 55` — three whole instructions, no relative branch) fixed it,
because that function is the single funnel both the vanilla call site and
Phobos's C++ call must pass through.

**Generalisable lesson:** overlap checking compares *addresses*. It cannot see
a rival handler whose **return value** routes control around your seat. When
placing a hook downstream of another framework's hook in the same function,
read that handler's return statement, not just the registry row. See also
`_TRAPS-READ-FIRST.md` (full-replacement functions, legal-vs-live) and the
same shape in `Buildability-Prerequisites.md` (Ares replacing `0x4F7870`).

Corollary for this subsystem: `0x710000` is the correct seat for *any*
magnetron work, and it is unhooked by every framework.

## Framework co-tenancy

None of `0x710000`, `0x70FEE0`, `0x4696FB` or `0x54C1CB` appears in
`registry/hooks.csv` — **this entire subsystem is unhooked by Phobos, Ares,
Antares and Kratos.** Nearby occupied addresses to avoid colliding with:
`0x4696CE` (Phobos `BulletClass_Detonate_ImbueLocomotor`), `0x46954C` (Phobos
`IsLocomotor` bunker fix), `0x469672` (Phobos PR#352), and the droppod/rocket
locomotor clusters at `0x4B5B70`/`0x4B607D` and `0x6622E0`.
