# Spy Infiltration & Stolen Tech

Building infiltration by a spy, the effects it dispatches, and the stolen-tech
index model the Ares-lineage frameworks built on top of it.

---

### `0x4571E0` — BuildingClass::Infiltrate

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Infiltrate` | 0x5 | `src/Ext/Building/Hooks.Infiltrate.cpp` |
| Antares | `BuildingClass_Infiltrate_Standard` (`0x4574D2`, `0x457533`) | 0x6 | same |

**What it does.** Vanilla dispatches the hardcoded spy effects (power outage,
radar outage, credits steal, veterancy boost, reset build timer, …) according to
the victim building's type. Antares hooks the entry, runs its own
`BuildingExt::InfiltratedBy(pEnterer)` dispatch, and returns **`0x4575A2`** to
skip the vanilla body when its own handler consumed the event.

**What it does *not* do — easily mistaken.**

* **Engineers do not come through here.** Capture is a different code path
  entirely (`InfantryClass::UpdatePosition` multi-engineer handling around
  `0x519D9C`, then `BuildingClass::ChangeOwnership` — labels at `0x448312` /
  `0x448D95`). "Give an engineer spy-like effects" therefore cannot be done by
  making the engineer look like a spy; the effect dispatch has to be lifted out
  and called from both paths.
* **It is not a general "building was entered" event** — only infiltration.
* The two `_Standard` sites (`0x4574D2`, `0x457533`) exist because the *vanilla*
  effects do not repaint the sidebar; Antares forces `SidebarNeedsRepaint()`
  there. Anything that changes buildability from an infiltration needs the same
  repaint or the cameo state lags until the next unrelated repaint.

**Interactions — co-hooking is safe here, conditionally.** Syringe runs **every**
registered handler for an address; only the **first non-zero return** decides
control flow. A third-party DLL that hooks `0x4571E0` and always returns 0 will
run its own effects and then let Antares (or vanilla) decide the jump, in either
load order. The moment it wants to *suppress* the vanilla/Antares effects it must
return a jump target, and then load order decides the winner — a real conflict.

**Register / calling convention.** `ECX = BuildingClass*` (the building entered),
`[ESP+0x4] = HouseClass*` (the infiltrator's house).

**Confirmed via** Antares source (`develop`, `src/Ext/Building/Hooks.Infiltrate.cpp`)
and the PDB symbol map (`0x4571E0 BuildingClass_Infiltrate`).

---

## Structural note — the stolen-tech index ceiling is 31, and it is a storage choice

Vanilla tracks only three flags: `HouseClass::Side0TechInfiltrated` /
`Side1` / `Side2`, consumed by `HouseClass::HasAllStolenTech` against
`TechnoTypeClass::RequiresStolenAlliedTech` / `…SovietTech` / `…ThirdTech`
(YRpp `HouseClass.h:625`).

The Ares-lineage frameworks generalise this to *indexed* stolen tech:

| | Storage | Ceiling |
|---|---|---|
| Antares — building grant | `BuildingTypeExt::StolenTechIndex`, a **`DWORD` bitfield** (`src/Ext/BuildingType/Body.cpp:230`) | index ≤ 31, logged as an error above that |
| Antares — house ledger | `HouseExt::StolenTech`, `std::bitset<32>` | 32 |
| Antares — requirement | `TechnoTypeExt::RequiredStolenTech`, `std::bitset<32>`, from `Prerequisite.StolenTechs=` | 32 |

Two things worth knowing before designing around this:

1. **The 32 ceiling is arbitrary** — it is the width of the chosen integer, not
   an engine constraint. Nothing in `gamemd.exe` knows what a "tech index" is;
   the whole system lives in framework ext data.
2. **A building may already grant several indices at once.** Antares parses
   `SpyEffect.StolenTechIndex=` as a *comma list*, OR-ing the bits
   (`Body.cpp:230-239`). The common belief that it is one index per building is
   wrong for Antares.

**Confirmed via** Antares source (`develop`) and YRpp headers. **Unverified:**
classic Ares' parser (not in the registry; the docs describe the same tag).

---

## Related

* `Buildability-Prerequisites.md` — where stolen tech is consumed
  (`HouseClass::CanBuild`, and the `0x4F8361` epilogue trap).
* `Veterancy-Abilities.md` — `TechnoClass::HasAbility`, the choke point for
  ability-based effects.
