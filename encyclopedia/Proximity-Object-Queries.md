# Proximity object queries

"Is something of type X standing within N cells of me?" — the primitive behind
auras, escort bonuses, proximity-gated logic, and anything else that reacts to
what is nearby.

These are **not hooks**. They are the engine globals and helper functions you
call from inside a hook you already own. They are documented here because
picking the wrong shape is the difference between a cheap query and a per-frame
`units x objects` scan — and because the obvious implementation desyncs.

---

### `0xA8EC78` — `TechnoClass::Array`

The global list of every techno (infantry, vehicles, aircraft, buildings) in the
match. In YRpp:

```cpp
DEFINE_REFERENCE(DynamicVectorClass<TechnoClass*>, Array, 0xA8EC78u)
```

**It is a reference, not a pointer** — `TechnoClass::Array.Count` and
`.GetItem(i)`, never `->`. Easy to get wrong, because most YRpp globals of this
shape (`RulesClass::Instance`, `ScenarioClass::Instance`) *are* pointers.

**Entries are not all real.** Filter on `pTechno->IsAlive` and
`!pTechno->InLimbo` before touching one. In-limbo objects include passengers
inside transports and buildings mid-construction; they still carry coordinates,
so a distance check against them silently succeeds and your aura fires from
inside a transport.

**A unit will find itself.** If the watched type can be the same type as the
unit doing the looking, skip `pOther == pThis` or every unit satisfies its own
proximity gate.

---

### `0x5F6440` — `AbstractClass::DistanceFrom(AbstractClass*)`

Returns the 2D distance in **leptons** (`Unsorted::LeptonsPerCell` = 256) as an
`int`. `0x5F6360` is the 3D variant. Both are ordinary `JMP_THIS` calls to real
game addresses — not R0/RX virtual stubs — so a qualified call genuinely runs
(see `Syringe-Stub-Semantics.md` for why that distinction matters elsewhere).

To express a radius in cells, multiply the cell count **up** by
`LeptonsPerCell`. Dividing the measured distance down instead discards the
remainder and makes the radius off by up to one cell.

---

## Determinism: the part that bites

A proximity query feeding **gameplay** (weapons, veterancy, damage, targeting)
must give byte-identical results on every client, or the match desyncs — often
several minutes after the frame that actually diverged.

Per `Logic-Frame-Update.md`:

* Iterate `TechnoClass::Array` **in index order**. Never iterate a
  `std::unordered_map` / `unordered_set` of objects to decide game state:
  iteration order follows pointer values, which differ per client.
* Break ties by **array index**, not pointer value.
* Keep distances in **integer** leptons; do not convert to floating-point cells
  and compare.

A purely **cosmetic** proximity effect is exempt, and should use an unsynced
local decision path so it never perturbs the synced stream. See
`Multiplayer-Sync-CRC-Logging.md`.

---

## Cost: index once per frame, don't scan per unit

The naive shape puts a full `TechnoClass::Array` walk inside each unit's own
update. That is `units x objects` of work per evaluation — in a late-game match
with a few hundred of each, it is likely the most expensive thing your DLL does.

The cheap shape is a **snapshot rebuilt at most once per frame**, keyed on
`Unsorted::CurrentFrame`, holding only objects whose types some rule actually
watches for. Each unit then scans a handful of candidates instead of the world:

```cpp
static void RebuildNearIndex()
{
    const int now = Unsorted::CurrentFrame;
    if (now == g_NearIndexFrame)
        return;                      // already current this frame
    g_NearIndexFrame = now;

    for (auto& kv : g_NearIndex)
        kv.second.clear();

    // INDEX ORDER - see the determinism note above.
    for (int i = 0; i < TechnoClass::Array.Count; ++i)
    {
        TechnoClass* const pOther = TechnoClass::Array.GetItem(i);
        if (!pOther || !pOther->IsAlive || pOther->InLimbo)
            continue;

        TechnoTypeClass* const pType = pOther->GetTechnoType();
        if (!pType || !g_Watched.count(pType->ID))
            continue;

        g_NearIndex[pType->ID].push_back(pOther);
    }
}
```

`g_NearIndex` being a hash map looks like it contradicts the determinism rule.
It does not: it is only ever **looked up by key**, never iterated to decide game
state, and the vectors inside it are filled in array index order — so the
candidate order each unit sees is identical on every client.

**You do not need a hook for this.** Call the rebuild lazily from whatever
per-object tick you already own (`0x6F9E50 TechnoClass_Update`, see
`Techno-Instance-Lifecycle.md`); the frame guard makes the first caller of each
frame pay for it and every later caller free. Taking `0x55B6B3` for a dedicated
per-frame pass is only worth it when you specifically need the *post-update*
world.

**Stale-by-one-tick is normal.** Whichever unit ticks first rebuilds the index,
so units later in the same frame read positions from before the earlier units
moved. That lag is identical on every client and therefore lockstep-safe — but
do not build anything that assumes same-frame freshness.

---

**Confirmed via.** YRpp declarations (`TechnoClass.h`, `AbstractClass.h`,
`Fundamentals.h`) for the addresses and the reference-vs-pointer form; Phobos
`Commands/ObjectInfo.cpp:64` divides `DistanceFrom` by `Unsorted::LeptonsPerCell`
to show a cell distance, which fixes the unit; Phobos
`Ext/Script/Mission.Move.cpp` for the `.Count` / `.GetItem(i)` iteration form.
Determinism rules carried over from `Logic-Frame-Update.md`.

Written up while adding proximity-gated traits to TraitExt. **The in-game
behaviour of that feature is not yet verified**, so treat the cost, staleness and
in-limbo claims as reasoned rather than measured; the address, unit and
container-form claims are source-confirmed.
