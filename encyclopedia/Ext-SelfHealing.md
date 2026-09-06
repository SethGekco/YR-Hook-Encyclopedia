# Subsystem: Self-healing

`TechnoTypeClass::SelfHealing=` (bool) with **global** rate/amount in
`RulesClass`. Entries sorted by address.

**Orientation.** Vanilla exposes no per-type control at all: the step size and
period come from `RulesClass::SelfHealInfantryFrames` / `SelfHealInfantryAmount`
and `SelfHealUnitFrames` / `SelfHealUnitAmount`, which are global. **Antares
replaces the whole system**, so on any Antares build those globals are dead and
the per-type tags below are what actually run.

---

### `0x70BE80` — TechnoClass::ShouldSelfHealOneStep

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_ShouldSelfHealOneStep` | 0x5 | src/Ext/Techno/Hooks.cpp |
| Ares | `TechnoClass_ShouldSelfHealOneStep` | 0x5 | src/Ext/Techno/Hooks.cpp |

**What it does.** Vanilla decides whether *this* frame produces a heal step.
Antares **replaces the function outright**:

```cpp
GET(TechnoClass* const, pThis, ECX);
R->EAX(TechnoExt::ExtMap.Find(pThis)->GetSelfHealAmount() > 0);
return 0x70BF46;                      // never returns 0
```

so the vanilla body (which reads `RulesClass+0x16E0` and the global frame
counters) never executes.

---

### `0x6FA743` — TechnoClass::Update, self-heal step

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_Update_SelfHeal` | 0xA | src/Ext/Techno/Hooks.cpp |
| Ares | `TechnoClass_Update_SelfHeal` | 0xA | src/Ext/Techno/Hooks.cpp |
| Phobos | `TechnoClass_AI_SelfHealing_BuildingGraphics` (`0x6FA781`) | 0x6 | src/Misc/Hooks.BugFixes.cpp |
| Phobos | `TechnoClass_AI_SelfHealGain` (`0x6FA793`) | 0x5 | src/Ext/Techno/Hooks.cpp |

**What it does.** Antares replaces the step itself: it blocks crashing/sinking
technos (`return 0x6FA941`), then applies `pThis->Health += GetSelfHealAmount()`
and returns `0x6FA75A`, or `0x6FA793` when the amount is zero. Note `0x6FA793`
is where Phobos's `SelfHealGain` hook lives, so the two compose.

**What it does *not* do — easily mistaken.** Because Antares owns both this and
`0x70BE80`, **any DLL adding its own per-type self-heal tags is duplicating work
that already exists**, and would have to out-return Antares (i.e. be listed
earlier in the Syringe `-i=` list) to have any effect at all.

---

## Antares' per-type tag surface (this is what modders should use)

Read in `Ext/TechnoType/Body.cpp:452-455`; applied in
`TechnoExt::ExtData::GetSelfHealAmount()` (`Ext/Techno/Body.cpp:781`).

```ini
[TechnoType]
SelfHealing=yes                ; vanilla gate; Ability::SelfHeal also qualifies
SelfHealing.Rate=              ; MINUTES between steps. default RulesClass::RepairRate
SelfHealing.Amount=            ; HP per step. default 1
SelfHealing.Max=               ; fraction of Strength to heal up to. default 1.0
SelfHealing.CombatDelay=       ; frames after taking damage during which it will
                               ; not heal. default 0
```

`Amount` and `Max` are `Promotable<T>`, so each also accepts veterancy variants —
`SelfHealing.RookieAmount=`, `.VeteranAmount=`, `.EliteAmount=` (and the same for
`Max`). Setting the bare key sets all three.

**⚠ The rate is in MINUTES, not frames.** Antares converts with
`frames = max(rate * 900, 1)` (900 frames = 1 minute at the 15 FPS logic rate),
and the default comes from `RulesClass::RepairRate`, documented in vanilla rules
as *"minutes between applying repair step"*. So:

| intent | write |
|---|---|
| every 45 frames (~3 s) | `SelfHealing.Rate=0.05` |
| every ~1 s | `SelfHealing.Rate=0.016` |
| every 45 **minutes** (almost certainly a mistake) | `SelfHealing.Rate=45` |

Also note healing is gated on `SelfHealCombatTimer`, so a unit under fire will
not heal until `CombatDelay` frames have passed.

**Confirmed via.** Antares source read directly (`Ext/Techno/Hooks.cpp:2060-2089`,
`Ext/Techno/Body.cpp:781-814`, `Ext/TechnoType/Body.cpp:452-455`,
`Utilities/TemplateDef.h:645` for the `Promotable` expansion); vanilla globals
from YRpp `RulesClass.h:234-237`; `RepairRate` unit from the stock rules comment.
Addresses/consumers from `registry/hooks.csv`. Not re-derived from `gamemd.exe`
disassembly, and not in-game tested.
