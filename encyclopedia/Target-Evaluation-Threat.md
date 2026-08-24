# Target Evaluation & Threat Gates (`TechnoClass::EvaluateObject`)

`TechnoClass::EvaluateObject` (**`0x6F7CA0`**) scores a candidate object as a
target for `this`. It is called in a tight loop from `GreatestThreat`
(the call site is `0x6F9D76`: `call 0x6F7CA0`, return address `0x6F9D7B`). Inside
it, a series of **threat gates** reject candidates that vanilla considers
un-targetable — most importantly objects with `ThreatPosed=0` (unarmed
buildings, passive support units, etc.). Extensions that add an "aggressive
stance" / "attack anything" behaviour intercept these gates to *skip* the
rejection.

⚠️ **Every one of these gates' stolen bytes contains a relative branch.** Read
the "Trampoline footgun" section below before hooking any of them — getting it
wrong produces a reliable crash that looks like it comes from nowhere.

---

### `0x6F84A9` — EvaluateObject, vehicle (`UnitClass`) threat gate

**What it does.** `test cl,cl / jne 0x6F894F` — rejects the candidate (jumps to
the `DisallowedObject` label `0x6F894F`) when a per-target-type flag is set.
Reached for vehicle candidates.

**Stolen bytes (8).** `84 C9 0F 85 9E 04 00 00`. Fall-through / continue =
`0x6F84B1`; deny = `0x6F894F`. Contains a **`jne rel32`**.

**Register / calling convention.** `EDI = this` (attacker), `ESI = candidate`,
`CL` = the flag being tested.

---

### `0x6F8503` — EvaluateObject, non-building threat gate

**What it does.** `je 0x6F894F` — rejects the candidate when the value tested by
the preceding `test eax,eax` (`0x6F8501`) is zero. Reached for non-building
candidates (infantry / aircraft, and vehicles that passed `0x6F84A9`).

**Stolen bytes (6).** `0F 84 46 04 00 00` (`je 0x6F894F`). Fall-through =
`0x6F8509`; deny = `0x6F894F`. A common aggressive-stance bypass returns
`0x6F851C` to also skip the follow-up `call 0x50B730` eligibility check. Contains
a **`je rel32`**; `ZF` originates from the `test eax,eax` *before* the hook, so a
replicating hook must read `EAX` at entry.

**Register / calling convention.** `EDI = this`, `ESI = candidate`, `EAX` = the
tested value.

---

### `0x6F858F` — EvaluateObject, building threat gate

**What it does.** `test edi,edi / je 0x6F85AB / mov al,[edi+0x14]` — begins the
building-specific `ThreatPosed` handling. Aggressive-stance extensions force the
accept path by returning `0x6F88BF`. This is YRAggressiveStance's one
substantive hook (see `sources.md`).

**Stolen bytes (7).** `85 FF 74 18 8A 47 14`. If `EDI == 0` the original jumps to
`0x6F85AB`; otherwise it loads `AL = [EDI+0x14]` and continues at `0x6F8596`
(the next insn, `shr al,2`, consumes `AL`). Contains a **`je rel8`**, so a
replicating hook that wants the continue path must set `AL` itself and return
`0x6F8596` — it **cannot** return into the stolen window (`0x6F858F`–`0x6F8595`),
because Syringe's 5-byte JMP clobbers those bytes.

**Register / calling convention.** `EDI = this`, `ESI = candidate`.

---

## The trampoline footgun (why all three bite)

When you hook at entry (`DEFINE_HOOK`) and `return 0`, Syringe re-executes the
copied stolen bytes from its **trampoline stub** (a `VirtualAlloc`'d page,
observed around `0x09ED0000` under wine) and then jumps back to `addr+size`. The
copied bytes are **not relocated**. A stolen `jcc rel8/rel32` therefore computes
its target relative to the *stub*, not the original site, and sends `EIP` to a
garbage offset inside the stub page.

**Observed crash signature (YRAggressiveStance, three identical snapshots).**
`C0000005` at `EIP ≈ 0x09ED0475`, with return address `0x6F9D7B` on the stack
(i.e. inside `GreatestThreat → EvaluateObject`). The `0x6F8503` gate is the usual
trigger because its `return 0` path is hit for almost every non-building
candidate scanned. All the extension DLLs load at `0x77xxxxxx`, so an `EIP` in
the `0x09xxxxxx`/`0x0Dxxxxxx` range is a dead giveaway for an executing Syringe
stub rather than any module's code.

**The fix: never `return 0` from these gates.** Always return an explicit
address, replicating the stolen branch by hand from the register context:

```cpp
// 0x6F8503 example
enum { SkipDeny = 0x6F851C, Deny = 0x6F894F, Continue = 0x6F8509 };
if (aggressiveBypassApplies) return SkipDeny;
return (R->EAX() == 0) ? Deny : Continue;   // reproduces `je 0x6F894F`
```

For `0x6F84A9` use `R->CL()`; for `0x6F858F`, return `0x6F85AB` when `EDI == 0`,
otherwise `R->AL(*(BYTE*)(pThis + 0x14))` and return `0x6F8596`.

**Used by / interactions.** Antares' aggressive-attack-move behaviour and
Phobos' `AttackMove_Aggressive` both operate in this function; Phobos' hook sits
at `0x6F85AB` (stolen bytes `mov ecx,[edi+0x21c]` — no branch, safe). The three
gates above are the ones a custom "aggressive stance" DLL adds, and are the ones
that carry the branch hazard. Multiple DLLs hooking the same gate chain safely;
the danger is the un-relocated branch, not co-tenancy.

**Confirmed via.** objdump of vanilla `gamemd.exe` (all addresses/stolen bytes
above); crash forensics on `debug/snapshot-2026*/except.txt` (three snapshots,
identical `0x09ED0475` fault reached from `0x6F9D7B`); fix applied and reasoned
in YRAggressiveStance `src/Ext/Techno/Hooks.TargetEvaluation.cpp`. Not yet
re-verified in-game post-fix (MSVC build required). See also the general note in
[Cell-Numbering-Events-Pathfinding.md] ("Hook-at-entry with `return 0`
re-executes the stolen bytes in the trampoline") and the relocation caveat in
[Veterancy-Abilities.md].
