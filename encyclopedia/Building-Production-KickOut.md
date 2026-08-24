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

### `0x443B90` — BuildingClass::KickOutUnit (function entry)

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
`[esp+4] = TechnoClass* pTechno`; `[esp+8] = CellStruct cell`. A hook here needs
size **`0xB`** to cover whole instructions — the prologue is
`push esi; mov esi,ecx; push edi; cmp [esi+0xAC],0x13` (1+2+1+7 = 11 bytes); the
next instruction (`je`) is at `0x443B9B`. The entry is NOP-padded
(`0x443B86`–`0x443B8F`), confirming the function boundary.

**Inner type branches (where the frameworks actually hook), for reference.**
`EDI` holds `pTechno` throughout the function, so these read the ejected unit from
`EDI`:
- `0x443CCA` — AircraftType branch (Antares/Ares `0xA`, Phobos `0xA`)
- `0x444119` — UnitType branch (Antares/Ares `0x6`)
- `0x444131` — InfantryType branch (Antares `0x6`)
- `0x4440B0` — CloningFacility (Antares/Phobos)

**Confirmed via.** objdump of `gamemd-spawn.exe` (entry prologue, NOP padding,
`EDI = pTechno` at `0x44411F` `mov edx,[edi]; mov ecx,edi; call [edx+0x2c]`);
Antares PDB label names for the inner branches; registry cross-reference for the
framework consumers; in-game test of a built-only gate stamped at this entry.
