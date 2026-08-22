# Buildability & Prerequisites

`HouseClass::CanBuild` and the prerequisite helpers behind it — the gate that
decides whether a cameo is shown, greyed out, or hidden.

This subsystem is a **hidden-conflict hotspot**: the Ares-lineage frameworks and
Phobos hook *the same function at different addresses*, so `registry/conflicts.md`
(which matches on exact address equality) reports **no collision here at all**.
The interaction is nonetheless load-order- and framework-presence-dependent, and
one framework runtime-patches another's hook site out of existence. Read the whole
page before hooking anything in this cluster.

**Return type** — `CanBuildResult` (YRpp `GeneralDefinitions.h:805`):

| Value | Meaning |
|---|---|
| `TemporarilyUnbuildable = -1` | grey/black out the cameo (condition may change) |
| `Unbuildable = 0` | remove the cameo (permanent) |
| `Buildable = 1` | can build |

---

### `0x4F7870` — HouseClass::CanBuild

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `HouseClass_CanBuild` | 0x7 | `src/Ext/House/Hooks.cpp` |
| Ares | `HouseClass_CanBuild` | 0x7 | `src/Ext/House/Hooks.cpp` |

**What it does.** Entry point of
`int __thiscall CanBuild(TechnoTypeClass* item, bool buildLimitOnly, bool includeQueued)`.

**⚠ This is a FULL REPLACEMENT, not an extension.** Antares' handler computes
`HouseExt::PrereqValidate(...)`, writes the verdict into `EAX`, and
`return 0x4F8361` — i.e. it jumps to the function's epilogue and **the entire
vanilla body never executes**. Ares does the same.

**What it does *not* do — easily mistaken.**
- It does **not** leave the vanilla prerequisite logic in place. Anything you
  install *inside* the vanilla body (between `0x4F7870` and `0x4F8361`) is **dead
  code** whenever Antares or Ares is loaded. This is the trap.
- Do **not** add a second hook at `0x4F7870` expecting to extend the verdict.
  Antares' handler returns a jump target, so a chained hook either never runs or
  fights over `EAX`. **Use `0x4F8361` instead** (below).

**Register / calling convention** (Antares `src/Ext/House/Hooks.cpp:26`):
```
ECX       = HouseClass const*      pThis
[ESP+0x4] = TechnoTypeClass const* pItem
[ESP+0x8] = bool                   buildLimitOnly
[ESP+0xC] = bool                   includeInProduction
→ writes EAX = CanBuildResult, returns 0x4F8361
```

**Confirmed via.** Antares source (`~/Claude/Antares-src`, master); registry
`hooks.csv` (Antares + Ares, stolen 0x7); PDB symbol map name
`0x4F7870 HouseClass_CanBuild`. Vanilla body **not** independently disassembled.

---

### `0x4F7877` — HouseClass::CanBuild (inside vanilla body) — *self-disabling probe*

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `HouseClass_CanBuild_UpgradesInteraction_WithoutAres` | 0x5 | `src/Ext/BuildingType/Hooks.Upgrade.cpp` |

**What it does.** Sits 7 bytes into the function — i.e. *inside the vanilla body*,
which only executes when **no** Ares-lineage DLL replaced the function. Phobos uses
reachability here as a **runtime feature-detect for "Ares/Antares is absent"**. The
handler does no buildability work at all; it logs
`Hook [HouseClass_CanBuild_UpgradesInteraction] disabled` and then raw-patches
**both** sites back to original bytes:

```cpp
Patch::Apply_RAW(0x4F8361, { 0xC2, 0x0C, 0x00, 0x6E, 0x7D }); // kill the epilogue hook
Patch::Apply_RAW(0x4F7877, { 0x53, 0x55, 0x8B, 0xE9, 0x56 }); // kill itself (one-shot)
```

**What it does *not* do — easily mistaken.** It is **not** a "without-Ares
implementation" of the upgrade/BuildLimit feature despite the name — it
*disables* the feature. Phobos' BuildLimit-group logic simply does not run when
Ares/Antares is absent.

**⚠ Collateral damage for third-party DLLs.** That first `Apply_RAW` overwrites
**five raw bytes at `0x4F8361`**, clobbering whatever is installed there —
including hooks belonging to *other* DLLs. So:

> If Phobos is loaded **without** Ares/Antares, any third-party hook at `0x4F8361`
> is silently destroyed the first time `CanBuild` runs.

Practical rule: **a DLL hooking `0x4F8361` should declare Ares or Antares a hard
requirement**, or detect their absence itself. Failure mode is nasty — it works in
testing (Antares loaded) and silently no-ops for a user running Phobos alone.
*(Byte-clobber reasoning is from reading the patch call; not yet confirmed by
runtime experiment.)*

