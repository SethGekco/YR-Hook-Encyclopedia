# Attachment / cell-placement & occupation

Hooks around unit placement marking, cell occupation, and the "custom
locomotor rides another object" pattern (Phobos PR #352 "Techno Attachment").
These are notable because a **do-nothing / parent-relative locomotor** interacts
badly with the vanilla placement code, and because the fixes cluster on
addresses the registry does not fully index (PR-side `DEFINE_JUMP`s are not
captured by the PR-hook extractor — see notes below).

---

### `0x4D37A2` — FootClass::Mark (locomotion layer check)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos (PR #352, unmerged) | *(skip)* `DEFINE_JUMP(LJMP, 0x4D37A2, 0x4D37AE)` | — | src/Ext/Cell/… |

Not in the auto-registry: the PR uses a static `DEFINE_JUMP`, which the PR-hook
extractor does not record. No release framework (Antares/Ares/Phobos) hooks
this address → collision-free.

**What it does.** Inside `FootClass::Mark` (placement / occupation marking),
vanilla runs `mov eax,[esi]; mov ecx,esi; call [eax+0x78]; cmp eax,2` — i.e. it
queries the object's **locomotion layer** (virtual at vtable offset `0x78`,
`In_Which_Layer`) and branches on whether it equals a specific layer value (2).
The result steers how the unit marks its cell.

**What it does *not* do — easily mistaken.** It looks like a harmless passive
layer query. It is not, for an object whose `In_Which_Layer` resolves through
*another* object. A custom locomotor that reports its **parent's** layer (e.g.
PR #352's attachment locomotor, where a child rides a host) makes this call
re-enter placement/foundation code; combined with the `BuildingClass`
foundation-cell traversal (`0x434B90` → `0x4373B0`, see below) it recurses
without terminating → a **single-frame hang** when an active such child sits on
a building's foundation. Also easily mistaken: you **cannot** intercept this with
a small `DEFINE_HOOK` — the instructions here are 2-3 bytes (`8b 06`, `8b ce`,
`ff 50 78`), smaller than Syringe's 5-byte patch, so a `size<5` hook clobbers the
following `call [eax+0x78]` and crashes (observed: `C0000005 at 0x4D37AB`,
reading a bogus address, during unit generation). Use a `DEFINE_JUMP`.

**Used by / interactions.** Only PR #352, as an unconditional skip to
`0x4D37AE` (the layer-check's fall-through). Twin of `0x568831` below. Skipping
it for all units is the PR's chosen tradeoff; a conditional skip is impractical
here for the size reason above.

**Register / calling convention.** `ESI = this` (FootClass). `EAX` loaded with
`[ESI]` (vtable) immediately before the check. Skip target `0x4D37AE` reloads
`EDX=[ESI]`, so bypassing the two-byte load + the check is register-safe.

**Confirmed via.** objdump of vanilla `gamemd.exe` (YR 1.001) for the
instructions and skip target; PR #352 source; registry cross-check (absent);
in-game testing with a private attachment DLL — a watchdog caught the recursion
whose driver is this `call [vtable+0x78]`, the `DEFINE_JUMP` skip resolved the
hang, and the `size<5` `DEFINE_HOOK` attempt produced the crash above.

---

### `0x568831` — MapClass::PickUp (locomotion layer check)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos (PR #352, unmerged) | *(skip)* `DEFINE_JUMP(LJMP, 0x568831, 0x568841)` | — | src/Ext/Cell/… |

Not in the auto-registry (same `DEFINE_JUMP` reason). Collision-free.

**What it does.** Same `call [eax+0x78]; cmp eax,2` locomotion-layer check as
`0x4D37A2`, but in `MapClass::PickUp` (removing an object from the map/cell).

**What it does *not* do — easily mistaken.** Same trap: a parent-relative custom
locomotor turns this into a recursion entry point. Both the Mark and PickUp
copies must be skipped; fixing only one leaves the hang reachable via the other.

**Register / calling convention.** `EDI = this` here (not ESI). `EAX=[EDI]`
before the check. Skip target `0x568841` reloads `EDX=[EDI]`.

**Confirmed via.** objdump of vanilla `gamemd.exe`; PR #352 source; in-game
testing (this address appeared in the same freeze's call stack alongside
`0x4D37A2`).

---

### `0x4373B0` — BuildingClass foundation-cell visitor traversal (**do not hook**)

**What it does.** A generic foundation/cell **visitor traversal** (a throwaway
visitor object, vtable `0x7E2070`, is built on the stack at `0x437313`/`0x43724B`;
`F=0x437380` and `0x4373B0` mutually recurse through it). Reached from placement
via `0x434B90`. It is where the layer-check recursion above actually spins.

**What it does *not* do — easily mistaken.** It is **not** a logic-only routine.
It is on the **render path** — hooking `0x4373B0` directly (even a benign
counting probe) corrupts voxel rendering and the mouse cursor for *all* units.
Do not intercept it to "cut" the recursion; fix the cause upstream at the
locomotion-layer checks (`0x4D37A2`/`0x568831`) instead.

**Confirmed via.** objdump of vanilla `gamemd.exe` (visitor vtable + recursion
structure); in-game testing (a probe hook here broke rendering).

---

### `0x6F3283` — TechnoClass::CanScatter  ⚠ shared address (conflict-prone)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | TechnoClass_CanScatter_KillDriver | 0x8 | src/Ext/Techno/Hooks.cpp |
| Ares    | TechnoClass_CanScatter_KillDriver | 0x8 | src/Ext/Techno/Hooks.cpp |
| Phobos (PR #352, unmerged) | TechnoClass_CanScatter_CheckIfAttached | 0x8 | src/Ext/Techno/Hooks.TechnoAttachment.cpp |

**What it does.** Intercepts `TechnoClass::CanScatter`. Antares/Ares use it for
KillDriver (a scattered mind-controlled/driver unit); PR #352 returns false for
an attached child (its do-nothing locomotor can't scatter, so nothing keeps
asking it to vacate a wanted cell).

**What it does *not* do — easily mistaken.** Returning false here does **not** by
itself fix the building-host attachment freeze — that hang is the
locomotion-layer recursion above, a different subsystem. CanScatter only governs
the scatter request path.

**Used by / interactions.** Address hooked by **Antares, Ares, and PR #352**
(all `size 0x8`, all `Ext/Techno`). All three are `DEFINE_HOOK` breakpoints, so
they chain; correctness depends on each returning "continue" for cases it
doesn't own. A consumer adding a fourth hook here (e.g. an attachment DLL run
alongside Antares) chains onto Antares'/Ares' KillDriver hook — verified working
in-game alongside **Ares**; re-verify under **Antares** (parity expected).
Top-priority conflict entry — three frameworks on one address.

**Register / calling convention.** `ECX`/`ESI = this` at `0x6F3283`
(`push esi; mov esi,ecx` precedes it, so both hold `this`); `size 0x8`. Return
`0x6F32C5` to force "cannot scatter".

**Confirmed via.** registry (`hooks.csv`: Antares+Ares+Phobos rows); objdump of
`gamemd.exe`; in-game testing alongside Ares.
