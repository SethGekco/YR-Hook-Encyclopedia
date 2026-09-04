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

**Pattern — the correct home for clearing a DLL-side "identity flag."** If your
DLL keeps a per-object flag in a side table (a `set<TechnoClass*>` marking
"this one was spawned / delivered / built", to drive a chain-guard like
`OnlyBuilt=`/`BuiltOnly=`), **this is where you erase it.** The flag must be:
- **set at creation, before the trigger it guards can fire** (a synchronously-
  created child can otherwise re-trigger before it is marked — see `0x702050` and
  the building-`Place`/`DiscoveredBy` re-entry case), and
- **stable for the object's whole life — never consumed on read.** A guard that
  erases its own mark on each check (or re-marks a *guessed* number of times) leaks
  the moment the guarded event fires once more than predicted, and the object is
  then mistaken for un-marked. Concrete failure seen in the wild: a "delivered"
  structure whose delivery flag was consumed on its first `Grand_Opening` re-ran
  its free-unit list on a later `Place` and the free units *reproduced* despite
  the guard being set. Fix: check without mutating; clear only here, on death.

Erasing a pointer that was never in your table is a harmless no-op, so a single
unconditional `erase(this)` here is safe even though the dtor fires for every
techno.

**Confirmed via.** Upstream Kratos `TechnoExtHook.cpp`; registry cross-reference;
in-game use (erasing per-unit map entries and clearing a delivered-building
chain-guard flag here — standalone Syringe DLLs — with no stale-pointer issues).

**⚠ Stolen size is 0x5 and nothing else — verified failure at 0x6.** The prologue
is:

```
6F4500  51        push ecx
6F4501  53        push ebx
6F4502  56        push esi
6F4503  8B F1     mov  esi,ecx     <- cumulative exactly 5
6F4505  33 DB     xor  ebx,ebx
```

Five bytes lands exactly on an instruction boundary, which is why all four
frameworks declare `0x5`. Declaring `0x6` splits the two-byte `33 DB` and leaves
a dangling `DB` byte in the patched stream. Observed result (2026-08-25, a
standalone Syringe DLL co-loaded with Antares + Phobos): **three reproducible
`C0000005` faults at `0x09C00126`, an address inside no loaded module at all** —
i.e. execution derailed into heap/freed memory rather than crashing inside the
offending DLL. The faulting address therefore points nowhere near the culprit;
the minidump's module list is what rules our own modules out, and the stolen-byte
audit is what finds it. Worth generalising: *a wild-address `C0000005` with a
fault outside every module is a classic signature of a mis-sized stolen-byte
count somewhere, not of bad pointer arithmetic in the hook body.*

**Confirmed via.** Upstream Kratos `TechnoExtHook.cpp`; registry cross-reference;
objdump of vanilla `gamemd.exe` at `0x6F4500`–`0x6F4507` for the boundary above;
in-game use (erasing per-unit map entries here — a standalone Syringe DLL — with
no stale-pointer issues across a session), plus the 0x6 failure described above.

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

---

## VERIFIED — `ObjectClass::IsAlive` is still TRUE inside `InfantryClass::Remove`

Measured, not inferred. A hook at `0x51DF13` (inside `InfantryClass::Remove`,
entry `0x51DF10`) logged **every** infantry removal across two full matches:

* **3172 removals, then 3302 — not one with `IsAlive == false`.**
* **563 of them were already playing `Die1`** (`SequenceAnim == 11`).

So the engine does **not** clear `IsAlive` when an object leaves the map. It is
cleared later, at deletion. Any code that tests `!IsAlive` at `Remove` time to
mean "this one died" will silently never fire — no crash, no log, just a feature
that appears unimplemented.

**Use `Health <= 0` instead**, or accept either signal (`Health <= 0 ||
!IsAlive`) so whichever clears first is enough.

### The wider trap

`Remove` is not a death notification at all. In those same runs it fired for
sequences `0` (Ready), `2` (Prone), `3` (Walk), `5` (Down), `16` (Tread), `28`
(Deployed) and `33`, i.e. ordinary transitions — transports, garrisons,
teleports, grinders and selling all route through it while the unit is alive and
healthy.

Positively identifying a *death* at this site therefore needs **two** facts:
aliveness (via `Health`) **and** a death sequence
(`Die1`–`Die5` = 11–15, `WetDie1`/`WetDie2` = 20/21). Neither alone is enough —
the grinder destroys with no death animation, and a healthy unit can be removed
mid-sequence.

**Confirmed via** IntelExt `src/Ext/Techno/Hooks.Corpse.cpp` logging every
removal with its facts, across two matches. **Unverified:** the exact point at
which `IsAlive` *does* get cleared.
