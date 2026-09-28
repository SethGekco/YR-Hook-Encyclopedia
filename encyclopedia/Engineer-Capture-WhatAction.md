# Engineer Capture & `InfantryClass::WhatAction`

Where the engine decides that clicking a building with an engineer means
*capture* — and the places that decision can be diverted before it is reached.

Written up mid-investigation of a live symptom ("engineers cannot enter a
neutral `CAOILD` tech oil derrick"). **The cause was NOT found.** This page
exists so the next attempt starts from the map rather than from scratch, and
records what has already been eliminated.

---

## The decision, disassembled

`Action::Capture` is `9`, and it is returned from exactly one place on this
path: `0x51E6A5`.

```
51e564  mov  ecx,[edi+0x21c]     ; ENGINEER's owner house   (edi = engineer)
51e56a  push esi                 ; esi = target building
51e56b  call 0x4F9A90            ; allied test
51e570  test al,al
51e572  jne  0x51E5E8            ; ALLIED -> repair/grind arm, capture never considered

51e574  mov  ecx,[esi+0x21c]     ; building's owner house
51e57a  mov  edx,[ecx+0x34]      ; -> its HouseTypeClass
51e57d  mov  al,[edx+0x1a6]      ; HouseTypeClass bool
51e585  je   0x51E5A5
51e587  mov  eax,[esi+0x520]     ; BuildingTypeClass
51e58d  mov  cl,[eax+0x157b]     ; type bool
51e595  je   0x51E5A5
51e59b  call [edx+0x1d4]         ; virtual on the building
51e5a3  je   0x51E5E8            ; -> repair/grind arm

51e5a5  mov  eax,[esi+0x520]     ; BuildingTypeClass
51e5ab  mov  cl,[eax+0x1572]     ; ⚠ type bool — UNIDENTIFIED
51e5b3  je   0x51E668            ; clear -> capture never considered
51e5b9  mov  ecx,esi
51e5bb  call 0x5F5C60            ; building health ratio -> ST(0)
51e5c0  mov  ecx,ds:0x8871E0     ; RulesClass::Instance
51e5c6  fld  [ecx+0x17F8]        ; EngineerCaptureLevel
51e5cc  fcompp                   ; EngineerCaptureLevel vs health
51e5d0  test ah,0x1              ; C0 = (level < health)
51e5d3  je   0x51E6A5            ; health <= level -> Action::Capture (9)
51e5d9  mov  eax,0x1C            ; else          -> Action::Damage (28)
```

### `RulesClass +0x17F8` is `EngineerCaptureLevel`

Parsed at `0x671E10` from the string at VA `0x83B414`. It has **exactly one
reader in the whole binary**, `0x51E5C6`, i.e. the line above.

⚠ **Its constructor default is `1.0`** — `mov DWORD PTR [esi+0x17F8], 0x3F800000`
at `0x667793`. So a rulesmd that omits the key still captures at any health.
**Omitting `EngineerCaptureLevel` is not a cause of capture failure**, which is
the obvious first suspect and is wrong.

---

## The repair/grind arm, and the one third-party hook on it

Two of the branches above divert to `0x51E5E8`, which is the repair/grind arm:

```
51e5e8  mov  edx,[esi+0x520]
51e5ee  mov  al,[edx+0x16c1]     ; type bool
51e5f6  je   0x51E620
51e5fa  call 0x5F5C60            ; ENGINEER's health this time (ecx = edi)
51e604  fcomp [Rules+0x16F8]     ; a DOUBLE — ConditionYellow/Red, NOT
51e60f  je   0x51E620            ;   EngineerCaptureLevel, which is a float
51e614  mov  eax,0x3             ; Action::Enter

51e620  call 0x5F5C60            ; building health
51e62d  fcomp [Rules+0x16F8]
51e638  je   0x51E659            ; -> Action::GRepair (29)
51e63a  mov  edx,[esi+0x520]     ; ⚠ PHOBOS HOOKS HERE
51e643  mov  al,[edx+0x16ad]
51e64a  ...                      ; -> Action::NoGRepair (32) or Repair (11)
```

⚠ **Phobos seats `InfantryClass_WhatAction_Grinding_Engineer` at `0x51E63A`
(size 6)** and, for **any** `BuildingClass` target, overwrites the action and
short-circuits the rest of the function:

```cpp
if (const auto pBuilding = abstract_cast<BuildingClass*>(pTarget)) {
    const bool canBeGrinded = BuildingExt::CanGrindTechno(pBuilding, pThis);
    R->EBP(canBeGrinded ? Action::Repair : Action::NoGRepair);
    return 0x51F17E;            // skips everything after
}
```

So any engineer that reaches this arm against a non-grinder gets
`NoGRepair` — "nothing you can do here". This is the **only** third-party code
on the path and is the leading suspect, but it is **unproven**: nobody has
shown the engineer reaches `0x51E63A` rather than being turned away earlier at
`0x51E5B3`.

---

## Eliminated

| Suspect | Verdict | Evidence |
|---|---|---|
| Missing `EngineerCaptureLevel` in rulesmd | **Not it** | ctor default is `1.0` (`0x667793`) |
| Building's own tags | **Not it** | `Capturable=yes`, `NeedsEngineer=yes`, no `Immune=`; identical in a pre-mod backup |
| IntelExt | **Not it** | Probes at both capture seats (`0x519A1F`, `0x519F71`) logged zero for a whole match, so the engineer never reaches capture at all. Independently, IntelExt's engineer path is armed only by `Infiltrate.Effects.Source=` on the target, and the affected building has no such tag |
| Other third-party Ext DLLs | **Not it** | A sweep of every locally-built Ext DLL across `0x444000–0x457FFF` found hooks only in AcademyExt, CloningExt, FreeUnitExt and PrerequisiteExt, none on the action path |

---

## Open questions for the next attempt

1. **What is `BuildingTypeClass +0x1572`?** It gates the entire capture branch
   at `0x51E5B3`. Most likely `Capturable` or `NeedsEngineer`, but unconfirmed.
   Identify it by finding its parse site from the INI key string, the same way
   `EngineerCaptureLevel` was pinned to `+0x17F8` here.
2. **Does `0x4F9A90` report a neutral-house building as *allied*?** If so the
   engineer is diverted to the repair arm at `0x51E572` and capture is never
   evaluated — which would make the Phobos hook the proximate cause.
3. **Which branch is actually taken?** The decisive move is a read-only probe
   at `0x51E5A5` (`mov eax,[esi+0x520]`, 6 bytes, clean boundary, return 0)
   logging the building ID, the `0x4F9A90` result, the `+0x1572` bool and the
   health ratio. One match settles it. Guessing between these branches has
   already cost several test cycles.

## Related

* [Ext-Building-Occupancy.md](Ext-Building-Occupancy.md)
* [Spy-Infiltration.md](Spy-Infiltration.md) — the *spy* path, `0x4571E0`;
  engineers do **not** pass through it
