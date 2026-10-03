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

### `0x4F657A` — `Owner=` is resolved through `ParentCountry`, not the country

**Framework names** — *no framework hooks this address.* Not in the registry.

**What it does.** Inside `HouseClass::CanExpectToBuild`. Builds the country bit
used to test a TechnoType's `Owner=` — and it does **not** use the house's own
country index:

```asm
4f657a:  mov 0x34(%esi),%ecx      ; HouseClass->Type  (HouseTypeClass*)
4f6588:  add $0x98,%ecx           ; &HouseTypeClass->ParentCountry   (+0x98)
4f658e:  call 0x5117d0            ; HouseTypeClass::FindIndexOfName(ParentCountry)
4f6593:  mov $0x1,%edx
4f6598:  mov %eax,%ecx
4f659d:  shl %cl,%edx             ; EDX = 1 << idxParentCountry
...
4f65ad:  test %edx,0x6cc(%ebx)    ; against [TechnoType+0x6CC] = Owner
```

**The two country-list verbs are indexed differently:**

| Tag | Indexed by |
|---|---|
| `Owner=` | the **parent** country — `FindIndexOfName(ParentCountry)` |
| `RequiredHouses=` / `ForbiddenHouses=` | the country **itself** — `ArrayIndex2` (`+0xB8`) |

This confirms YRpp's `HouseClass::InOwners` / `InRequiredHouses` helpers
(`HouseClass.h:632-643`) are *literal* models of engine behaviour, not
conveniences.