**Confirmed via.** Phobos source (`Phobos/src/Ext/BuildingType/Hooks.Upgrade.cpp:119-133`,
develop). Registry `hooks.csv`. The restored byte values are quoted from that
source, not independently disassembled.

---

### `0x4F8361` — HouseClass::CanBuild epilogue — **the safe integration point**

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `HouseClass_CanBuild_UpgradesInteraction` | 0x5 (registry says 0x3 — see below) | `src/Ext/BuildingType/Hooks.Upgrade.cpp` |

**What it does.** The function's `ret 0xC` epilogue, reached **both** by the
vanilla fall-through *and* by Antares'/Ares' `return 0x4F8361`. On arrival `EAX`
already holds the final verdict — Phobos names the variable literally
`resultOfAres`. Phobos reads it and, when it is `Buildable`, layers its
BuildLimit-group / upgrade checks on top via `R->EAX(...)`, then returns `0`.

**Why this is the right place to extend buildability.** It is
framework-agnostic (works whether or not the body was replaced), the verdict is
already computed so you can treat it as a fallback and only override
deliberately, and the handler returning `0` means multiple DLLs chain here
cleanly.

**Register / calling convention** (Phobos `Hooks.Upgrade.cpp:95-101` — identical
layout to `0x4F7870`, since it is the same frame):
```
ECX       = HouseClass const*      pThis
[ESP+0x4] = TechnoTypeClass const* pItem
[ESP+0x8] = bool                   buildLimitOnly
[ESP+0xC] = bool                   includeInProduction
EAX       = CanBuildResult         incoming verdict (read it; write back via R->EAX)
```

**What it does *not* do — easily mistaken.**
- `EAX` here is **not** "the vanilla verdict" — with Antares/Ares loaded it is
  *their* verdict, already including their extended prerequisite model. Treat it
  as the composed upstream answer, not a clean slate.
- Respect the `-1` vs `0` distinction when overriding: collapsing
  `TemporarilyUnbuildable` into `Unbuildable` permanently removes cameos that
  should merely grey out.
- `buildLimitOnly == true` calls ask a *different* question (limit check only);
  handlers that assume every call is a full prerequisite query will misbehave.

**⚠ Stolen-byte discrepancy.** `registry/hooks.csv` records **0x3** for Phobos at
this address, but the Phobos develop source reads
`DEFINE_HOOK(0x4F8361, HouseClass_CanBuild_UpgradesInteraction, 0x5)`, and the
matching `Apply_RAW` restores **5** bytes (`C2 0C 00 6E 7D` = `ret 0xC` plus two
following bytes). Either the registry harvest is stale/mis-parsed or it captured a
different Phobos revision. **Treat 0x5 as current**; the registry row should be
re-checked. *(Compare the similar noted mismatch at `0x67E42E` in
[Savegame-Stream.md](Savegame-Stream.md).)*

**Used by / interactions.** Absent from `registry/conflicts.md` because Antares/
Ares hook `0x4F7870` while Phobos hooks `0x4F7877`/`0x4F8361` — different
addresses, same function. The dependency is real regardless: Phobos' logic here
is *designed* to run downstream of an Ares-lineage verdict, and self-disables when
that verdict is absent (see `0x4F7877`).

**Confirmed via.** Phobos source (develop) and Antares source (master), read
directly; YRpp `GeneralDefinitions.h` for `CanBuildResult`; PDB symbol map for
`0x4F7870`. **Unverified:** in-game behaviour with both frameworks plus a third
DLL hooking `0x4F8361` simultaneously; the exact vanilla instruction stream.

---

### `0x505360` — HouseClass::PrerequisitesForTechnoTypeAreListed

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `HouseClass_PrerequisitesForTechnoTypeAreListed` | 0x5 | `src/Ext/House/Hooks.cpp` |
| Ares | `HouseClass_PrerequisitesForTechnoTypeAreListed` | 0x5 | `src/Ext/House/Hooks.cpp` |

**What it does.** Answers "would *this given list* of building types satisfy the
item's prerequisites?" — a hypothetical/planning query over a supplied list,
**not** a query about what the house currently owns. Antares **replaces** it
(`return 0x505486`), delegating to `HouseExt::PrerequisitesListed`, which tests
each of the item's `PrerequisiteLists` alt-groups with `Prereqs::ListContainsAll`.

**What it does *not* do — easily mistaken.** It does not gate live buildability —
that is `CanBuild`. Hooking this expecting to change what a player can build will
appear to do nothing in normal play.

