# Subsystem: converting a unit's TechnoType at runtime

How to make one live object answer as a *different* `TechnoTypeClass`, and why
this is the cheap way to make any type-level tag per-unit — including the tags
every "per-instance stat" attempt gives up on.

**There is no hook on this page.** That is the point worth taking away: the
mechanism is a field assignment plus a fix-up list, called from wherever you
already run per-unit logic. Several projects have reached for a read-site hook
per tag; none is needed, and the hook space does not have room for it.

## The headline: the engine re-reads the type pointer at every read site

Nearly every type field is read as `pThis->Type->Field`. The engine
dereferences **the instance's own pointer, at the read site, every time** — it
does not cache a resolved type into the object. So an object whose type pointer
has been repointed answers *every* one of those reads with the new type's
value, with no further work.

This is why the common approach is backwards. Hooking the read site for
`Armor`, then `Speed`, then `Sight` is hundreds of hooks for a result one
assignment already produces — and a *missed* read site is worse than an
unsupported tag, because the field then behaves inconsistently between code
paths (e.g. armour that applies in one damage path and not another).

## Where the pointer lives: NOT on TechnoClass

There is no single `TechnoClass::Type`. Each subclass declares its own typed
field, so the slot has to be selected on RTTI:

| `WhatAmI()` | field | type |
|---|---|---|
| `AbstractType::Infantry` | `InfantryClass::Type` | `InfantryTypeClass*` |
| `AbstractType::Unit` | `UnitClass::Type` | `UnitTypeClass*` |
| `AbstractType::Aircraft` | `AircraftClass::Type` | `AircraftTypeClass*` |
| `AbstractType::Building` | `BuildingClass::Type` | `BuildingTypeClass*` |

`WhatAmI()` of the old and new **type** must match as well. A `UnitClass`
instance cannot wear an `InfantryTypeClass`: the field is typed, and the
object's vtable would disagree with its own RTTI.

### Buildings are excluded, and not for lack of trying

A building's foundation is written into **map cells** at `Unlimbo`. Repointing
its type does not re-lay the occupancy, so the old footprint stays marked and
the new one is never claimed. Phobos refuses `BuildingClass` for this reason
and only accepts `FootClass`. Treat vehicles / infantry / aircraft as the
supported set.

## The fix-up list: what does NOT follow the pointer

State *copied into the instance at creation* keeps its old value. This list is
the valuable part of the page, and it is not derived from reading the binary —
it is what Ares and Phobos converged on in a shipped feature:

| state | why the pointer does not fix it | what to do |
|---|---|---|
| `Health` | current HP is absolute; the maximum comes from the type, so a 50%-damaged unit reads as full or overfull after the move | `SetHealthPercentage(oldHealth / oldType->Strength)`, then `EstimatedHealth = Health` |
| house tallies | counters are keyed **by type** | `RegisterLoss` + `RemoveTracking` **before**, `AddTracking` + `RegisterGain` **after**, then `RecheckTechTree = true` |
| `Ammo` | current ammo is on the object and the new maximum may be smaller | clamp, and `Mark(MarkType::Change)` if it was reduced |
| ROT | copied into the facing object | `PrimaryFacing.SetROT(newType->ROT)`, or `SecondaryFacing` for aircraft |
| locomotor | a COM object instantiated from the type's CLSID at `Unlimbo` | if the CLSID differs: drain `End_Piggyback` in a loop, then `CreateInstance` + `Link_To_Object` |
| CLEG freeze | `TemporalImUsing->Target` is left pointing at stale state | `LetGo()` first |

**Order matters on the house tallies.** Untrack under the old type, repoint,
then track under the new one. Doing it in any other order double-counts, or
counts the unit as the wrong type for build limits.

**Drain the piggyback stack before replacing a locomotor.** Releasing a
piggybacked locomotor from underneath leaves the unit stuck — the same failure
mode [Magnetron-Locomotor-Imbue.md](Magnetron-Locomotor-Imbue.md) documents
when the jumpjet imbue is torn down out of order.

**The HP rescale is lossy.** It is proportional, so a round trip does not
return the original value and repeated conversion *drifts*. Anything that
converts on a condition needs a dwell/deadband, or a unit sitting on a
threshold boundary converts every tick and bleeds HP while thrashing its
locomotor.