**What it does *not* do — easily mistaken.** `ArrayIndex2` is **not** a
precomputed parent index (a tempting reading of YRpp's `//dunno why`). It is the
country's **own** position: written from `ArrayIndex` in the constructor
(`0x511410`) and recomputed by a self-search at `0x511608`. Only two writes to
`+0xB8` exist in `0x511000`–`0x513000`, both self-index writes.

**The empty-`ParentCountry` trap.** `FindIndexOfName` (`0x5117D0`) matches on
**`Name` (`+0x64`)** first, then `ID` (`+0x24`); returns `-2` for `"<random>"`
and `-1` when not found. **Vanilla defines `ParentCountry=` for no country at
all**, so every house passes an empty string, which:

- returns `-1` if every country has a non-blank `Name=` → `1u << -1` is bit 31
  on x86 (the shift count is masked to 5 bits) → matched by nothing → the test
  fails for **every** country. This is vanilla's normal state, and the game
  ships that way — so **this path tolerates failure**;
- but returns a **real index** if any country has a *blank* `Name=`, matching
  the first such country in array order. Ownership then silently collapses onto
  one arbitrary country, and behaviour flips between working and crashing
  (see `0x4F671D`) as `Owner=` lists change.

A mod that adds countries with blank `Name=` therefore acquires a failure whose
trigger looks unrelated to the edit that caused it.

**Register / calling convention.** `ESI` = `HouseClass*`, `EBX` =
`TechnoTypeClass*`, result of the test in flags at `0x4F65AD`.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-23 — instruction bytes quoted. **Confirmed.** `+0x6CC` = `Owner` is
corroborated independently by the four `ReadHouseTypesList` write sites (see
[Countries-Taunts.md](Countries-Taunts.md)). `+0x64` = `Name` follows from YRpp
`AbstractTypeClass.h` (`ID[0x18]` @ `+0x24`, `zero_3C`, `UINameLabel[0x20]`,
`const wchar_t* UIName` 4-aligned @ `+0x60`, `Name[0x31]` @ `+0x64`) and is
consistent with `ParentCountry` @ `+0x98`. **Confirmed.** The vanilla
"no `ParentCountry` anywhere" claim is from two independent unmodified
14-country `rulesmd.ini` copies — **confirmed** for those files, **not** checked
against a pristine Westwood release.

---

### `0x4F671D` — unguarded NULL deref of `FirstBuildableFromArray` (**crash site**)

**Framework names** — *no framework hooks this address.* Antares **replaces the
callee** (`0x5051E0`, `Ext/House/Hooks.BasePlan.cpp:148`, *"replaced the entire
function"*) and guards its NULL return at two *other* call sites, but not here.

**What it does.** Picks a base unit from `[General]BaseUnit=` for a house that
has no buildings, and dereferences the result without checking it:

```asm
4f670b:  mov 0x8871e0,%eax        ; RulesClass::Instance
4f6712:  add $0x938,%eax          ; &Rules->BaseUnit  (TypeList<UnitTypeClass*>)
4f6718:  call 0x5051e0            ; HouseClass::FirstBuildableFromArray
4f671d:  mov (%eax),%edx          ; <<< EAX == 0 -> C0000005
4f6722:  call *0x84(%edx)         ; virtual call through the null vtable
```

`FirstBuildableFromArray` returns **NULL** when the house can build nothing in
the list — a normal, expected outcome (it checks `Owner=`,
`Required`/`ForbiddenHouses=`, `AIBasePlanningSide=`). Every other consumer
treats NULL as "none"; this one does not.

**Why it matters.** This is the address at which the country-identity problems
above become a **Fatal Error** rather than a silent mismatch. Observed
`C0000005 at 004F671D` four times across two days on a mod with 61 countries,
with different victim countries each time (`Brazil`, `Japan`) — the victim is
whichever house the base-planning path happens to evaluate, not a property of
that country.

**How to identify the failing house from a dump:** `HouseClass + 0x34` →
`HouseTypeClass*`, ID string at `+0x24`.

**What it does *not* do — easily mistaken.** The `[Developer fatal]` line
*"House of country [%s] cannot build anything from [General]BaseUnit="* that
often appears in `debug.log` shortly before the crash is **Antares' own message
from a different call site** (`0x5D705E`,
`MPGameMode_SpawnBaseUnit_BaseUnit`) — one of the two it *does* guard. Its
presence is a useful signal but it is **not** emitted by the crashing site, and
its absence does not mean this crash is something else.

**Diagnosis checklist** when this fires:
1. Does every country have a non-blank `Name=`? A blank one hijacks
   `FindIndexOfName("")` (see `0x4F657A`).
2. Does the victim country's resolved bit appear in the `Owner=` of at least
   one `BaseUnit=` entry?
3. Are any countries at index ≥ 32? Their bit aliases mod 32.

The robust mod-side fix is `ParentCountry=<self>` on every country, which makes
each resolve to its own index instead of a shared accident.

**Upstream.** Worth reporting to the Antares/Phobos channel as a missing third
guard; the framework's own comment beside the two existing guards anticipates it
(*"I imagine we'll have a pile of hooks like this sooner or later"*).

**Confirmed via.** `except.txt` from four crash snapshots (`C0000005 at
004F671D`, `EAX: 00000000`) plus `objdump` of vanilla `gamemd.exe`
(sha1 `189a5a86…`) — instruction bytes quoted. **Confirmed.**
`RulesClass::Instance` @ `0x8871E0` and `FirstBuildableFromArray` @ `0x5051E0`:
YRpp `RulesClass.h:86`, `HouseClass.h:476`. **Confirmed.** `+0x938` = `BaseUnit`
is **inferred** from the field order in `RulesClass.h` plus the engine's own
`[General]BaseUnit=` log text; not independently offset-checked.

---

### `0x4F79E4` / `0x4F7A77` — the `RequiredHouses` / `ForbiddenHouses` tests

**Framework names** — *no framework hooks these addresses.* They are interior
points of `HouseClass::CanBuild` (`0x4F7870`), which the Ares lineage replaces
wholesale — so under Antares this vanilla code is dead and the framework's own
implementation decides. Documented because it is the reference semantics.

**What it does.** `EDI` = `TechnoTypeClass*`, `EBP` = `HouseClass*`.

```asm
; RequiredHouses (+0xDA0)
4f79e4:  mov 0xda0(%edi),%eax
4f79ea:  cmp $0xffffffff,%eax
4f79ed:  je  0x4f7a77             ; -1 = no restriction -> straight to Forbidden
4f79fb:  mov 0xb8(%ecx),%ecx      ; House->Type->ArrayIndex2  (the country's OWN index)
4f7a01:  shl %cl,%edx             ; 1 << ArrayIndex2
4f7a03:  test %edx,%eax
4f7a05:  jne 0x4f7a77             ; match -> go check Forbidden
         ;  ...else fall into the four AltOwner paths below; if they also fail,
         ;  jump to 0x4F7994 (FAIL) and Forbidden is NEVER evaluated

; ForbiddenHouses (+0xDA4)
4f7a77:  mov 0xda4(%edi),%eax
4f7a7d:  cmp $0xffffffff,%eax
4f7a80:  je  0x4f7a9a             ; -1 -> continue past
4f7a92:  test %edx,%eax           ; same 1 << ArrayIndex2
4f7a94:  jne 0x4f7994             ; match -> FAIL
```

**Precedence — it is an AND, not an override.**

| `RequiredHouses` | `ForbiddenHouses` | Result |
|---|---|---|
| fails | **not evaluated** | unbuildable |
| passes or `-1` | matches | unbuildable |
| passes or `-1` | no match or `-1` | continue |

"Forbidden wins when both name the country" is a correct *outcome*, but there is
no priority rule in the code: the semantics are
`Required_satisfied AND NOT Forbidden_matched`, with Forbidden evaluated second
and only when Required already passed.

**What it does *not* do — easily mistaken.** `RequiredHouses` is **not** a single
test. When the direct `ArrayIndex2` check fails, the engine tries four
alternate-ownership bitfields on the *house*, each gated on the item's abstract
type (`0x4F7A07`–`0x4F7A71`):

| House field | Offset | `WhatAmI()` | Type |
|---|---|---|---|
| `InfantryAltOwner` | `+0x2C4` | `0x10` | `InfantryType` = 16 |
| `UnitAltOwner` | `+0x2C8` | `0x28` | `UnitType` = 40 |
| `AircraftAltOwner` | `+0x2CC` | `0x03` | `AircraftType` = 3 |
| `BuildingAltOwner` | `+0x2D0` | `0x07` | `BuildingType` = 7 |

Each is `RequiredHouses & <AltOwner>` — the captured-factory mechanic. So a house
may satisfy `RequiredHouses=` **without its own country being listed at all**.
Anyone reimplementing or gating on `RequiredHouses` who tests only
`1 << ArrayIndex2` silently breaks captured-factory buildability.

These four are also **32-bit country bitfields**, so they carry the same ceiling
and the same mod-32 aliasing as the INI-side tags (see
[Countries-Taunts.md](Countries-Taunts.md)) — but they are *runtime* state, so a
hook on the INI parser `0x4750D0` does not reach them.

**Used by / interactions — the Ares lineage keeps the precedence but DROPS the
AltOwners.** Antares replaces `0x4F7870` wholesale
(`Ext/House/Hooks.cpp:26` → `HouseExt::PrereqValidate` → `RequirementsMet`), and
the operative line is `Ext/House/Body.cpp:115`:

```cpp
if(!pHouse->InRequiredHouses(pItem) || pHouse->InForbiddenHouses(pItem)) {
    return RequirementStatus::Forbidden;
}
```

- **Precedence: identical.** C++ `||` short-circuits, so a failed
  `RequiredHouses` returns before `InForbiddenHouses` is evaluated — the same
  conjunction, in the same order, as the vanilla asm above.
- **AltOwners: gone.** YRpp's `HouseClass::InRequiredHouses` (`HouseClass.h:637`)
  is purely `pItem->InRequiredHouses(1u << this->Type->ArrayIndex2)`. No
  AltOwner test exists in the Ares-lineage path, so **captured-factory
  satisfaction of `RequiredHouses=` does not happen under Antares/Ares.** A mod
  that depends on it loses it silently when the framework is loaded.

⚠ **YRpp mislabels these four fields.** `HouseClass.h:874-884` carries exactly
this AltOwner logic as commented-out pseudo-code introduced by *"these four are
unused horrors"*. They are **not** unused in vanilla — the disassembly above
reads all four. The comment is true only of the Ares lineage.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-09-25 — instruction bytes quoted. **Confirmed.** Field identification
corroborated by YRpp `HouseClass.h:885-888` (four consecutive `DWORD`s in the
order Infantry/Unit/Aircraft/Building, matching the `WhatAmI()` constants
16/40/3/7) and the constants themselves by `GeneralDefinitions.h`.
**Confirmed.** Antares behaviour from source at `9f25bdb`. **Confirmed.**

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
  Antares' handler writes `EAX` and jumps past the vanilla body, so a chained
  handler has nothing useful to extend and merely fights over `EAX`.
  **Use `0x4F8361` instead** (below).
  *(Precision note — now **disputed**. This page has said both "it never runs"
  and "it does still execute, because Syringe runs every registered handler and
  the first non-zero return only decides control flow". There is a runtime
  observation for each: see the ⚠ UNRESOLVED section in
  [Syringe-Stub-Semantics.md](Syringe-Stub-Semantics.md). **Assume nothing —
  prove your handler is live with a log line before its first bail.** The
  practical advice is unchanged either way: use `0x4F8361`.)*

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

> ⛔ **SUPERSEDED, in two ways — do not stop reading here.** Kept because the
> symptom description is accurate and is what you will actually observe.
>
> 1. **There IS a second gate.** `HouseClass::ShouldDisableCameo` (`0x50B370`)
>    decides the cameo's disabled state without consulting `CanBuild` at all. See
>    *"…and even answering BOTH calls is not enough"* below. Hunting for a second
>    gate was the correct instinct.
> 2. **`-1` is not uniformly ignored.** Antares' `HouseExt::HasFactory` compares
>    `(int)CanBuild(...) <= 0` — signed — so `-1` blocks there exactly like `0`.
>    The vanilla `test eax,eax` sites counted below are real, but several sit
>    inside functions Antares *replaces*, so they are not all live.
>
> What survives: `0` is the only value every reader agrees on, so prefer it when
> you want a hard refusal — but if you want **greyed-and-still-blocked**, `-1`
> alone will not get you there, and neither will `0` (it removes the cameo).
> That combination needs `0x50B669`.

Write **`Unbuildable` (0)** to actually refuse — it is falsy, so every caller
agrees *(true, and the one part of this section that never needed correcting)*,
and removing the cameo is what vanilla itself does for
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

### …and even answering BOTH calls is not enough — `ShouldDisableCameo`

Both sections above are about what `CanBuild` returns. **A third-party gate can
get every one of those right and still ship a clickable, greyed-out cameo**,
because whether a cameo is *disabled* is decided somewhere else entirely.

`StripClass_Draw_GetCameo1` does two independent things (`0x6A97D2` onward):

```
6a97d2:  call 0x4F7870        ; CanBuild(type, 0, 0)
6a97e1:  cmp  eax,0xFFFFFFFF
6a97e5:  sete [esp+0x16]      ; darken flag = (result == -1)   <- your -1 lands here
6a97ea:  call 0x50B370        ; HouseClass::ShouldDisableCameo  <- and here it does NOT
```

**`0x50B370` is a fifth Ares-lineage full replacement** in this path (after
`0x4F7870`, `0x5F7900`, `0x6F47A0`, `0x500910`). Antares'
`HouseClass_ShouldDisableCameo` (`src/Ext/House/Hooks.Queue.cpp:115`) recomputes
availability from **`pItem->BuildLimit` — the vanilla INI field** — via
`HouseExt::BuildLimitRemaining`, and **never calls `CanBuild` at all**. A
third-party build limit is invisible to it by construction.

Symptom: the cameo greys (your `-1` reached the draw path) and stays clickable
(you were never party to the disable decision). It looks identical to "the
refusal half worked", which is why it gets misdiagnosed as a `-1`-vs-`0` problem.

⚠ **Correction to a claim previously made on this page:** `-1` is not uniformly
"too weak". Antares' `HouseExt::HasFactory` gates on
`(int)pHouse->CanBuild(pItem, true, true) <= 0` (`src/Ext/House/Body.cpp:382`) —
a **signed** compare, where `-1` blocks exactly like `0`. The eight
`test eax,eax` sites in *vanilla* are real, but several of them are inside
functions the frameworks replace, so under Antares the population of live
readers is different. Check the framework's code, not just `gamemd`.

**Seat for fixing it:** `0x50B669`, Antares' own jump target — the same
post-process-the-epilogue pattern as `0x4F8361`. At the `ret 0x4` the frame is
still the callee's: `ECX = HouseClass*`, `[ESP+4] = TechnoTypeClass*`,
`AL` = the bool Antares computed. Raise it to `true` to disable; never lower it,
or you grant buildability that other layers have refused. The 5-byte patch
spills into the vanilla switch jump table at `0x50B66C`, which is unreachable
for the same reason the `0x4F8361` waiver is valid — Antares owns the only entry
and always returns here.

**Confirmed via.** objdump of `gamemd.exe` at `0x6A97D2`–`0x6A97F3` and
`0x50B650`–`0x50B66C`; Antares `src/Ext/House/Hooks.Queue.cpp:115` and
`src/Ext/House/Body.cpp:174-186, 377-382`; the in-game symptom that prompted the
search (a globally build-limited Chronosphere darkening but still building).

### `ShouldDisableCameo` has a SECOND clause — and it is the one that bites

The description above ("recomputes availability from `pItem->BuildLimit`") is
accurate but **incomplete**, and the omitted half is the dominant one. Antares'
replacement (`src/Ext/House/Hooks.Queue.cpp:115-180`) is two tests, not one:

```cpp
if(HouseExt::BuildLimitRemaining(pThis, pType) - queued <= 0) {
    ret = true;                       // the documented clause
} else {
    auto const state = HouseExt::HasFactory(pThis, pType, true, true, false, true).State;
    ret = (state < HouseExt::FactoryState::Available);   // THE OTHER ONE
}
```

So `ShouldDisableCameo` is **also a factory check**. For a BuildingType with no
Construction Yard, `HasFactory` yields `NoFactory`, which is `< Available`, so
the cameo is disabled **unconditionally** — and since the function never calls
`CanBuild`, *no* verdict at `0x4F8361`, `0x5F7A89` or any other `CanBuild`-side
seat can reach it.

**Measured, in game (BuildQueueExt, 2026-10-02).** A tagged BuildingType with
its ConYard gone, with all three `CanBuild`-side pieces independently verified
working — cameo force-inserted via `AddCameo`, `CanBuild` promoted to
`Buildable`, `FindFactory` substituted with a real owned building:

```
frame 51221: GAPILL house 0 -> ALLOWED (engine said unbuildable)
  T25_NoConYard: gate=active test=pass
```

…and the cameo was **still dark and still refused clicks**. The `CanBuild` path
was never the binding constraint. ⚠ This is worth internalising as a pattern:
*a seat can be where a verdict is **observable** without being where it is
**decided**.* The same mistake had already been made once on this feature, at the
`CanBuild` epilogue.

#### A sanctioned exception to "never lower it"

The guidance above — raise to `true`, never lower — is right as a default, and
the reason given is correct: lowering grants buildability other layers refused.
There is one case where lowering is the entire point, and it can be scoped
safely. BuildQueueExt's `AlwaysAvailable` lowers at `0x50B669` only when **all**
of these hold:

- the type carries the feature's own opt-in tag;
- the house has **no usable factory** for the type's abstract — i.e. the disable
  can only have come from the `HasFactory` clause, never from something else;
- `BuildLimit` is **not** genuinely spent, mirroring Antares'
  `BuildLimitRemaining` semantics (`> 0` counts owned-now, `< 0` counts
  owned-ever, **`0` means unlimited** — treating `0` as a limit of zero disables
  every ordinary building, a trap worth naming);
- the house is not an observer or defeated.

Everything any other layer disabled for any other reason stays disabled.

⚠ **Chain order is load-bearing for this.** Phobos occupies this same epilogue
(`Phobos/src/Ext/House/Hooks.cpp:349`, size `0x5`, always returns `0`) and
raises. A handler that lowers must be injected **after** Phobos or its result is
overwritten — verify with the `-i=` order in `syringe.log` rather than assuming;
there is no ordering guarantee beyond load order.

**Confirmed via.** Antares `src/Ext/House/Hooks.Queue.cpp:115-180`; Phobos
`src/Ext/House/Hooks.cpp:349-362`; in-game 2026-10-02 as quoted above.

#### ✅ CONFIRMED SUFFICIENT — in game, 2026-10-02

Lowering at `0x50B669` **is** enough to make the cameo both live and clickable.
A BuildingType with its Construction Yard gone became fully buildable, and the
produced building placed and completed normally:

```
disable-probe #1 GAPILL: incoming=1 hasFactory=0 limitReached=0 spectating=0
ENABLE-CAMEO #1 GAPILL -- lowered ShouldDisableCameo (no usable factory, limit ok)
SUBSTITUTE #1 GAPILL -> stand-in YABRCK
```

`incoming=1` is the important field: Antares really had disabled the cameo via
the `HasFactory` clause, so the lower is doing real work rather than riding a
verdict that was already permissive.

⚠ **The click-time gate at `0x6AB312` did NOT need satisfying, and the
"unpowered factory" reading of it was WRONG.** It was predicted that an
unpowered stand-in would be rejected there. Tested directly: the only owned
building was an **unpowered barracks** (no power plant anywhere on the base) and
production started and finished regardless. So either that gate does not reject
on power the way it appears to, or it is not on this path. Treat `0x6AB312` as
**uncharacterised** rather than as a power check.

**What a `FindFactory` stand-in must actually satisfy:** merely existing. Any
owned building works — powered or not, factory or not. The only failing case is
owning **zero** buildings, which yields a null factory and a cameo that
highlights on click without starting production.

**Confirmed via.** In-game 2026-10-02, two runs: one with a self-powered power
plant as the only building, one with an unpowered barracks as the only building.
Both built. A third with no buildings produced the highlight-but-no-build
symptom.

### …and it is **not** evaluated every frame

`CanBuild` is consulted when the engine rebuilds the sidebar / rechecks the tech
tree — driven by *events* (a building finishes, is sold, is destroyed), not by a
per-frame tick. For a verdict that depends only on owned objects this is
invisible, because the events and the verdict change together.

It becomes visible the moment a verdict depends on the **match clock**. A
condition that flips on frame N is not observed until the next recheck, which can
be a long time later. Measured in a build with a once-per-frame diagnostic:

| Condition | Should flip at | Actually observed | Lag |
|---|---|---|---|
| absolute deadline | frame 4500 | frame 4920 | 420 frames (~28 s) |
| expiring window | frame 7570 | frame 8283 | 713 frames (~47 s) |

Worse, a window **shorter than the gap between rechecks can open and close
entirely unobserved** — the cameo never appears at all, and the same
configuration appears to behave differently from run to run depending on what
else happened to trigger a recheck. That non-determinism is the tell.

The fix is to drive the re-evaluation yourself: set `HouseClass::RecheckTechTree`
on a timer from a per-frame seat (e.g. `0x55B6B3`, see
[Logic-Frame-Update.md](Logic-Frame-Update.md)). Once per second was enough to
bring the same deadline in at frame 4501 against a target of 4500 — one frame.

**Multiplayer caution.** Drive it **uniformly for every house, from the shared
frame counter**. Limiting the nudge to `CurrentPlayer` makes clients re-evaluate
buildability on different frames, which is a lockstep divergence waiting to
happen.

**Confirmed via.** In-game measurement with a per-verdict-change log (frame
numbers above, 15 fps); the corrected timings after adding a 1 Hz
`RecheckTechTree` nudge. The *reason* CanBuild is event-driven was inferred from
this behaviour, not from disassembling the sidebar refresh path — treat the
mechanism as unconfirmed, the timings as measured.

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
