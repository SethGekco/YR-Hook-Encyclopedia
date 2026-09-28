# Cross-cutting traps — read this before hooking anything

Every entry here cost a real debugging round, and **most of them cost it more than
once**, because the knowledge lived on a page nobody thought to open. They are
collected here precisely because they are *not* about any single address.

This page is deliberately short. Each item states the trap, the tell, and where
the full write-up lives.

---

## 1. The framework may have replaced the whole function

An Ares-lineage framework or Phobos frequently **replaces** a function outright:
its handler computes a value, writes `EAX`, and `return`s an address past the
vanilla body. Anything you hook *inside* that body is **dead code**, and nothing
warns you — your handler simply never fires.

**Known full replacements in the buildability/production path alone:**

| Address | Function | Owner |
|---|---|---|
| `0x4F7870` | `HouseClass::CanBuild` | Antares / Ares |
| `0x5F7900` | `ObjectTypeClass::FindFactory` | Antares |
| `0x6F47A0` | `TechnoClass::GetBuildTime` | Antares / Ares |
| `0x711EE0` | `TechnoTypeClass::GetBuildSpeed` | Antares / Ares |
| `0x500910` | `HouseClass::GetFactoryCount` | Phobos |
| `0x50B370` | `HouseClass::ShouldDisableCameo` | Antares / Ares |

**The tell:** your feature parses correctly and then does nothing at all.

**The remedy:** hook the framework's own **jump target** (the epilogue) and
post-process there. `0x4F8361` and `0x6F4955` are working examples. But check the
epilogue's geometry first — see trap 3.

⚠ **A replacement also means the framework's readers are the live ones, not
vanilla's.** Counting `test eax,eax` sites in `gamemd.exe` will mislead you if
several of them sit inside a replaced function. Read the framework's source.

Pages: [Buildability-Prerequisites.md](Buildability-Prerequisites.md),
[Production-Queues-Factories.md](Production-Queues-Factories.md).

---

## 2. One function can be gated by a *different* function

Getting a function's return value right is not the same as changing the outcome.
`CanBuild` can correctly answer "no" while the cameo stays clickable, because
whether a cameo is *disabled* is decided by `ShouldDisableCameo` — a separate
function that never calls `CanBuild` at all.

**The tell:** the effect is half-applied. Something greys but still works;
a preview turns red but the action still commits.

**The remedy:** find *every* consumer of the decision, not just the obvious one.
Placement needed two seats for the same reason (preview and commit).

Pages: [Buildability-Prerequisites.md](Buildability-Prerequisites.md).

---

## 3. `return 0` is often a bug

The stub re-runs the **copied original bytes** after your handler. That is only
safe if those bytes are still valid to run. Three shapes break it — a stolen
relative branch, a stolen read of a register you just wrote, and a stolen `ret`
sitting in NOP padding (returning 0 walks into the next function).

⚠ In all three the hook's **geometry is perfect**, so size, boundary and overlap
checkers all pass it. The defect is control flow.

Full write-up: [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

---

## 4. Legal ≠ live (same-address co-hooks)

Syringe installs a second handler at an address without complaint. Whether it
**runs** is a separate question, and this repository holds two contradicting
in-game observations about it — see the ⚠ UNRESOLVED section of
[Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

**The rule that survives either answer:** emit a log line as the handler's
**first statement, before every bail**, and confirm you see it. A handler that
only logs on its success path is indistinguishable from a dead hook.

**The tell:** parsed correctly, then nothing — same tell as trap 1, which is why
you must be able to rule this out cheaply.

---

## 5. Verify the register at *that exact address*

Registers are not stable across a function. Copying `ECX = this` from a
neighbouring entry in the same function is how three separate silent failures
happened in one project. Read the reference implementation's handler **for the
address you are hooking**.

At an *epilogue* reached via a framework's `return`, the incoming registers are
the framework handler's **entry** registers, because YRpp's `REGISTERS` is a
`PUSHFD`/`PUSHAD` frame and the stub restores everything the handler did not
write. That is what makes `ECX` readable at `0x4F8361` and `0x6F4955` — but it
holds *only* while a framework really does replace the entry.

---

## 6. YRpp shapes that silently do nothing

- **`DEFINE_REFERENCE` globals are references, not pointers.** `HouseClass::Array`,
  `BuildingClass::Array`, `MapClass::Instance` — use `.`, not `->`. Three separate
  compile failures in one session; it reads as a pointer everywhere else.
- **`R0`/`RX` virtuals have no address.** Calling one *qualified* silently no-ops;
  it only works through vtable dispatch on an object. `GetFoundationData` is one.
- **`R->ESP()` cannot move the stack.** `POPAD` discards the ESP slot, so the write
  is accepted and thrown away. See shape 3 of
  [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md).

---

## 7. Sentinel values and inverted enums

- **`CanBuildResult`: `-1` is truthy.** `TemporarilyUnbuildable = -1` blocks at
  signed comparisons (`jle`, `<= 0`) and **passes** at `test eax,eax / jne`. It
  greys a cameo; it does not reliably refuse. Three bugs in one project traced to
  this split.
- **`AIDifficulty` is INVERTED: `Hard=0, Normal=1, Easy=2`.** Never do arithmetic
  on it; switch on the names. Any INI key exposing difficulty should take names,
  not numbers, or authors will write `0` meaning Easy and get Hard.
- **Watch for a sentinel the *next* instruction tests for.** If vanilla does
  `cmp eax,0xFFFFFFFF; je` right after, that value is expected — and your handler
  will produce it.

---

## 8. Counters that look interchangeable are not

`OwnedBuildingTypes` (produced/gained, includes under-construction) and
`ActiveBuildingTypes` (physically present) diverge in both directions:

- pre-placed map objects never pass through `RegisterGain`, so `ownedNow` reads 0
  for a house that plainly owns them;
- a building under construction counts in `ownedNow` but not in `present`.

The engine's own prerequisite check reads `ActiveBuildingTypes`. Taking
`max()` of the two to paper over the first problem silently buys the second.

---

## How much to trust a claim on any page

See [_CONVENTIONS.md](_CONVENTIONS.md). In short: look for the status marker.
`VERIFIED` means someone observed it; `⚠ Unverified` / `⚠ DISPUTED` mean they did
not. Nothing here is archived for being wrong without saying so first.
