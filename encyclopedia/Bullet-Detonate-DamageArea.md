# Subsystem: Bullet detonation & area damage

What happens, in order, inside `BulletClass::Detonate` (`0x4690B0`), where
`MapClass::DamageArea` (`0x489280`) sits in that order, where `CellSpread` is
read, and the cell-count table that bounds it. Addresses for standard YR
`gamemd.exe`, imagebase `0x400000`.

**Provenance:** hook rows from `registry/hooks.csv`; handler bodies, return
values and register/stack reads from Phobos `develop` as read 2026-09-25
(`src/Ext/Bullet/Hooks.DetonateLogics.cpp`, `src/Ext/WarheadType/Hooks.cpp`,
`src/Ext/Bullet/Body.cpp`, `src/Ext/Techno/Hooks.Firing.cpp`); table helpers
from YRpp `CellSpread.h` / `BulletClass.h` / `ObjectClass.h` (commit
`3ba9495`). **Nothing on this page has been independently disassembled.** The
position of the vanilla `DamageArea` call is *inferred* from Phobos's
`InDamageArea` flag protocol (below) — marked RE-VERIFY.

## Detonate, in execution order

| Address | Size | Phobos seat | Registers / stack | Phobos returns |
|---|---|---|---|---|
| `0x4690C1` | 0x8 | `BulletClass_Logics_DetonateOnAllMapObjects` | ESI = bullet | 0, or `ReturnFromFunction` when its detonate-on-all-objects feature fires |
| `0x4690D4` | 0x6 | `BulletClass_Logics_NewChecks` | ESI = bullet, EAX = warhead, `[ebp+0x8]` = `CoordStruct*` | `GoToExtras` (`0x469AA4`) when the target fails the warhead's trigger conditions, `SkipShaking` (`0x469130`), else 0 |
| `0x46920B` | 0x6 | `BulletClass_Detonate` | — | 0 — **runs Phobos's warhead effects** (`WarheadTypeExt::Detonate`) and clears `InDamageArea` |
| `0x4692BD` | 0x6 | `BulletClass_Logics_ApplyMindControl` | ESI = bullet | `SkipGameCode` |
| `0x469453` | 0x6 | `BulletClass_Logics_TemporalUnderGround` | EAX = target | `NotOK` / `OK` |
| `0x46954C` | 0x6 | `BulletClass_Logics_IsLocomotor_Bunker` | ECX = target | `CannotImbue` / 0 |
| *(vanilla `DamageArea` call — inferred here)* | | | | |
| `0x469A75` | 0x7 | `BulletClass_Logics_DamageHouse` | ESI = bullet, ECX = house | 0 |
| `0x469AA4` | 0x5 | `BulletClass_Logics_Extras` | ESI = bullet, `[ebp+0x8]` = `CoordStruct*` | 0 — ExtraWarheads, ReturnWeapon, UnlimboDetonate; **sets `InDamageArea = true`** |
| `0x469AA4` is also `GoToExtras`, the jump target of `0x4690D4` | | | | |
| `0x469B44` | 0x6 | `BulletClass_Logics_LandTypeCheck` | ESI = bullet | `SkipChecks` / 0 |
| `0x469C46` | 0x8 | `BulletClass_Logics_DamageAnimSelected` | ESI = bullet, **EBX = the damage `AnimTypeClass*` the engine just picked**, coords at `STACK_OFFSET(0xA4, -0x40)` | **always** `SkipGameCode` (`0x469C98`) — Phobos creates the anim(s) itself |
| `0x469D1A` | 0x6 | `BulletClass_Logics_Debris` | ESI = bullet | `SkipGameCode` |
| `0x469EC0` | 0x6 | `BulletClass_Logics_AirburstWeapon` | ESI = bullet | `SkipGameCode` |

`Detonate` has an **EBP frame**: Phobos reads the detonation coordinates at
`[ebp+0x8]` from two different seats in it.

### Where `DamageArea` sits (inferred, RE-VERIFY)

`WarheadTypeExt::InDamageArea` is a per-warhead flag Phobos uses so its warhead
effects run **once** per detonation, whichever path caused it:

- `0x46920B` (bullet path) runs the effects, then sets `InDamageArea = false`.
- `0x489286` (`MapClass_DamageArea`, the `DamageArea` entry) runs the effects
  **only if `InDamageArea` is true**.
- `0x469AA4` (Extras) sets it back to `true`.

For a bullet not to get its effects twice, the vanilla `DamageArea` call must
come **after `0x46920B` and before `0x469AA4`**. The flag is then `false` when
`DamageArea` is entered from the bullet path and `true` for every other caller
(death explosions, direct `DamageArea` calls). So:

- **The engine picks the damage anim after `0x469AA4`** (EBX at `0x469C46`), and
  that happens **after** area damage.
- A per-detonation override bracketed from `0x4690C1` (in) to `0x469AA4` (out)
  covers both vanilla area damage and Phobos's bullet-path warhead effects.
  It does **not** cover the anim pick, debris or airburst.

## `MapClass::DamageArea` (`0x489280`)