## Reversing it

Phobos' conversion is one-way: a warhead converts a unit and that is its new
identity. Converting **back** needs nothing new — the same `Repoint` in the
other direction — but it does need the *original* type remembered from the
**first** conversion and never overwritten, or a second conversion makes its
own target the thing you restore to.

Do **not** reverse on destruction. The engine is already registering the loss;
moving house tracking for a dying unit double-counts it. Drop the bookkeeping
instead.

## Save / load and multiplayer

Both work, with one condition each, and both fall out of existing machinery:

* **Save/load.** Type data is re-parsed from the INI on load
  ([Techno-Type-Lifecycle.md](Techno-Type-Lifecycle.md)) and the saved type
  pointer is swizzled like any other
  ([Savegame-Stream.md](Savegame-Stream.md)), so a converted unit reloads
  converted — **provided the type it points at still exists at load**. A
  synthesised type must therefore be synthesised deterministically, before
  parsing, on every load.
* **Sync.** Conversion changes house tallies, which feed the CRC
  ([Multiplayer-Sync-CRC-Logging.md](Multiplayer-Sync-CRC-Logging.md)). Every
  client must convert the same unit on the same frame from the same inputs. If
  several conditions could each convert the same unit, the tie-break must be
  something identical everywhere — declaration order works; iteration order of
  a pointer-keyed container does not.

## Not to be confused with

* **`DeploysInto` / `UndeploysInto`** — vanilla's own transformation, which
  *destroys and recreates* the object. That is how cross-category change is
  done; it is not this.
* **The draw-time type swap** — repointing around `UnitClass::DrawAsVXL` /
  `DrawAsSHP` / `InfantryClass::DrawIt` and restoring immediately. Cheap,
  reversible, no fix-ups, and limited to what the renderer and
  `TechnoClass::GetWeapon` read. Prefer it when art and weapons are all you
  need; it cannot deliver anything else, and the two must not be combined on
  one object — the draw swap's own save/restore will put the original type back
  mid-frame and undo the conversion.

## Confirmed via

* **Phobos** `develop` (local checkout at commit `47475624`),
  `src/Ext/Techno/Body.cpp:345` `TechnoExt::ConvertToType` — the full fix-up
  list, the `WhatAmI()` guard, the `FootClass`-only restriction, and the
  locomotor replacement (which its own comment marks as adapted from Ares 0.A's
  abduction code and **untested**). `src/New/Type/Affiliated/TypeConvertGroup.cpp`
  is the warhead/SW trigger side.
* **YRpp** for every field and signature used above: `TechnoClass.h:728-729`
  (`PrimaryFacing`/`SecondaryFacing`), `ObjectClass.h:299-306`
  (`Health`/`EstimatedHealth`/`InLimbo`), `ObjectClass.h:209`
  (`SetHealthPercentage`, `0x5F5C80`), `HouseClass.h:504-507,753-756`,
  `TechnoTypeClass.h:210` (`Locomotor` as `_GUID`), `LocomotionClass.h:131,139`.
* **Not verified in game at the time of writing.** TraitExt drives conversion
  from a condition gate rather than a warhead, and that path has not yet been
  played. The mechanism is Phobos' shipped one; the *reverse* direction and the
  gate-driven trigger are new here and unproven.
* **Deliberately NOT used:** Ares/Antares' own exported `ConvertTypeTo`. Phobos
  binds it at a hardcoded module offset (`0x43650` on Ares 3.0, `0x44130` on
  3.0p1, `src/Utilities/AresAddressInit.cpp:31,76`), which breaks on any build
  whose layout differs. The vanilla path above needs nothing but YRpp.

## Related pages

- [Techno-Instance-Lifecycle.md](Techno-Instance-Lifecycle.md) — where to call
  this from, and the removal/death traps around it.
- [Techno-Type-Lifecycle.md](Techno-Type-Lifecycle.md) — types are re-parsed on
  load, which is what makes a converted unit reloadable.
- [Magnetron-Locomotor-Imbue.md](Magnetron-Locomotor-Imbue.md) — locomotor
  replacement done the engine's own way, and the piggyback ordering trap.
- [INI-Read-Inheritance.md](INI-Read-Inheritance.md) — `$Inherits`, which is how
  you get a conversion target that differs from the original in only the keys
  you meant.
