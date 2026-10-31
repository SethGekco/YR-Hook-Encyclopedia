# Subsystem: pointer invalidation — what `0x7258D0` does *not* do

**Lead symptom:** a C0000005 on a pointer your code just null-checked. Either a
read at a small constant (`0x4`, `0x10` — i.e. `nullptr + offset`), or a vtable
call that lands in heap data.

`0x7258D0` (`AnnounceInvalidPointer`) is hooked by **Antares, Ares, Kratos and
Phobos** alike, so every YR extension DLL inherits its semantics. The useful
fact is the limit of those semantics:

> **It nulls the pointers you scrub in place. It removes nothing from your
> containers, and it knows nothing about objects you own yourself.**

Everything below follows from that one sentence.

---

## The two mirror-image failures

Both ✅ **VERIFIED** — each diagnosed from a full minidump in TechnoAttachmentExt.

| | **A. Live pointer → dead object** | **B. Live object → nulled member** |
|---|---|---|
| What dangles | your cached pointer to something you **own** | a member the announce **cleared** |
| Why the announce missed it | your object is not an `AbstractClass`, so nothing announces its death | it fired correctly; it just did not remove the entry from your vector |
| Guard that fails | `if (ptr)` — freed heap is not null | *(none written — the invariant was assumed)* |
| Symptom | garbage read as a pointer: ASCII text, bucket addresses | clean `nullptr + offset` read |
| Fix | a liveness registry; membership, not dereference | check the member at each use, or maintain the invariant |

**A** looked like this: an extension's child object held a raw back-pointer to a
slot owned by its *parent's* `vector<unique_ptr<…>>`. The slot's destructor
scrubbed that back-pointer only while its own `Child` was still set — and the
announce clears `Child` *first*. So that teardown order freed the slot and left
the pointer live. In one dump the recycled block read as the ASCII bytes
`"date"`; in another it had become `std::unordered_map` bucket storage, so a
vtable call jumped into container data.

**B** is the opposite, and the more surprising one, because the framework
behaved correctly: scrubbing a member leaves the **containing object in your
container**. Code that walks the container every frame then sees an entry whose
member is null. One such walker guarded a sibling field and used the nulled one
three times.

### The lesson that generalises

**Liveness cannot be tested by dereferencing.** `if (p)` answers "is this word
zero", which is not the question. Only membership in something authoritative —
your own registry, or `TechnoClass::Array` — answers it.

---

## Easily mistaken

* **A ref-counted smart pointer does not rescue an already-dead object.**
  `ILocomotionPtr` is a real `_COM_SMARTPTR_TYPEDEF` (`YRpp/Interfaces.h:317`),
  so it looks like the fix for a dangling COM pointer. Assigning into one calls
  **`AddRef()`** — a virtual call through the *same* vtable pointer that is
  already poisoned. The fault moves from the slot you were calling to slot
  `0x04` and reads as a brand-new bug. It guards a release *during* a call, and
  nothing else.
* **`Find()` is nullable twice over.** Phobos' `Container::TryFind()` null-checks
  the **key**; `Find()` checks nothing and returns null for any key **missing
  from the map**. The dangerous case is a valid object that was never
  registered, which `TryFind()` does not catch either. See
  [Cargo-KillCargo-Recursion](Cargo-KillCargo-Recursion.md).
* **Heap fill patterns are a hint, not a verdict.** `0xBAADF00D` (uninitialised
  allocation) and `0xABABABAB` (guard past the object) both turned up *inside* an
  object whose other fields were perfectly valid — `0xABABABAB` simply sat beyond
  its `0x1C`-byte extent. Don't conclude "unconstructed" from fill bytes alone.
* **A "parent" field that is nullable by design.** If your design lets the
  announce clear a host pointer, say so at the field, because every reader now
  needs a guard and the compiler will not ask for one.

---

## If you own objects whose lifetime the engine does not announce

Three options, cheapest first:

1. **A liveness set** — `static std::unordered_set<const T*>`, inserted in the
   constructor and erased in the destructor, with an `IsLive()` used by every
   reader. O(1), and it makes a stale pointer *detectable* rather than merely
   unlikely.
2. **Maintain the invariant** — remove the entry from the container when the
   member is cleared. Correct in principle, but you are inside engine teardown,
   so mutating a container another frame is walking is its own hazard.
3. **Guard at every use** — fine for a handful of sites; it does not scale, and
   it silently fails to cover the site added next month.

(1) + a mechanical check scales. In TechnoAttachmentExt a CI checker for case
**A** found **19** unguarded sites in one repo, and one for case **B** found
**6** — both after the specific crash had already been fixed. ⚠ Those counts are
that project's, not a general claim, but the ratio of "crashes reported" to
"sites exposed" is the point.

---

## Confirmed via

* **Three minidumps**, `snapshot-20260929-134629`, `snapshot-20260930-202005`
  and `snapshot-20261030-203952` — full memory; faulting objects read directly
  and fields matched against the headers.
* **Disassembly** of the extension DLL against its md5-matched `.map`, which
  named the fields unambiguously (`cmp [edi+8],0` as the guard that *was*
  written, `push [edi+4]` as the member that was not).
* **In-game** for all three crashes.
* Fixed in TechnoAttachmentExt `a109be7` (case A) and `8deb9ce` (case B).

## RE-VERIFY

* Whether `AnnounceInvalidPointer` **ordering** between an object's own
  invalidation and its container's teardown is deterministic is ⚠ **Unverified**.
  The case-A fix assumes it is not, and defends either order. If someone
  establishes the order, that fix could become narrower.
* Reading exception parameters from a minidump: `MINIDUMP_EXCEPTION`'s
  `ExceptionRecord`/`ExceptionAddress` are **ULONG64** and
  `ExceptionInformation[]` begins at **+0x28**, not +0x20. Parsing them as 32-bit
  makes `NumberParameters` read as `param[0]` and inverts READ/WRITE. Recorded
  here because it produced a confident, wrong answer once.
