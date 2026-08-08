# TechnoClass per-instance lifecycle (create / tick / destroy / death)

Per-*instance* hooks on `TechnoClass` — they fire once per live object, not once
per type. This is the backbone every extension uses to attach and drive
per-unit state. All three of the frameworks below plus Antares/Ares patch these,
so they're squarely in `registry/conflicts.md`; the point of this page is which
one to reach for and the scope traps in each.

---

### `0x6F4500` — TechnoClass_DTOR

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | TechnoClass_DTOR | 0x5 | src/Ext/Techno/Body.cpp |
| Ares    | TechnoClass_DTOR | 0x5 | src/Ext/Techno/Body.cpp |
| Kratos  | TechnoClass_DTOR | 0x5 | src/Hooks/TechnoExtHook.cpp |
| Phobos  | TechnoClass_DTOR | 0x5 | src/Ext/Techno/Body.cpp |

**What it does.** Fires from the `TechnoClass` destructor — the object is going
away. The canonical place to drop any per-instance state you key by
`TechnoClass*`, so a later reused pointer can't alias stale data.

**What it does *not* do — easily mistaken.** It is **not** a "unit died" event.
The destructor runs for *every* way an object leaves the game — sold, undeployed,
transformed, captured-then-freed, map cleanup — not just combat death, and it is
already too late to read the object's position or spawn anything "where it died"
(use `0x702050` for that). Treat it purely as cleanup.

**Register / calling convention.** `ECX = TechnoClass*` (Kratos). The `this`
register is shared by the other consumers.

**Confirmed via.** Upstream Kratos `TechnoExtHook.cpp`; registry cross-reference;
in-game use (erasing per-unit map entries here — a standalone Syringe DLL — with
no stale-pointer issues across a session).

---

### `0x6F9E50` — TechnoClass_Update (Phobos: TechnoClass_AI)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | TechnoClass_Update | 0x5 | src/Ext/Techno/Hooks.cpp |
| Ares    | TechnoClass_Update | 0x5 | src/Ext/Techno/Hooks.cpp |
| Kratos  | TechnoClass_Update | 0x5 | src/Hooks/TechnoExtHook.cpp |
| Phobos  | TechnoClass_AI | 0x5 | src/Ext/Techno/Hooks.cpp |

**What it does.** The per-instance game-logic tick — runs once per techno per
logical frame. This is where per-unit timers, periodic abilities, and AI-adjacent
custom behaviour live. (Phobos calls it `TechnoClass_AI`; same address, same
call.)

**What it does *not* do — easily mistaken.** It is **per-instance, not
per-type** — do not cache one-shot per-type work keyed off it without a guard, it
will re-run for every unit of that type every frame. It is the **logic** tick,
not a render tick, so it is frame-synchronous and safe for synced game state
(spawns, RNG via `ScenarioClass::Instance->Random`) — do **not** put presentation
randomness here and elsewhere off a shared generator (that desyncs; see the
Kratos shared-RNG note). It also does not fire for objects in limbo.

**Verified behaviours (useful when writing your own hook here):**
- **Spawning new technos from inside this tick is safe** — `pType->CreateObject`
  → `++Unsorted::IKnowWhatImDoing; Unlimbo(...); --…; SetLocation(...)` works when
  called from the updating unit's own tick.
- **Killing the updating unit from inside its own tick is safe *via the damage
  path*** — `pThis->TakeDamage(pThis->Health + 1, crewed)` defers the actual
  removal through the engine's normal death handling. (Directly `Limbo()` +
  `UnInit()` on `this` mid-tick is the riskier route the state-machine
  frameworks guard with a "break the component loop" flag.)

**Register / calling convention.** `ECX = TechnoClass*` (Kratos).

**Confirmed via.** Upstream Kratos/Phobos hooks; registry cross-reference;
in-game testing of per-unit timer spawns and self-destruct-via-TakeDamage from a
standalone Syringe DLL (no crash; correct behaviour).

---

### `0x702050` — TechnoClass::ReceiveDamage (destroyed-by-damage site)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | TechnoClass_ReceiveDamage_SuppressUnitLost | 0x6 | src/Ext/WarheadType/Hooks.Damage.cpp |
| Kratos  | TechnoClass_ReceiveDamage_Destroy | 0x6 | src/Hooks/TechnoExtHook.cpp |
| Phobos  | TechnoClass_ReceiveDamage_AttachEffectExpireWeapon | 0x6 | src/Ext/Techno/Hooks.ReceiveDamage.cpp |

**What it does.** A point inside `TechnoClass::ReceiveDamage` reached when the
damage result is destruction. `ESI = TechnoClass*` — the unit is **still present**
(its coordinates and owner are valid) but is about to be removed. This is the
clean "died from damage" trigger: read `GetCoords()` / `Owner`, then act (spawn
replacements, release cargo, fire an expire-weapon, suppress the "unit lost" EVA).

**What it does *not* do — easily mistaken.** It is **"destroyed by damage," not
"removed."** Selling, undeploying, transforming, `UnInit` from script, or a unit
walking into a transport do **not** pass through here — for universal teardown use
the destructor (`0x6F4500`), which conversely is too late to read position. Also
note this is one shared call site used for **three unrelated purposes** across
frameworks (EVA suppression / AttachEffect expire-weapon / on-death release), so
it is a genuine multi-consumer address rather than "the on-death hook."

**Used by / interactions.** In `registry/conflicts.md` (Antares + Kratos + Phobos
— all co-loadable, all `0x6` stolen). Because each does something different and
all just read `this` then return 0, they chain without fighting. **Verified:** an
`0x702050` hook that reads the dying unit and spawns replacements ran correctly
alongside an Ares-lineage DLL + Phobos in-game (on-death spawns fired reliably,
no conflict). The framework loaded at test time was Ares; **Antares** patches the
same address (registry), so the chaining should transfer — not yet re-verified
under Antares.

**Register / calling convention.** `ESI = TechnoClass*`; return `0` to continue.

**Confirmed via.** Upstream Kratos `TechnoExtHook.cpp` (name/register/stolen);
registry cross-reference (Antares/Phobos purposes); in-game on-death spawn
testing from a standalone Syringe DLL coexisting with Ares + Phobos.