| Address | Size | Owner | Notes |
|---|---|---|---|
| `0x489286` | 0x6 | Phobos `MapClass_DamageArea` (+ a second Phobos handler `MapClass_DamageArea_BeforeAll`, `src/Misc/Hooks.BugFixes.cpp`) | ECX = `CoordStruct*`; `[ebp+0x8]` = source `TechnoClass*`, `[ebp+0xC]` = `WarheadTypeClass*`, `[ebp+0x14]` = source `HouseClass*`. Both return 0. |
| `0x48928C` | 0x6 | Phobos (registry: `MapClass_DamageArea_CellSpread`, `src/Ext/Bullet/Hooks.cpp`) | **Not found in `develop` as of 2026-09-25** — the registry row may predate a move/removal. RE-VERIFY. |
| `0x489430`, `0x4894C1`, `0x48979C`, `0x4897C3`, `0x48985A`, `0x4898BF` | — | Phobos `CellSpread_Cylinder` family (`src/Ext/WarheadType/Hooks.cpp`) | **`CellSpread` / the Z distance are re-read at several points inside `DamageArea`** |
| `0x4896BF`, `0x4899B3`, `0x489BDB`, `0x489E47` | — | Phobos DamageItems / Rocker fixes (`src/Misc/Hooks.BugFixes.cpp`) | per-cell / per-object loops |
| `0x4899DA` | 0x7 | Phobos `MapClass_DamageArea_DamageUnderGround` | returns 0 |

## The cell-count table (what bounds `CellSpread`)

YRpp `CellSpread`:

- `NumCells(n)` = `reinterpret_cast<size_t*>(0x7ED3D0)[n]`: the number of cell
  offsets within spread `n`.
- `GetCell(i)` = `reinterpret_cast<const CellStruct*>(0xABD490)[i]`: the
  offsets, grouped by ring.
- `GetDistance(dx, dy)` = longer axis + half the shorter (integer).

**The table's length is not recorded anywhere we could find** (YRpp gives no
bound, and there's no ModEnc/Phobos doc line). A `CellSpread` past the end
indexes whatever follows `0x7ED3D0`. It can be **measured** safely at runtime
without disassembly: entry `n` must equal the count of `(dx,dy)` with
`GetDistance(dx,dy) <= n`. The last `n` that matches is the table length − 1.
This only reads the game's static data. Measured value: **not yet recorded
here** — add it once a live run logs it.

## Bullet ↔ firer seats

| Address | Size | Phobos seat | Notes |
|---|---|---|---|
| `0x6FF660` | 0x6 | `TechnoClass_FireAt_LateLogic` (also Kratos `TechnoClass_FireAt_ObstacleCellUnset`, same size) | ESI = firer; the **freshly created bullet** at `STACK_OFFSET(0xB0, -0x74)` = `[esp+0x3C]`; Phobos returns 0. The one Fire seat where firer and new bullet are both in hand, so it's the place to capture anything about the firer that must survive the firer dying. |
| `0x4664BA` | 0x5 | `BulletClass_CTOR` | ESI = bullet (Owner not yet assigned). |
| `0x4665E9` | 0xA | `BulletClass_DTOR` | ESI = bullet; returns 0. |

A bullet's **damage lives in `ObjectClass::Health`** (`BulletClass` has no
separate damage field in YRpp).

## What it does *not* do — easily mistaken

- **`0x469AA4` is not "the end of Detonate".** Damage-anim selection
  (`0x469C46`), debris and airburst all run after it. Also, `0x4690D4` jumps
  *to* it, so code there runs even when vanilla damage was skipped.
- **Phobos warhead effects do not run in Extras.** In the bullet path they run
  at `0x46920B`; for non-bullet `DamageArea` calls they run at the `DamageArea`
  entry `0x489286`. Only ExtraWarheads / ReturnWeapon / UnlimboDetonate are in
  Extras.
- **Patching one `CellSpread` read in `DamageArea` does not resize the
  explosion.** The spread is re-read at several points (the Cylinder hook
  family). Change the warhead's field for the duration of the detonation and
  put it back afterwards instead. The field is shared by every house, so this
  must be strictly scoped. Nested detonations (death weapons firing inside
  `DamageArea`) re-enter `Detonate` for the same or other warheads.
- **`CellSpread` is not unbounded.** See the table above.
- **Co-hook liveness at `0x469C46` / `0x4692BD` / `0x469D1A` / `0x469EC0`.**
  Phobos returns non-zero there unconditionally. Whether that stops *later*
  handlers at the same address is **unresolved** (see
  `Syringe-Stub-Semantics.md`: contradicting observations). Prove a co-hook is
  live with a log line before relying on it.

## Used by / interactions

- Phobos owns nearly every seat above; Antares/Ares/Kratos have none in
  `0x4690C1`–`0x469EC0` per the registry.
- Incidental consumer: the private WeaponExt DLL co-hooks `0x4690C1` /
  `0x469AA4` / `0x469C46` / `0x6FF660` / `0x4665E9` at Phobos's sizes to scale
  `CellSpread` per detonation. CI overlap/bounds checks against this registry
  pass. **No in-game confirmation yet.**

## RE-VERIFY

- [ ] Disassemble `0x46920B`–`0x469AA4` and confirm the vanilla
      `MapClass::DamageArea` call lies in that window (inferred above).
- [ ] Record the cell-count table length (`0x7ED3D0`) from a live measurement
      or disassembly of the table's producer.
- [ ] Locate the `0x48928C` Phobos hook in current source, or mark it removed.
- [ ] Confirm `ReceiveDamage`'s falloff reads `DistanceFromEpicenter` against
      the warhead's current `CellSpread` (i.e. `PercentAtMax` is applied inside
      `ReceiveDamage` / `GetTotalDamage`, not inside `DamageArea`).
