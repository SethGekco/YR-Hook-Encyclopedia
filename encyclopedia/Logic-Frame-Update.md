# Logic frame update — the per-frame object loop

`LogicClass::AI` (often called LogicClass::Update) walks every object on the map
once per logic frame. It is the natural home for anything that must run **exactly
once per frame** — global solvers, registries, sweeps — as opposed to per-object
work, which belongs in the individual `Update`/`AI` methods.

Addresses here bracket that loop. Picking the wrong one is the usual mistake:
several look interchangeable but differ in *when* relative to the object loop, and
in how contended they are.

---

### `0x55AFB3` — LogicClass::Update (entry)  ⚠ heavily contended

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Ares | LogicClass_Update | 0x6 | src/Misc/SWTypes.cpp |
| Ares | LogicClass_Update_1000 | 0x6 | src/Misc/Invalidators.cpp |
| Antares | LogicClass_Update | 0x6 | src/Misc/SWTypes.cpp |
| Antares | LogicClass_Update_1000 | 0x6 | src/Misc/Invalidators.cpp |
| Kratos | LogicClass_Update | 0x6 | src/Hooks/GeneralHook.cpp |

**What it does.** Fires at the *start* of the logic update, before objects are
iterated. Ares/Antares use it for super-weapon timing and pointer invalidation
sweeps; Kratos for general per-frame work.

**Easily mistaken.** This is the most crowded per-frame address in the exe — three
release frameworks, two of them registering *two* hooks each. They chain fine
(all breakpoint-style, all return 0), but a **fourth** consumer adds cost to the
hottest path in the game, and anything expensive here is paid before any object has
even updated. If your work only needs to happen once per frame and doesn't care
about running before the objects, prefer `0x55B6B3` below — it is nearly empty.

**Confirmed via.** registry (`hooks.csv`: 5 entries across Ares/Antares/Kratos).

---

### `0x55B6B3` — LogicClass::AI, immediately after the object-update loop  ✅ uncontended

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos (PR #352, unmerged) | LogicClass_AI_After | 0x5 | src/Misc/Hooks.AI.cpp |

**What it does.** Sits directly after the loop that updates every object
(`inc esi; cmp esi,[0xA80238]; jl <loop top>` — the exit edge of that loop lands
here), before the tail call at `0x55B6B8`. So every object has already ticked for
this frame when it fires. Ideal for a **global once-per-frame pass** that wants to
observe the post-update world: network/graph solvers, registry rebuilds, sweeps.

**What it does *not* do — easily mistaken.** It is **not** per-object (the loop is
already over — there is no "current object" in a register to `GET`), and it is
**not** the start of the frame. Work published here is naturally read by objects on
the **following** frame; that one-frame lag is deterministic and fine for lockstep,
but do not expect same-frame visibility for objects that already ticked.

**Used by / interactions.** Only Phobos PR #352 (unmerged) — so **no release
framework hooks it**, making it the cheapest safe seat for a standalone DLL's
per-frame pass. A standalone coexisting with base Phobos + Antares + Kratos can
take it without contention today; if #352 ever merges, the two still chain (both
breakpoint-style, size 0x5).

**Determinism note (multiplayer).** Anything computed here must be lockstep-safe:
iterate `TechnoClass::Array` (0xA8EC78) in index order rather than a hash map,
break ties by array index rather than pointer value, and use integer math for
distances. Pointer-ordered iteration is the classic source of a desync that only
shows up after minutes of play.

**Confirmed via.** objdump of `gamemd.exe` (loop exit edge at `0x55B6B1 jl 0x55B698`,
hook site `0x55B6B3 mov ecx,0x87F7E8`, tail call `0x55B6B8`); registry
(single PR consumer); in-DLL use for a per-frame power-network solve (built, not
yet play-tested).

---

### `0x55B719` — LogicClass::Update, late

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Kratos | LogicClass_Update_Late | 0x5 | src/Hooks/GeneralHook.cpp |

**What it does.** A later seat in the same routine, past `0x55B6B3`. Kratos uses it
for work that should trail the frame.

**Easily mistaken.** Being "late" here is *not* the same as being after the object
loop — `0x55B6B3` already satisfies that and is earlier. Choose between them by
what else runs in between, not by the name.

**Confirmed via.** registry (Kratos release).
