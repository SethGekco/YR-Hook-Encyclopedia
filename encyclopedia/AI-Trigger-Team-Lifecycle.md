# Subsystem: AI Trigger evaluation, team selection & lifecycle

The vanilla path by which a skirmish/multiplayer AI turns an `[AITriggerTypes]`
entry into a live attack/defense team, and the callbacks fired when that team
later succeeds or dies. Entries sorted by address.

**None of these addresses is hooked by any mainline framework** (Phobos, Antares,
Ares, Kratos) — none appears in `registry/hooks.csv`. This page therefore
documents the **vanilla engine** functions themselves, for anyone who wants to
observe or extend AI team behaviour. Register/stack details were cross-checked
against an incidental consumer that does hook them (the `AITriggerTypeExt`
Syringe DLL); the subject here is the engine, not that mod.

All addresses are for the standard YR `gamemd.exe`, imagebase `0x400000`,
verified by objdump/Ghidra disassembly (2026-07-17). Ghidra `FUN_` names are
given so you can find the same function in your own database.

## The pipeline in one glance

```
per AI evaluation tick, per trigger:
  AITriggerTypeClass::ConditionMet (0x41E720)      ── does this trigger's INI condition pass?
        │ true-return 0x41EAC0  (ESI=trigger, EDI=owner house, EBX=enemy house)
        ▼
  HouseClass::FindEligibleAITeams (0x6F0AB0)        ── collect all passing triggers into a
        │                                              weighted distribution, draw ONE winner
        │ winner picked 0x6F0D1B → EDI, non-null by 0x6F0D26
        ▼
  TeamTypeClass::CreateTeam (0x6F09C0)              ── actually build a team… or not (caps,
        │ AI-trigger caller 0x4F8AAD, return 0x4F8AB2   existing instance, production gating)
        ▼   EAX = new TeamClass* (may be NULL)
  … team lives, runs its ScriptType …
        ▼
  TeamClass destructor (0x6E8DE0)
        ├─ script completed  → AITriggerTypeClass::RegisterSuccess (0x41FD60)  ECX=trigger
        └─ wiped out first   → AITriggerTypeClass::RegisterFailure (0x41FE20)  ECX=trigger
```

The single most important thing to understand: **"won the weighted draw" is not
"a team was built."** They are two different addresses (`0x6F0AB0` vs `0x4F8AB2`)
and the gap between them is large — see the two "easily mistaken" notes below.

---

### `0x41E720` — AITriggerTypeClass::ConditionMet (`FUN_0041E720`)

**Framework names.** None in the registry — no mainline framework hooks the AI
trigger condition evaluator.

**What it does.** `__thiscall`, `ECX = AITriggerTypeClass*` at entry. Returns
`AL = 1` if this trigger's vanilla condition (its `RequiredHouse`, the owner/enemy
building-count comparison encoded in the `[AITriggerTypes]` line, side/ownership,
etc.) is currently satisfied, else `AL = 0`. This is the gate that decides whether
a trigger is even *eligible* to enter the weighted draw. It is called repeatedly —
once per candidate trigger per AI evaluation cycle — so it is a hot path.

Useful interception points:
- **Entry `0x41E720`** — prolog `PUSH EBX/EBP/ESI + MOV ESI,ECX + PUSH EDI` = 6
  bytes. `ECX = this`. Hook here if you only need the trigger identity (e.g. to
  read a sidecar `[TriggerID.AIExt]` extension).
- **True-return `0x41EAC0`** — epilog `POP EDI/ESI/EBP + MOV AL,1` = 5 bytes.
  Fires *only when the trigger passed*. Registers are still live here:
  - `ESI = AITriggerTypeClass*` (the trigger)
  - `EDI = HouseClass*` — the owning/calling AI house
  - `EBX = HouseClass*` — the resolved enemy/target house
  This is the ideal place to AND-in extra conditions: re-evaluate, and if your
  extra check fails, jump to the false-return instead.
- **False-return `0x41EA84`** — `POP EDI/ESI/EBP + XOR AL,AL + POP EBX + RET 0xC`.
  Jump target for "veto this trigger." Note the `RET 0xC`.