**Register / calling convention** (Antares `src/Ext/House/Hooks.cpp:45`):
```
ECX       = HouseClass*                             pThis   (unused by Antares)
[ESP+0x4] = TechnoTypeClass*                        pItem
[ESP+0x8] = DynamicVectorClass<BuildingTypeClass*>* pBuildingsToCheck
[ESP+0xC] = int                                     listCount
→ writes EAX = bool, returns 0x505486
```

**Confirmed via.** Antares source (master); registry `hooks.csv`; PDB symbol map.

---

## ⚠ `CanBuildResult::TemporarilyUnbuildable` is −1, and −1 is truthy

```
enum class CanBuildResult : int {
    TemporarilyUnbuildable = -1,   // "black out cameo"
    Unbuildable            =  0,   // "permanently; remove cameo"
    Buildable              =  1,
};
```

The YRpp comment invites you to read `-1` as "greyed out and therefore not
buildable". **It is not.** Of the eleven `call 0x4F7870` sites in `gamemd.exe`,
**eight** test the result with `test eax,eax` and treat any non-zero value as
permission to build; only **three** do `cmp eax,-1`, and those are the
cameo-blackout paths.

So a hook that refuses a build by writing `-1` produces exactly this symptom:
the sidebar cameo goes dark, and the unit builds anyway when clicked. It looks
like the refusal "half worked", which sends people hunting for a second gate
that does not exist.

Write **`Unbuildable` (0)** to actually refuse — it is falsy, so every caller
agrees, and removing the cameo is what vanilla itself does for
`RequiresStolenAlliedTech` / `…SovietTech` / `…ThirdTech`. Reserve `-1` for
conditions the *engine* already treats that way (insufficient power, factory
busy), where the surrounding code knows to re-check.

**Confirmed via.** YRpp `GeneralDefinitions.h` for the values; objdump sweep of
all `call 0x4F7870` sites for the test-vs-compare split; observed in game
(cameo blacked out, unit still produced) before switching to `0`.

### …and the value is only half of it: `CanBuild` is asked **twice**

`CanBuild(pItem, buildLimitOnly, includeInProduction)` is consulted with two
different intents:

* `buildLimitOnly = false` — the **sidebar** asking what to draw.
* `buildLimitOnly = true` — the path that **actually starts production**.

A hook that early-outs on `buildLimitOnly` (a natural-looking guard, since that
query nominally asks about build limits) therefore changes the *picture* and
never touches the *gate*: the cameo greys or vanishes and the item still builds
when clicked or queued.

This is exactly why a reached `BuildLimit` genuinely prevents production —
Antares' `HouseExt::PrereqValidate` answers **both** calls, returning its
`BuildLimitStatus` on the `buildLimitOnly` path
(`src/Ext/House/Body.cpp`, `PrereqValidate` / `CheckBuildLimit`). Any
third-party refusal that wants to be real has to do the same.

**Confirmed via.** Antares source (`develop`); observed in game — refusing only
the `buildLimitOnly = false` call produced a darkened-but-buildable cameo, and
answering both produced a real refusal.

---

## Related engine facts (not hooks)

Useful when writing anything in this subsystem; all from YRpp headers, verified by
reading `HouseClass.h` / `HouseTypeClass.h`:

- **One-way vs mutual alliance.** `HouseClass::IsAlliedWith(pHouse)` tests
  `this->Allies.Contains(them)` — **one-way**. `HouseClass::IsMutualAlly(pHouse)`
  (`HouseClass.h:256`) tests both directions. A house you allied with that hasn't
  accepted is `IsAlliedWith` but **not** `IsMutualAlly`.
- **Owned vs present counts.** `CountOwnedNow(BuildingTypeClass*)` reads
  `OwnedBuildingTypes`; `CountOwnedAndPresent()` reads `ActiveBuildingTypes`
  (`HouseClass.h:545` / `:564`). The two differ for limboed/undeployed instances.
- **Stolen tech is only 3 flags in vanilla.** `HasAllStolenTech`
  (`HouseClass.h:609`) checks `Side0TechInfiltrated` / `Side1` / `Side2` — there is
  **no indexed stolen-tech in vanilla**. Antares adds `std::bitset<32> StolenTech`
  in its own House ext (`Ext/House/Body.h:106`), which is private to Antares and
  not readable from a third-party DLL.
- **House matching for `RequiredHouses=`/`ForbiddenHouses=`** uses
  `1u << Type->ArrayIndex2` (`HouseClass::InRequiredHouses`, `HouseClass.h:637`);
  resolve a country name with `HouseTypeClass::FindIndexOfName`.
