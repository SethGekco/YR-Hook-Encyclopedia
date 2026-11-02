# Target legality for scenery — trees, walls, and the disguise coupling

**Arrive here holding one of these symptoms:**

- "`TreeTargeting=yes` lets units that cannot scratch a tree shoot it forever."
- "I changed tree targeting and now Mirage Tanks will not disguise as trees."
- "I need the attack cursor over a tree to depend on the attacker."

One engine predicate answers all three, and the third symptom is the reason this
page exists: **the predicate that decides whether you may shoot a tree is the
same one a Mirage Tank asks before disguising as one.**

---

### `0x70EF00` — TechnoClass vtable `+0x398`, scenery target legality

**What it is.** `bool __thiscall(TechnoClass* this, AbstractClass* pTarget)`.
Given an attacker and a non-Techno target, it selects the weapon that would be
used and decides whether that target is addressable at all. Reconstructed from
`objdump`:

```
70ef00  push ebx; push esi; mov esi,ecx       ; esi = this
70ef04  push edi; mov edi,[esp+0x10]          ; edi = pTarget
70ef09  mov ebx,[esi]                         ; vtable
70ef0b  push edi;  call [ebx+0x2E4]           ; SelectWeapon(pTarget)  -> idx
70ef12  push eax;  call [ebx+0x3F8]           ; GetWeapon(idx)         -> WeaponStruct*
70ef1b  mov esi,[eax]                         ; esi = WeaponTypeClass*   (!! esi reused)
70ef1d  test esi,esi;  je 0x70efbc            ; no weapon -> FALSE
70ef25  call [vtable(edi)+0x2C]               ; pTarget->WhatAmI()
70ef2c  cmp eax,0x24                          ; AbstractType::Terrain (36) -- a TREE
70ef2f  jne 0x70ef53
70ef31  mov ecx,ds:0x8871E0                   ; RulesClass::Instance
70ef37  mov al,[ecx+0x17E9]                   ; TreeTargeting
70ef3d  test al,al;  jne 0x70ef4b             ; set -> TRUE
70ef41  mov al,[esi+0x138]                    ; else: weapon->TerrainFire
70ef47  test al,al;  je 0x70efbc              ; clear -> FALSE
70ef4b  mov al,1; ret 4                       ; TRUE
70ef53  mov al,[esi+0x138]                    ; non-Terrain arm ALSO requires TerrainFire
70ef59  test al,al;  je 0x70efbc
70ef5d  call [vtable(edi)+0x2C]               ; WhatAmI()
70ef64  cmp eax,0x0B                          ; AbstractType::Cell (11)
70ef69  mov eax,[edi+0x44]                    ; CellClass overlay type index
70ef71  mov ecx,ds:0xA83D84                   ; OverlayTypeClass array
70ef7a  mov al,[edx+0x2B5]                    ; overlay bool (wall-ish) -> TRUE
70ef8c  test [edi+0x14],2                     ; AbstractFlags bit 2
70ef9a  call [vtable(edi)+0xC4]               ; must be TRUE
70efaa  push 1; call [vtable(edi)+0xD0]       ; must return 0
70efb4  mov al,1; ret 4                       ; TRUE
70efbc  xor al,al; ret 4                      ; FALSE
```

**The slot is never overridden.** `0x70EF00` appears in all six TechnoClass-family
vtables — `0x7E263C`, `0x7E4254`, `0x7E902C`, `0x7EB3F0`, `0x7F4CF8`, `0x7F6008`
— each at `+0x398`. There is **no `E8` call site**: every caller goes through the
vtable, so searching for `call 0x70EF00` finds nothing and the function looks
dead. Search for `ff 9x 98 03 00 00` instead.

**YRpp labels the slot `CanDisguiseAs`.** That is one of its three uses, not all
of them; treat the name as a hint, not a description. Counting YRpp's
`TechnoClass.h` virtual list against two independent anchors (`SelectWeapon` at
`+0x2E4` and `GetTurretWeapon`/`GetWeapon` at `+0x3F4`/`+0x3F8`, which are 68 and
69 slots apart in both the header and the vtable) puts slot `+0x398` on
`CanDisguiseAs`, so the label is correctly *positioned* — it is just narrower
than the behaviour.

**⚠ The three callers, and why the third one matters.**

| Caller | Returns to | Identity |
|---|---|---|
| `0x7002EE` | `0x7002F4` | `TechnoClass::WhatAction` — cursor over an object |
| `0x700A4F` | `0x700A55` | `TechnoClass::GetActionOnCell` — cursor over a cell |
| `0x7466C0` | `0x7466C6` | `UnitClass::DisguiseAs` — **the trap** |

A **Mirage Tank asks this predicate whether it may disguise itself as a tree.**
Soften the Terrain arm to "only attackers that can hurt the tree may target it"
and you also take tree disguises away from every Mirage whose own gun is not
wood-capable. **In vanilla RA2/YR rules that is the Mirage Tank itself** —
`MGTK`'s `MirageGun` uses `MirageWH`, which has no `Wood=yes`. So this is not a
hypothetical coupling; a naive change breaks the signature unit of the feature
you were trying to improve.