**What it does *not* do — easily mistaken.**
- The `ESI/EDI/EBX = trigger/owner/enemy` mapping is only guaranteed **at the
  true-return `0x41EAC0`**. Do not assume those registers hold the same things at
  the entry or mid-function.
- It does **not** build or dispatch anything — it only answers "is this trigger's
  condition met right now?" A trigger can pass `ConditionMet` every tick for a
  long time and still never produce a team, because selection (`0x6F0AB0`) and
  creation (`0x4F8AB2`) are downstream and can all decline.
- The enemy house in `EBX` is the engine's already-resolved target for this tick;
  it is not "every enemy." Multi-enemy logic must resolve houses itself.

**Confirmed via.** objdump/Ghidra of vanilla `gamemd.exe`; register mapping at
`0x41EAC0` cross-checked in-game via the incidental consumer. **Confirmed.**

---

### `0x41FD60` — AITriggerTypeClass::RegisterSuccess (`FUN_0041FD60`)

**Framework names.** None in the registry.

**What it does.** `__thiscall`, `ECX = AITriggerTypeClass*`. Called from the
`TeamClass` destructor (`0x6E8DE0`, via vtable slot `+0x20`) when a team spawned
by this trigger **completed its ScriptType** and disbanded normally — the
*success* path. Vanilla uses it to bump the trigger's running weight by
`AITriggerSuccessWeightDelta` (scaled by the track-record coefficient), so the AI
favours approaches that work. First stolen bytes at entry:
`PUSH ECX (1) + MOV EDX,[ECX+0x108] (6) + FLD qword [0x7E2800] (6)` = 13.

**What it does *not* do — easily mistaken.**
- The name is about the **script outcome, not the game object**. "Success" here
  means the team finished its orders and was cleaned up — *not* that it killed
  anything. A team that trundles to a waypoint and completes an empty script
  "succeeds." (A consumer that exposes a lifecycle event tends to call this
  `Deleted`/`Completed` rather than `Destroyed`, precisely to avoid this trap.)
- `ECX` is the **AITriggerType**, not the team and not the house. The team is
  already being torn down by the time this runs.
- It is a per-team-instance callback, not per-trigger-once: it fires each time
  *any* team from this trigger completes.

**Confirmed via.** objdump/Ghidra; `ECX = trigger` verified in-game. **Confirmed.**

---

### `0x41FE20` — AITriggerTypeClass::RegisterFailure (`FUN_0041FE20`)

**Framework names.** None in the registry.

**What it does.** `__thiscall`, `ECX = AITriggerTypeClass*`. The mirror of
`RegisterSuccess`: called from the `TeamClass` destructor when the team was
**wiped out before finishing its script** — the *failure* path. Vanilla applies
`AITriggerFailureWeightDelta`, lowering the trigger's weight so a proven-bad
approach is chosen less often. First stolen bytes:
`PUSH ECX (1) + MOV EDX,[ECX+0x108] (6) + PUSH ESI (1)` = 8.

**What it does *not* do — easily mistaken.**
- "Failure" is defined as **script-not-completed**, not "lost a fight." A team
  that is disbanded for other reasons before its script ends counts as failure
  here; a team that completes a suicide script "succeeds" via `0x41FD60`.
- Same `ECX = trigger` (not team/house) and same per-instance firing as
  `RegisterSuccess`.
- The `+0x108` field read in the stolen bytes is the trigger's weight/bookkeeping
  member, not a team pointer.

**Confirmed via.** objdump/Ghidra; `ECX = trigger` verified in-game. **Confirmed.**

---

### `0x4F8AB2` — CreateTeam return, AI-trigger dispatch loop

**Framework names.** None in the registry.

**What it does.** This is the **return site** of a `TeamTypeClass::CreateTeam`
call inside the AI's trigger-dispatch loop. The sequence is:
`FindEligibleAITeams` at `0x4F8A6A` picks a winning trigger, then `0x4F8AAD`
calls `CreateTeam` for its TeamType, and execution resumes at `0x4F8AB2` with:
- `EAX = the new TeamClass*` — **or `NULL`** if creation was declined.
The next instruction (`MOV EAX,[ESP+0x34]`, reloading the loop counter) clobbers
`EAX`, so a hook must read it immediately. Stolen bytes:
`MOV EAX,[ESP+0x34] (4) + INC EDI (1)` = 5.

