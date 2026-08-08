# Savegame object stream (save/load boundaries)

The four addresses below bracket the **savegame object stream**: on save the
engine serialises its objects to an `IStream`; on load it reads them back and
runs the pointer **swizzle** pass that fixes every saved pointer to the object's
new address. These are the natural places for an extension to persist its own
per-object data (append after the engine's objects on save; read + swizzle at
the symmetric point on load).

Framework naming diverges here in a way that matters: Antares/Ares name these
generically (`SaveGame` / `LoadGame_End`), while Kratos names the *inner* stream
boundary precisely (`SaveGameInStream_Start/End`, `LoadGameInStream_Start/End`).
The Kratos names describe what the address actually is.

---

### `0x67D300` — SaveGameInStream_Start

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | SaveGame_Start | 0x5 | src/Misc/Savegame.cpp |
| Ares    | SaveGame_Start | 0x5 | src/Misc/Savegame.cpp |
| Kratos  | SaveGameInStream_Start | 0x5 | src/Hooks/SaveGameHook.cpp |

**What it does.** Fires just before the engine writes the object stream. Gives
you the `IStream*` (`ECX`) with the write cursor at the *start* of the object
section — write here and your bytes land ahead of the engine's objects.

**What it does *not* do — easily mistaken.** It is **not** per-object and not the
whole `.sav` file — it's the boundary of the in-stream object section. Writing
here is rarely what you want for pointer-bearing data: on load you'd have to read
your bytes *before* the objects exist, so the swizzle table is empty and pointers
can't be resolved yet. Prefer the `_End` pair for anything referencing objects.

**Used by / interactions.** Antares/Ares/Kratos all hook it (co-loadable →
`conflicts.md`). Antares *continues* Ares, so their overlap is inherited, not a
conflict; Kratos vs Antares is the genuine co-load case.

**Register / calling convention.** `ECX = IStream*`.

**Confirmed via.** Upstream Kratos `SaveGameHook.cpp` (name/register/stolen);
registry cross-reference for Antares/Ares. Load-time swizzle-emptiness is
reasoned from the load ordering, **not** separately disasm-verified.

---

### `0x67E42E` — SaveGameInStream_End

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | SaveGame | 0x5 | src/Misc/Savegame.cpp |
| Ares    | SaveGame | 0x5 | src/Misc/Savegame.cpp |
| Kratos  | SaveGameInStream_End | **0xD** | src/Hooks/SaveGameHook.cpp |

**What it does.** Fires after the engine has finished writing the object stream.
The `IStream*` (`ESI`) cursor is at the end of the object section — **append your
own data here** and it trails the engine's objects. To persist a pointer to a
game object, write the raw pointer value; the load-side swizzle turns it back
into a valid address.

**What it does *not* do — easily mistaken.** It does not give you per-object
context and does not manage swizzling for you — you write raw bytes. If several
DLLs append here, each must read back **exactly** what it wrote, in the **same
hook order**, on load; a magic marker at the head of your block makes a
layout mismatch detectable (and lets old saves stay loadable).

**Used by / interactions.** ⚠️ **Stolen-byte mismatch at one address:**
Antares/Ares declare `0x5`, Kratos declares `0xD`. Two co-loaded hooks that
disagree on how many prologue bytes they replace at the same address is a
coexistence hazard in principle. In practice a `0xD` (Kratos-style) hook here was
**observed to coexist with Ares (`0x5`) in-game with no save corruption** (see
below) — but if you write your own hook here, match the established size and
test your load order rather than assuming.

**Register / calling convention.** `ESI = IStream*`.

**Confirmed via.** Upstream Kratos `SaveGameHook.cpp`; registry cross-reference.
Coexistence + append behaviour confirmed by in-game save→load testing with a
standalone Syringe DLL (GiftBoxHost) that appends per-unit maps here — see
`0x67F7C8`.

---

### `0x67E730` — LoadGameInStream_Start

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | LoadGame_Start | 0x5 | src/Misc/Savegame.cpp |
| Ares    | LoadGame_Start | 0x5 | src/Misc/Savegame.cpp |
| Kratos  | LoadGameInStream_Start | 0x5 | src/Hooks/SaveGameHook.cpp |

**What it does.** Fires before the engine reads the object stream back in.
`ECX = IStream*` positioned at the start of the object section. Kratos also uses
this as the "we are now loading a game" signal (sets an `IsLoadGame` flag) so
that other hooks (e.g. object constructors) can suppress first-time init.

**What it does *not* do — easily mistaken.** The swizzle table is **not** yet
populated here — objects haven't been recreated, so calling `Swizzle` on a saved
pointer at this point cannot resolve it. Use it for the "loading started" signal,
not for reading pointer-bearing extension data.

**Register / calling convention.** `ECX = IStream*`.

**Confirmed via.** Upstream Kratos `SaveGameHook.cpp`; registry cross-reference.

---

### `0x67F7C8` — LoadGameInStream_End

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | LoadGame_End | 0x5 | src/Misc/Savegame.cpp |
| Ares    | LoadGame_End | 0x5 | src/Misc/Savegame.cpp |
| Kratos  | LoadGameInStream_End | 0x5 | src/Hooks/SaveGameHook.cpp |
| Phobos  | LoadGame_ClearShared | 0x5 | src/Phobos.Ext.cpp *(PR#2060, loose)* |

**What it does.** Fires after the engine has finished reading the object stream —
the symmetric partner of `0x67E42E`. Read your appended data here.

**Verified, non-obvious result — late swizzling works.** At this point **all
objects have been recreated and the swizzle table is still valid**, so calling
`SwizzleManagerClass::Instance->Swizzle((void**)&ptr)` on a raw pointer you read
from the stream correctly remaps it to the relocated object. This contradicts
the common assumption that pointer fix-ups must be done *inside each object's own
`Load`* (the per-object container pattern Ares/Phobos/Kratos use). A single
**global read + swizzle at this address** is sufficient for extension data that
only needs to re-key maps by object pointer. Confirmed by in-game save→load
testing: a standalone Syringe DLL persisted `unordered_map<TechnoClass*, …>`
state plus a set of "spawned" units by appending at `0x67E42E` and reading +
swizzling here; after load the pointers resolved, the per-unit state and the
spawned-flag set survived intact (verified behaviourally — guarded units stayed
guarded, no runaway), and no save corruption occurred.

**What it does *not* do — easily mistaken.** Not per-object, and it does not
loop your reads for you. If your marker/layout doesn't match what was written
(older save, or another appending DLL changed the byte layout), **stop** — do not
keep reading, or you'll consume unrelated bytes. A leading magic value handles
this cleanly.

**Used by / interactions.** Antares/Ares/Kratos hook it at release; Phobos has a
loose `PR#2060` hook here (`LoadGame_ClearShared`). Co-loadable → real conflict
surface; ordering matters if more than one consumer appends stream data.

**Register / calling convention.** `ESI = IStream*`.

**Confirmed via.** Upstream Kratos `SaveGameHook.cpp` (name/register/stolen);
registry cross-reference (Antares/Ares/Phobos-PR#2060); YRpp
`SwizzleManagerClass::Instance` (`0xB0C110`, vtable `Swizzle`); and in-game
save→load testing as described.
