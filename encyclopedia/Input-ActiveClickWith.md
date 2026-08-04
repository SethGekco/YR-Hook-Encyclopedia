# Input — active-click command dispatch

`DisplayClass::ActiveClickWith` (the routine that turns a left-click-with-units
into orders — move / attack / waypoint / etc.) and the building-planning guard
inside it. A cluster of frameworks want to *reimplement* the whole function,
which makes it one of the more compatibility-hostile spots in the exe.

---

### `0x4AE7B3` — DisplayClass::ActiveClickWith (order dispatch)  ⚠ multi-consumer, full-reimplementation

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos (PR #352, unmerged) | DisplayClass_ActiveClickWith_Iterate | 0x0 | src/Ext/Techno/Hooks.TechnoAttachment.cpp |
| Phobos (PR #1993, unmerged) | DisplayClass_ActiveClickWith_Iterate | 0x0 | src/Commands/DistributionMode.cpp |

**What it does.** The hook (size 0x0) sits near the top of `ActiveClickWith` and
**takes over the entire function**, iterating the selected objects and re-issuing
the click as orders itself, then returning past the tail (`0x4AE99B`) so the
original body never runs. PR #352 uses it to also forward the order to attachment
children (`InheritCommands`); PR #1993 (Distribution Mode) reimplements it to
distribute orders differently.

**What it does *not* do — easily mistaken.** It is **not** a small breakpoint you
can chain — it is a **full-function replacement**. Two consequences people miss:
1. **Two reimplementations are mutually exclusive.** PR #352 and PR #1993 both
   replace the whole function at the same address; they cannot both take effect.
2. **It bypasses every hook *inside* the function** — notably `0x4AE95E` below,
   which is a *release* hook in both Phobos and Kratos. A replacement that jumps
   to `0x4AE99B` silently skips it, breaking that shipped behaviour.

**Used by / interactions.** Both consumers are unmerged PRs, so base Phobos
release does not hook `0x4AE7B3` today. But a **standalone DLL coexisting with
base Phobos + Kratos must NOT full-replace this function** — doing so clobbers
the release `0x4AE95E` hook (see below). In-tree (inside Phobos) a reimplementation
can fold that logic back in; a coexisting DLL cannot. This is a case where the
in-Phobos PR approach does not translate to a standalone.

**Confirmed via.** registry (`hooks.csv`: two PR consumers at this address);
objdump of `gamemd.exe` (function tail at `0x4AE99B`); reasoning about
Syringe full-function-replacement semantics.

---

### `0x4AE95E` — DisplayClass sub_4AE750, building non-attack-planning guard  ⚠ release, inside ActiveClickWith

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | DisplayClass_sub_4AE750_DisallowBuildingNonAttackPlanning | 0x5 | src/Ext/Building/Hooks.cpp |
| Kratos | DisplayClass_sub_4AE750_DisallowBuildingNonAttackPlanning | 0x5 | src/Hooks/BuildingExtHook.cpp |

**What it does.** A small breakpoint **inside** `ActiveClickWith` that disallows
non-attack planning clicks for buildings.

**What it does *not* do — easily mistaken.** It is **released** (in shipped
Phobos *and* Kratos), not a PR — so it is live in the field. Because it lives
inside `ActiveClickWith`, it is **silently defeated by any full-function
replacement at `0x4AE7B3`** — the reason `0x4AE7B3` reimplementations are
coexistence-hostile.

**Used by / interactions.** Phobos + Kratos, same call site, both release. Safe
together (both chain the same breakpoint). Endangered only by an `0x4AE7B3`
takeover.

**Confirmed via.** registry (`hooks.csv`: Phobos release + Kratos release);
objdump of `gamemd.exe`.