**What it does *not* do — easily mistaken (the big one).**
- **This — not the weighted draw — is where a team actually exists.** Winning
  `FindEligibleAITeams` (`0x6F0AB0`) does *not* mean a team was built. The engine
  frequently declines creation: `TotalAITeamCap` reached, an instance of that
  TeamType already alive, production/credit gating, etc. Measured in-game, a
  single trigger reported ~114 draw-wins against only a handful of real teams.
  If you want a signal that lines up 1:1 with the eventual
  `RegisterSuccess`/`RegisterFailure`, gate on a **non-NULL `EAX` here**, not on
  the draw.
- `EAX` can be `NULL` — always check before dereferencing.
- There are **three** callers of `CreateTeam` (`0x4F8AAD`, `0x6DEB6E`,
  `0x6E1F76`); only `0x4F8AAD`/return `0x4F8AB2` is the AI-trigger path. The other
  two build teams by other means and won't carry AI-trigger attribution.

**Confirmed via.** objdump/Ghidra of vanilla `gamemd.exe`; the NULL/decline
behaviour and the ~114-vs-few discrepancy observed in-game. **Confirmed.**

---

### `0x6E8DE0` — TeamClass destructor (`FUN_006E8DE0`)

**Framework names.** None in the registry.

**What it does.** The `TeamClass` destructor. Among its teardown work it invokes
the owning trigger's `RegisterSuccess` (`0x41FD60`) or `RegisterFailure`
(`0x41FE20`) — **through a vtable call at slot `+0x20`**, not a direct `CALL`,
which is why those two are reached indirectly. Hook here if you need a
**per-TeamType** "any team of this type just died" signal, independent of which
trigger spawned it (the trigger-scoped success/failure callbacks can't give you
that — they key on the trigger, not the TeamType).

**What it does *not* do — easily mistaken.**
- It does **not** distinguish success vs failure by itself — that determination is
  made before the vtable dispatch and expressed by *which* of RegisterSuccess/
  Failure gets called. If you hook the destructor directly you must inspect team
  state to tell them apart.
- Because RegisterSuccess/Failure are invoked via vtable `+0x20` rather than a
  plain call, searching for direct `CALL 0x41FD60` xrefs will miss this site.

**Confirmed via.** Ghidra — found by tracing xrefs *into* RegisterSuccess/Failure
back through the vtable-`+0x20` dispatch. Address **confirmed**; treated as a
documented placeholder by the incidental consumer (not yet hooked there).

---

### `0x6F09C0` — TeamTypeClass::CreateTeam (`FUN_006F09C0`)

**Framework names.** None in the registry.

**What it does.** Constructs a live `TeamClass` instance from a `TeamTypeClass`
template and returns it (this is what `0x4F8AAD` calls and `0x4F8AB2` receives).
Returns the new team in `EAX`, or a null/decline result when the engine chooses
not to build (see the caps/gating notes at `0x4F8AB2`). Hook the *entry* if you
want to see or veto every team-creation attempt regardless of caller; hook the
*return site* (`0x4F8AB2`) if you specifically want the AI-trigger path with the
winning-trigger context still available.

**What it does *not* do — easily mistaken.**
- Reaching this function does not guarantee a team comes out — the decline logic
  lives inside/around it.
- It is called from three sites; a hook at the function entry sees all of them,
  so you cannot assume AI-trigger provenance here without checking the caller.

**Confirmed via.** objdump/Ghidra; the three call sites enumerated from xrefs.
**Confirmed.**

---

### `0x6F0AB0` — HouseClass::FindEligibleAITeams (`FUN_006F0AB0`)

**Framework names.** None in the registry.

**What it does.** For a given AI house, walks every `[AITriggerTypes]` entry that
passed `ConditionMet`, builds a **weighted distribution** of them, and draws a
single winner to (attempt to) dispatch this cycle. The useful interior point is
`0x6F0D26`:
- At `0x6F0D1B` the winner is selected: `MOV EDI,[EBX+ECX*8]`. The `TEST`/`JE` at
  `0x6F0D1E`/`0x6F0D20` guarantees `EDI != NULL` by **`0x6F0D26`**, where:
  - `EDI = the winning AITriggerTypeClass*`
  - `[ESP+0x48] = distribution array base` (engine reads it at `0x6F0D01`)
  - `[ESP+0x54] = distribution entry count` (engine reads it at `0x6F0CF5`)
