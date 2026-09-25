# Per-instance randomness without touching the shared stream

"Give each unit its own random variant" looks like it needs the game's synced
RNG. It usually doesn't, and reaching for `ScenarioClass::Random` costs two
things that are easy to miss until a match desyncs or a mod plays differently
with a DLL loaded.

Not a hook page — a pattern page for anyone writing per-instance behaviour.

---

## The two costs of pulling from `ScenarioClass::Random`

`ScenarioClass::Instance->Random` is the game's **synced** generator, so drawing
from it is the textbook-correct way to make a decision that must agree across
clients. Both problems are about *how* you draw, not *whether* it is synced.

**1. It only agrees if every client draws in the same ORDER.** A draw made from
a per-object update (`0x6F9E50 TechnoClass_Update`, say) agrees only because all
clients tick the same objects in the same sequence. That holds in lockstep today,
but it is a strong assumption to rest game state on: anything that changes
iteration order — a different object count, an early-out on one client, a second
DLL inserting or removing objects — diverges silently and shows up minutes later.

**2. Every pull SHIFTS the stream for everyone else.** The generator is shared
with vanilla logic. N extra draws per unit means every subsequent vanilla draw
gets a different value, so **the mod plays differently with the DLL loaded than
without it, even when the feature changes nothing.** That makes A/B testing a
DLL against its own absence unsound, and it is invisible in any log.

---

## The pattern: derive, don't draw

Make the decision a **pure function** of data that is already synced and already
per-object:

```cpp
// AbstractClass::UniqueID — from a synced creation counter
// (return ++ScenarioClass::Instance->UniqueID), and SAVED with the object.
const unsigned uid = pThis->UniqueID;

unsigned Draw(unsigned salt, unsigned uid, unsigned step)
{
    // splitmix32. Mixing is not optional: UniqueIDs are ADJACENT INTEGERS by
    // construction, so a plain `uid % n` or a weak hash makes neighbouring
    // units correlate visibly — every second tank picking the same variant.
    unsigned x = salt ^ (uid * 0x9E3779B9u) ^ (step * 0x85EBCA6Bu);
    x ^= x >> 16; x *= 0x7FEB352Du;
    x ^= x >> 15; x *= 0x846CA68Bu;
    x ^= x >> 16;
    return x;
}
```

`salt` is a per-match value every client agrees on (the spawn seed, or the
scenario RNG *state* read once at load — read it, don't draw from it). `step`
separates multiple independent decisions about the same unit.

What this buys:

| | sequential pull | derived from UniqueID |
|---|---|---|
| Agreement rests on | **tick order** | **creation order** |
| Perturbs vanilla randomness | yes | **no** |
| Survives save/load | no — silently re-rolls | **yes**, UniqueID is saved |
| Reproducible for testing | no | **yes** |

The save/load row is worth dwelling on. Per-unit state held only in a DLL-side
map is gone after a reload, so the unit re-draws and visibly changes. Deriving
from a saved field sidesteps the savegame stream entirely for anything you can
recompute — no `Savegame-Stream.md` work needed.

---

## When you still want the synced RNG

If the decision has **no stable per-object key** to derive from — a one-off event,
something about a cell or a house rather than an object — then
`ScenarioClass::Random` remains correct. Accept the stream shift, and make sure
the call site is reached in the same order on every client.

And keep the two generators strictly separate. A **cosmetic** unsynced effect
(an idle animation, a render-only variant) must use a LOCAL generator: drawing
from the synced one for something purely visual shifts the shared stream for
appearance's sake. One generator serving both synced logic and unsynced
rendering is the root cause behind the KratosPP desync.

---

**Confirmed via.** `AbstractClass::UniqueID` declaration and its documented
derivation (YRpp `AbstractClass.h:165`); `ScenarioClass::Random` usage in
`0x6F9E50`-driven per-instance code. Applied in TraitExt, replacing a sequential
`RandomRanged` draw with the derived form. **The sync and save/load properties
are reasoned from the ID's provenance, not yet observed across a save/load or a
multiplayer match** — treat them as sound but unverified. The correlation hazard
of unmixed adjacent IDs is the well-known property of counter-based keys.
