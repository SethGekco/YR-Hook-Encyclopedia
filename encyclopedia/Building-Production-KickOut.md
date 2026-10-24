# Building production: KickOutUnit (a factory ejects a finished unit)

`BuildingClass::KickOutUnit` is where a production structure pushes a *completed*
unit out onto the map — the closest thing the engine has to a "this unit was
built by a factory" event. Paradrop, crates, map-placed units, and DLL-spawned
units do **not** pass through here, which makes it the right hook for a
"built-only" gate (e.g. a `OnlyBuilt=`/`BuiltOnly=` tag that must exclude
paradropped units).

The frameworks hook the per-type *branches* inside the function; the **entry** is
unclaimed and is the clean single point if you just need the unit being ejected.

---

### `0x443C60` — BuildingClass::KickOutUnit (function entry)

**Framework names.** None hook the entry. (Antares/Ares/Phobos hook the inner
type branches — see below.)

**What it does.** Entry of `KickOutUnit(TechnoClass* pTechno, CellStruct cell)`,
a `__thiscall`: `ECX` = the producing `BuildingClass*`, and on entry
`[esp+4]` = `pTechno` (the finished unit being kicked out), `[esp+8]` = the target
cell (a `CellStruct`, one dword). Fires once per unit ejected from a factory
(barracks/war factory/etc.), for units, infantry, aircraft and cloned units.

**Why it's useful.** It cleanly distinguishes *factory-built* units from every
other way a techno appears. A "built" flag stamped here (a `set<TechnoClass*>`,
set at this entry, checked without consuming, cleared in the `TechnoClass` dtor at
`0x6F4500`) lets a gate admit only built units — paradropped/crate/map/spawned
units are simply never stamped. **Verified in-game:** switching a Host/spawn gate
from "mark what I spawned" to "mark what a factory kicked out" here fixed
paradropped units wrongly triggering the ability.

**What it does *not* do — easily mistaken.** It is not "a unit was created" (that
is the ctor, and covers paradrop/crate too) and not "production finished" (a
`FactoryClass` concept). It is specifically the *placement onto the map from a
factory*. It can be entered for a unit that then fails to find an exit cell; if
you stamped it, rely on the dtor to clear the flag when that unit is destroyed.

**Register / calling convention.** Entry, `__thiscall`: `ECX = BuildingClass*`;
`[esp+4] = TechnoClass* pTechno`; `[esp+8] = CellStruct cell`. The prologue is
`sub esp,0x130; push ebx; push ebp; push esi; push edi; mov edi,[esp+0x144]` — that
last load is `pTechno` (`0x130 + 4 pushes = 0x140`, so `[esp+0x144] == entry
[esp+4]`). A hook at the entry uses size **`0x6`** (the `sub esp,0x130`). The entry
is a clean function boundary: the previous function ends `ret 0x4` at `0x443C5C`
with NOP padding at `0x443C5F`.

**⚠ Do not hook `0x443B90`.** That is the *previous* function (it ends `ret 0x4`
at `0x443C5C`); it is NOT KickOutUnit even though it sits just before the
`0x443CCA` branch. Hooking it to mark "built" units marks nothing useful.

**Inner type branches (where the frameworks actually hook), for reference.**
`EDI` holds `pTechno` throughout the function, so these read the ejected unit from
`EDI`:
- `0x443CCA` — AircraftType branch (Antares/Ares `0xA`, Phobos `0xA`)
- `0x444119` — UnitType branch (Antares/Ares `0x6`)
- `0x444131` — InfantryType branch (Antares `0x6`)
- `0x4440B0` — CloningFacility (Antares/Phobos)

## Refining "built": the predicate, and an ordering trap (2026-10-23)

Two additions from using this entry to drive a per-type "only if constructed"
profile.

### `Factory->Object == pTechno` beats "is a production factory"

The stamp this page describes admits everything a factory ejects. That is not
the same as "the thing the factory was building". The sharper test is

```
pBuilding->Factory && pBuilding->Factory->Object == pTechno
```

which additionally excludes anything else the same building might eject —
notably a **clone** (which never matches the factory's current product) and a
**free unit**. It matters for a barracks that also clones, where the clone and
the primary leave the *same* building, so building identity cannot separate them.

For the record, free units never reach here at all: they go out through
`Grand_Opening`'s own `NearByLocation` placement
(`0x446AA9`–`0x446EE1`, see
[Building-GrandOpening-FreeUnits.md](Building-GrandOpening-FreeUnits.md)), which
is a separate path. So the exclusion list this page already gives — paradrop,
crates, map-placed, DLL-spawned — extends to free units too.

### ⚠ The entry runs BEFORE the clone dispatch in the same function

The clone dispatch sites (`0x444DBC` infantry, `0x44441A` naval, `0x4445F0`
vehicle) are further down `KickOutUnit` than the entry. So anything the entry
does to the **primary product** is already true when cloning resolves what to
clone.

Concretely, a handler at the entry that **changes the product's type** — a
built-only variant, a type conversion, a profile redirect — will have the clone
logic read the *changed* type and clone that. If the variant type is itself
suffixed (`GGI.construct`), a suffix-based clone resolver then goes looking for
`GGI.construct.clone` and misses, and the clone silently comes out as the
construct variant.

The fix is not to move the hook (the per-category branches are triple-hooked and
hold the house in a different register each). Record the pre-change type at the
entry and have the clone side resolve from that. Stated as a rule: **clones are
clones of what was built**, not of the built-only variant.

**Confirmed via.** Source reading of the call order inside `KickOutUnit`
(entry `0x443C60` vs the dispatch sites listed above), plus CloningExt's own
clone-vs-primary predicate which already relied on `Factory->Object`.
**UNTESTED in game** at the time of writing — the ordering claim is from the
addresses' relative position in one function, which is not in doubt, but the
observable consequence has not been played.

**Confirmed via.** objdump of `gamemd-spawn.exe` (entry `0x443C60`
`sub esp,0x130 … mov edi,[esp+0x144]`; boundary `ret 0x4`@`0x443C5C` + NOP pad;
`EDI = pTechno` at `0x44411F` `mov edx,[edi]; mov ecx,edi; call [edx+0x2c]`);
Antares PDB label names for the inner branches; registry cross-reference for the
framework consumers; in-game test of a built-only gate stamped at this entry.
