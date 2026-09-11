# Syringe stub semantics — when `return 0` is a bug

Not an address page. This collects a **family of crashes** caused by one thing:
what Syringe's stub does *after* your handler returns `0`.

A `DEFINE_HOOK(addr, name, size)` patches a 5-byte jump at `addr` (padding with
NOPs when `size > 5`) into a generated stub. The stub calls your handler, and:

- **handler returns non-zero** → jump to that address; the copied original bytes
  are **not** executed.
- **handler returns 0** → execute the **copied original bytes**, then resume at
  `addr + size`.

"Return 0 to continue normally" is the usual mental model, and it is right only
when the stolen bytes are still *valid to run* after your handler. Two common
shapes make them invalid — and in both, the hook's **geometry is perfect**
(correct size, no split instruction, no overlap), so size/bounds checkers pass it.
**The defect is control flow, not layout.**

---

## Shape 1 — the stolen bytes contain a relative branch

Copied bytes are **not relocated**. A stolen `jcc`/`jmp`/`call` with a relative
displacement, executed from the stub, computes its target relative to the *stub*,
landing in unmapped memory.

Seen at the three `EvaluateObject` threat gates (`0x6F84A9`, `0x6F8503`,
`0x6F858F`) — see [Target-Evaluation-Threat.md](Target-Evaluation-Threat.md).
Symptom: `C0000005` at an address like `0x09ED0475`, reached from
`GreatestThreat` `0x6F9D7B`.

**Rule:** if the patch window contains a relative branch, replicate the branch in
your handler and return an explicit address. Never `return 0`.

---

## Shape 2 — the stolen bytes re-read a register your handler wrote

If the hook covers a **read** and the handler writes that read's *destination*
register, returning `0` re-runs the read — using your computed **value** as a
**pointer**.

Field example (TechnoAttachmentExt, 2026-09-02). Hooking
`0x6FB01C` `mov eax,[eax+0x684]` in `TechnoClass::Reload` — on entry `EAX` is the
`TechnoTypeClass*`, on exit it should be the ammo capacity. The handler did:

```cpp
R->EAX(capacity);
return 0;              // BUG
```

The stub then re-ran `mov eax,[eax+0x684]` with `EAX` = the capacity.
`TechnoTypeClass::Ammo` is **-1 for every unlimited-ammo type**, so `EAX` became
`0xFFFFFFFF` and it read `[0xFFFFFFFF+0x684]`. `C0000005` **at launch**, for
essentially every unit. Fix: `return 0x6FB022;` (`addr + 6`, past the patched
window).

**The sentinel is the amplifier.** Values like `-1` / `0` / `0xFFFFFFFF` turn a
"rare edge case" into "fires immediately for everything". A useful tell: if
vanilla's *very next* instruction tests for a sentinel (`cmp eax,0xFFFFFFFF; je`),
that value is not exceptional — it is expected, and your handler will produce it.

**Rule:** writing a register the stolen instruction reads → return
`addr + size`, never `0`.

---

## Reading the crash

An EIP inside a Syringe stub — a small offset into an address unlike any module
base, e.g. `0x0A040029` (+0x29) — is the **copied-original-bytes** region. To
name the culprit, read the `push <origin>` at the top of that stub: the pushed
value is the hooked game address, which identifies the hook and its owning DLL
directly. That turns "mystery address" into a named hook in one step.

## Scanning a codebase for shape 2

Match **"the stolen instruction dereferences the same register the handler set"**.
Do *not* simply grep for `R->EAX` — in Phobos's macro set `R->EAX()` with empty
parens is the **getter**, and treating it as a write floods the results with false
positives. With that narrowing, a sweep of several DLLs found exactly one true
instance; a superficially identical site (MapSizeExt `0x5270C5`) proved safe
because every path there returns a non-zero address.

**Confirmed via.** Syringe stub layout (5-byte patch + NOP padding, `push
<origin>` prologue, copied-bytes tail); in-game crashes and their fixes for both
shapes; `objdump` of `gamemd.exe` at `0x6FB01C`/`0x6FB08E` and the three
`EvaluateObject` gates.

---

## ⚠ UNRESOLVED — does a non-zero return stop the *rest of the chain*?

Everything above concerns **one** handler. When several DLLs hook the **same
address**, this page's model is silent about what happens to the handlers
registered *after* one that returns non-zero — and **this repository currently
contains two runtime observations that contradict each other.** Neither is
inference; both were seen in real games on the same machine, in the same inject
list. Do not treat either as settled.

**Observation A — later handlers DO run.** `Spy-Infiltration.md` (see its
"VERIFIED — co-hooking `0x4571E0`" section): Antares registers first at
`0x4571E0` and wraps the whole function, returning `0x4575A2`. `IntelExt`
registers later at the same address and returns `0`. **IntelExt's log lines
appear in real games**, so its handler ran despite the earlier non-zero return.

**Observation B — a later handler did NOT run.** `PrerequisiteExt`'s sell hook at
`0x449CC1` (an address a co-loaded framework wraps) **never produced a single log
line**, with a log statement placed as the handler's first statement, before any
bail. The symptom is the nastiest one this repository documents: *parsed, then
silently nothing*. No handshake failure, no crash, no diagnostic.

**What is NOT yet known** — any of these would explain the split, and none has
been tested: whether Syringe orders handlers by inject-list position or by
something else; whether the two cases differ in *which* handler returned
non-zero (first-registered vs later); whether the `0x449CC1` handler was dead for
an unrelated reason (wrong address, a raw patch overwriting the jump, the site
never being reached at all on the sell path).

**The rule that survives either answer, and the only safe one:**

> A same-address co-hook is **legal** (Syringe installs it without complaint) but
> that is **not** the same as **live**. Prove liveness with a log line emitted as
> the handler's *first statement*, before every bail. Never conclude "my handler
> runs" from source, from this page, or from the absence of an error — and when a
> feature parses correctly and then does nothing at all, suspect a dead handler
> **before** suspecting your own logic.

Overlap checkers cannot see this: they compare byte ranges, and a dead handler's
geometry is perfect. `PrerequisiteExt/tools/check_local_overlap.py` prints the
caveat next to every same-address note for exactly this reason.

Resolving this properly means reading Syringe's own stub generator (source not
present on this machine — only `YRpp/Syringe.h`, which defines the handler ABI
and says nothing about multi-handler dispatch) or disassembling a generated stub
at an address with three or more registered handlers. **Worth doing: the answer
changes the design rule for every co-hooked address in this repository.**
