# Subsystem: cargo teardown, and why `KillCargo` seats are not Techno-only

**Lead symptom:** a C0000005 reading a small constant address — `0x10`, `0x4`,
`0x8` — inside your own extension code, shortly after a *building* dies. The
faulting value is `nullptr + <member offset>`: an ExtMap lookup missed and the
result was used anyway.

**The cause is almost never a bad pointer.** It is a *correct* pointer to an
object of a type you did not expect, which is therefore absent from your map.

---

## The recursion that makes this happen

`TechnoClass::KillCargo` @ **`0x707CB0`** empties a transport by detaching one
passenger at a time and **calling itself on each one**:

```asm
707cb0  push ebx
707cb1  mov  ebx,ecx            ; ebx = this   (so EBX at 0x707CB3 IS `this`)
707cb3  mov  eax,[ebx+0x118]    ; <- the usual 6-byte seat
707cbb  je   0x707d1c           ; no cargo -> out
707cc4  lea  edi,[ebx+0x114]    ; &this->Passengers  (CargoClass)
707ce7  call 0x473430           ; CargoClass::RemoveFirstPassenger
707cec  mov  esi,eax
707cf0  je   0x707d0f           ; null -> out
707cf5  call 0x707cb0           ; *** RECURSE on the passenger
```

A cargo list holds `ObjectClass*`, **not** `TechnoClass*`. So the recursive call
can hand your seat any object that ended up in a passenger list. ✅ **VERIFIED**
— a `TerrainClass` (a tree) in a *building's* passenger list did exactly this
(`WhatAmI` = 36, object size 224 bytes; a `UnitClass` is 2280, so the AbsID and
the size agree independently).

**So `GET(TechnoClass*, pThis, EBX)` at `0x707CB3` is wrong.** The *register* is
right; the *type* is assumed. Use `GET(ObjectClass*, …)` and `abstract_cast`.

### The second seat, which is easy to miss

`0x5F6609` is object teardown and feeds the same function:

```asm
5F6603  test byte [esi+0x14],1   ; an ObjectClass FLAG -- not a type check
5F6607  je   5F6612
5F6609  push 0                   ; <- the 9-byte seat
5F660B  mov  ecx,esi
5F660D  call 0x707CB0            ; TechnoClass::KillCargo
5F6612  mov  dl,1
5F6616  call 0x7258D0            ; AnnounceInvalidPointer
```

Every `ObjectClass` reaches this, and the only gate ahead of the seat is a flag.
Anyone hooking `0x5F6609` to "notify on techno destruction" has the same bug.
Phobos' own name for its PR#352 seat here keeps the distinction —
`ObjectClass_RemoveThis_TechnoClass_NotifyParent` — which is worth copying.

---

## Easily mistaken

* **`0x707CF2` looks patched and is not a bug.** Live byte `55` (`push ebp`) vs
  disk `56` (`push esi`), with no Syringe stub. That is Phobos'
  `DEFINE_PATCH(0x707CF2, 0x55)` from `Misc/Hooks.BugFixes.cpp` — *"Fixes
  recursive passenger kills not being accredited to proper techno but to their
  transports"*. Don't chase it.
* **`Find()` vs `TryFind()` (Phobos `Container`).** `TryFind()` null-checks the
  **key**. `Find()` checks nothing and returns null for any key **missing from
  the map**. The dangerous case is a valid object that was never registered, so
  `TryFind()` does **not** help — only a null test on the **result** does.
* **Reading arguments from `[ebp+0x8]` on an optimised build.** A callee may
  recycle an argument slot. One analysis of this crash reported "`pThis` was
  NULL" after reading `[ebp+0x8]`; the real value was in the Syringe stub's
  `pushad` block, and the slot had been reused to hold `CurrentMission` (0 =
  `Mission::Sleep`). Read registers from the stub snapshot, not argument slots.

---

## Anchoring frames on a Syringe stub

The `pushad` block is self-checking, which is what makes this diagnosable:

```
origin     slot = the hooked address itself     ✓
pushed esp slot = the address of the origin slot ✓
EBX        slot = `this` as the hook read it
```

Then cross-check against the code: in this case `EDI − outerEBX = 0x114`,
exactly the `CargoClass` offset that `0x707CC4: lea edi,[ebx+0x114]` computes.
Three agreeing values mean a live chain rather than same-tick residue.

---

## Still open — not an engine question

**Why a `TerrainClass` is in a building's passenger list at all** is unexplained.
Type guards turn the crash into a no-op without addressing it. Unproven leads:
PayloadExt (synthesises occupiers), MirageTreesExt (units and trees), and
Phobos' `CargoClass::Attach` hook at `0x4733BD`.

---

## Confirmed via

* **Minidump**, `snapshot-20261019-224522` — full memory; faulting object read
  by vtable slot (`WhatAmI` is `+0x2C`, `Size` is `+0x30`; **both** are
  `mov eax,imm32; ret`, so a "first constant-returning thunk" scan silently
  returns `Size` and lies).
* **Disassembly** of `gamemd-spawn.exe` for `0x5F65F0..0x5F661B` and
  `0x707CB0..0x707CF5`; call targets resolved from their rel32 displacements.
* **In-game**: the crash itself, on TechnoAttachmentExt commit `a109be7`.
* Fixed in TechnoAttachmentExt `13a14b1`, which also adds
  `tools/check_ext_find_guard.py` — a CI check for `Find()` results dereferenced
  without a null test. It found **19** further unguarded sites in that one repo,
  so this is a category worth checking mechanically rather than by eye.

## RE-VERIFY

The `[esi+0x14] & 1` gate at `0x5F6603` is **⚠ Unverified** as to meaning — it is
read here only as "an ObjectClass flag, not a type discriminator", which is
enough to establish that the seat is not Techno-only. If you need to know which
objects actually reach `0x5F6609`, identify that bit first.