If you need to change only the targeting answer, exclude the disguise caller by
its return address. At `0x70EF37` the frame is provable from the prologue — three
pushes, and both intervening calls are `ret 4` callees that clean their own
argument, which the engine itself confirms at `0x70EF05` by reading its parameter
from `[esp+0x10]` — so `[esp+0xC]` is the return address.

**Easily mistaken.**

- `[weapon+0x138]` is **`TerrainFire`**, not a tree-specific flag. The
  **non**-Terrain arm requires it too, so it is better read as "this weapon may
  address scenery at all".
- `esi` is the attacker on entry and the **WeaponTypeClass** from `0x70EF1B`
  onward. A handler seated after that point and reading `esi` as a `TechnoClass*`
  will dereference a weapon type.
- `0x70EFD0` is the **next function** (`IsUnderEMP`-shaped, reads `[ecx+0x504]`)
  and is already hooked by Kratos. `0x70EFE0` is `TechnoClass::GetMaxSpeed`,
  hooked by Phobos. `0x70EF00`–`0x70EFC1` is unclaimed as of this writing.

**Confirmed via.** `objdump` of `gamemd-spawn.exe` at `0x70EF00`; vtable slot
derived from six `dword` references cross-checked against `GetTurretWeapon`
(`0x70E1A0`) at `+0x3F4` in every one; call sites found by scanning for
`ff 9x 98 03 00 00`; caller identities from the YR Hook Encyclopedia registry
(`0x7002E9` Phobos `TechnoClass_WhatAction_PassableTerrain`, `0x700600` Antares
`TechnoClass_GetActionOnCell_Cursors`, `0x7466D8` Kratos/Phobos
`UnitClass_DisguiseAs`). The Mirage-breaks claim is **⚠ Unverified in game** —
it is a rules reading (`MirageWH` has no `Wood`) plus the call-graph above, and
it was designed around rather than observed.

---

### `0x7009C8` — the engine's own "can this warhead hurt this scenery" test

Inside `TechnoClass::GetActionOnCell` (`0x700600`), already written and already
reading the flags you were about to add:

```
7009c8  ecx = targetType
7009ca  al = [ecx+0x2A8]                ; ObjectTypeClass::LegalTarget
7009d0  test al,al; je FAIL
7009d4  al = [edi+0x144]                ; WarheadTypeClass::Wall
7009da  test al,al; jne PASS
7009de  al = [edi+0x147]                ; WarheadTypeClass::Wood
7009e4  test al,al; je FAIL
7009ea  cmp [eax+0x9C],6                ; ObjectTypeClass::Armor == Armor::Wood
7009f1  jne FAIL
7009f3  PASS
```

**Field offsets, all confirmed by name from the engine's own INI readers:**

| Offset | Field | Confirmed at |
|---|---|---|
| `WarheadTypeClass+0x144` | `Wall` | `0x75D4F4` pushes `"Wall"` |
| `WarheadTypeClass+0x147` | `Wood` | `0x75D549` pushes `"Wood"` |
| `WeaponTypeClass+0x138` | `TerrainFire` | `0x7721A3` pushes `"TerrainFire"` |
| `ObjectTypeClass+0x9C` | `Armor` | engine literal `6` == `Armor::Wood` |
| `ObjectTypeClass+0x2A8` | `LegalTarget` | ⚠ **Unverified** — inferred from YRpp member order, not from a reader |
| `RulesClass+0x17E9` | `TreeTargeting` | parsed at `0x66CF0F`; string at `0x83ACE8` |

**Easily mistaken — the `Wall` pass.** Vanilla serves walls and trees from this
one block, so a `Wall=yes` warhead passes it even against a tree. If you are
building "can this attacker hurt this *tree*", `Wall` is a false positive: a
wall-busting warhead does not fell a tree.

**Also mistaken — `Wood=yes` is not sufficient.** `Wood=yes` with `Verses` = 0%
against wood armour is a warhead the engine lets you target with and that still
cannot do a point of damage. `Wood` gates *legality*, `Verses` gates *effect*;
the complaint that sends people to this page is usually the second one.

**`TreeTargeting` lives in `[CombatDamage]`, not `[General]`.** Easy to get
wrong because it reads like a general presentation flag, and a tag parsed from
the wrong section is indistinguishable from a feature that does not work.

**Confirmed via.** `objdump` at `0x700990`–`0x700A60` and `0x75D53C`,
`0x7721A3`; `0x700600` identified as `GetActionOnCell` from the registry
(Antares hooks it at size 5 — **mind that claim if you seat at the entry**);
`Armor::Wood == 6` from YRpp `GeneralDefinitions.h` matching the engine literal.

---

## What is not covered here

- **Auto-acquisition.** None of the three callers is `GreatestThreat`, so this
  predicate is about the cursor and about ordered attacks, not about whether a
  tree is ever picked as a threat on its own.
- **Force fire.** `GetActionOnCell` short-circuits the capability block when its
  force flag is set (`[esp+0x38]` at `0x7009B4`), so force fire survives any
  tightening done at `0x70EF37`. The exact parameter that flag comes from is
  **⚠ Unverified**.
- **`ObjectTypeClass+0x2A8`.** Believed `LegalTarget` from member order only. If
  you depend on it, read it out of `ObjectTypeClass`'s INI reader first.