- **Distribution entries are 8 bytes each:** `{ AITriggerTypeClass* @ +0,
  int weight @ +4 }`. Walking the array gives you *every* trigger that was
  eligible this cycle plus its weight — i.e. the winner **and** all the losers.
  (The winner is also reachable as `Team1 [EDI+0xDC]` / `Team2 [EDI+0xE0]`.)

This is the natural place to observe AI decision-making: "which trigger won"
(the `EDI` entry) and "which triggers passed conditions but lost the draw"
(every other array entry).

**What it does *not* do — easily mistaken (the other big one).**
- **Winning here is upstream of building a team.** This is the correct site for a
  "considered but rejected" (lost-the-draw) signal, because losers never advance.
  It is the **wrong** site for a "team started" signal — the winner still has to
  survive `CreateTeam` (`0x4F8AB2`), which frequently declines. Firing a "Start"
  event here over-reports by roughly an order of magnitude. Stash the winner here
  and confirm at `0x4F8AB2` instead.
- The distribution array holds only triggers that already passed `ConditionMet`;
  it is not the full trigger list.
- `EDI` is only guaranteed non-null *after* the `0x6F0D20` branch — read it at
  `0x6F0D26`, not earlier.

**Confirmed via.** objdump/Ghidra of vanilla `gamemd.exe`; the 8-byte entry
layout and stack offsets confirmed by disassembly and exercised in-game (the
loser-walk produces one event per losing trigger). **Confirmed.**

---

## Class-extension points (AITriggerTypeClass sidecar sites)

Standard sites for attaching per-trigger extension data (an `ExtData`/container),
included for completeness. These are lifecycle/serialization plumbing rather than
behaviour, so they get a compact table instead of full entries. All confirmed by
Ghidra/objdump of vanilla `gamemd.exe`; several cross-referenced against Phobos
PR #2119.

| Address | Function | Conv. / regs | Notes |
|---|---|---|---|
| `0x41E350` | `AITriggerTypeClass` CTOR (`FUN_0041E350`) | `ECX = this` at entry (saved to `ESI` at `0x41E356`) | Allocate your ExtData here. Steal 5. |
| `0x41E540` / `0x41E5B2` | `IPersistStream::Load` prefix / suffix | stdcall; `[ESP+4]=this`, `[ESP+8]=IStream*`; at suffix `ESI=this` | Read your serialized ExtData across save/load. |
| `0x41E5C0` / `0x41E5D4` | `IPersistStream::Save` prefix / suffix | stdcall; `[ESP+4]=this`, `[ESP+8]=IStream*`, `[ESP+C]=fClearDirty` | Write your ExtData. Callee `RET 0xC`. |
| `0x41F2E0` → `0x41F39F` | `AITriggerTypeClass::CreateFromINIList`, per-item point after `CALL [EDX+0x64]` (`LoadFromINI`) | `ESI = AITriggerTypeClass*`, `EBX = CCINIClass*` | Parse a sidecar `[TriggerID.AIExt]`-style section here. Steal 0xA. |

**Note on the destructor.** The `AITriggerTypeClass` *destructor* address is
**not** confirmed — vtable slot 0 of `0x007E2A50` is `QueryInterface`
(`FUN_00410260`), not the dtor. In practice `AITriggerTypeClass` instances are
only freed on scenario unload, so a missing dtor hook leaks nothing within a
session; finding it is low priority. (Do not confuse this with the *TeamClass*
destructor `0x6E8DE0` above, which is confirmed.)

---

## See also

- Vanilla weight tags this subsystem reads: `AITriggerSuccessWeightDelta`,
  `AITriggerFailureWeightDelta`, `AITriggerTrackRecordCoefficient` (applied in
  RegisterSuccess/Failure), `TotalAITeamCap`, `TeamDelays`, `DissolveUnfilledTeamDelay`
  (gating between selection and creation).
- `registry/vanilla-tags.*` and `registry/engine-string-surface.*` for where the
  engine reads those tag strings.
