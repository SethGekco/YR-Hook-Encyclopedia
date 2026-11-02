# Engineer Capture

An engineer taking an enemy building is **two subsystems bolted together**, and
almost every mistake here comes from hooking the wrong one:

1. **The infantry side** — the engineer is given `Mission::Capture`, paths to the
   target, and on arrival `InfantryClass::UpdatePosition` decides *capture vs.
   damage vs. repair* and then asks the building to change hands.
2. **The building side** — `BuildingClass::SetOwningHouse` (the community also
   calls it `ChangeOwnership`) runs the owner-change bookkeeping. This is the
   "building was captured" event — **but it fires for every owner change**, not
   just engineers.

Execution order for a successful capture:

```
Mission::Capture           0x4D4B43   engineer acquires the building as Destination     (EDI = infantry)
  → InfantryClass::UpdatePosition
      0x519D9C   arrival: capture-or-damage decision                                    (ESI = engineer, EDI = building)
      0x519F71   immediately before the house flips (mind-control teardown)             (EDI = building)
      → BuildingClass::SetOwningHouse / ChangeOwnership
          0x448312 … 0x44939F   old-spy / tech / factory-plant / sensor / academy /
                                owned-lists / buildup bookkeeping                        (ESI = building)
          → TechnoClass owner-change tracking
              0x7015C9   auto-death / tracking, all technos                             (ESI = techno, EBP = new owner)
```

> ⚠ **The `this`/target register is not stable across these sites.** In
> `InfantryClass::UpdatePosition` the engineer is **ESI** and the building is
> **EDI**. At the `Mission::Capture` handler `0x4D4B43` the infantry is **EDI**.
> In the `ChangeOwnership` cluster the building is **ESI**. Copy a `GET` macro
> from the wrong site and you dereference the wrong pointer — usually a silent
> `C0000005`, not a compile error.

Neither half is spy infiltration ([Spy-Infiltration.md](Spy-Infiltration.md),
`0x4571E0`) nor mind control ([CaptureManagerClass], `0x471xxx`). Those are
covered elsewhere; the "not this" section below lists the engineer-named hooks
that are *not* the capture event.
