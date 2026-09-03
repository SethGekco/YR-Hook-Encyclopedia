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
