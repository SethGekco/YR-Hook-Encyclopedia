# Subsystem: Turrets — index selection, multi-turret art, voxel drawing

Covers *which* turret a techno shows (`CurrentTurretNumber`), how multi-turret
art is loaded, and the voxel turret/barrel draw path. Entries sorted by address.

**Orientation.** `TechnoClass::CurrentTurretNumber` (YRpp `TechnoClass.h:600`,
commented *"for IFV/gattling/charge turrets"*) picks the drawn turret voxel.
Vanilla only ever varies it for: gattling stage (`IsGattling`), charge-turret
animation frames (`IsChargeTurret` — the SREF pattern), and the IFV gunner
(`TechnoClass::SwitchGunner`). Anything else wanting to vary the turret must
write that field itself, and must **not** write it on gattling/charge types.

---

### `0x5F865F` / `0x5F887B` / `0x5F8084` / `0x5F8277` / `0x5F848C` — ObjectTypeClass::Load3DArt (turret & barrel art)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `ObjectTypeClass_Load3DArt_Turrets` | 0x6 | src/Ext/Techno/Hooks.Turrets.cpp |
| Antares | `ObjectTypeClass_Load3DArt_Barrels` | 0x6 | src/Ext/Techno/Hooks.Turrets.cpp |
| Antares | `ObjectTypeClass_UnloadTurretArt` | 0x6 | src/Ext/Techno/Hooks.Turrets.cpp |
| Antares | `ObjectTypeClass_Load3DArt_NoSpawnAlt1` / `_NoSpawnAlt2` | 0x7 / 0x6 | src/Ext/Techno/Hooks.Turrets.cpp |

**What it does.** Antares' multi-turret art loading: loads N turret and barrel
voxels (`ChargerTurrets[]` / `ChargerBarrels[]`) rather than the single vanilla
pair, and unloads them symmetrically. `Load3DArt_Turrets`/`_Barrels` names are
confirmed in the Antares PDB symbol map.

**What it does *not* do.** Loading the art does not make the game *select*
between the turrets — selection is `CurrentTurretNumber` (below). A mod can have
N turret voxels loaded and still only ever see turret 0.

**Confirmed via.** Encyclopedia registry (Antares release) + Antares PDB symbol
map for `0x5F865F` / `0x5F8084`.

---

### `0x6F9E50` — TechnoClass::Update

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_Update` | 0x5 | src/Ext/Techno/Hooks.cpp |
| Ares | `TechnoClass_Update` | 0x5 | src/Ext/Techno/Hooks.cpp |
| Kratos | `TechnoClass_Update` | 0x5 | src/Hooks/TechnoExtHook.cpp |
| Phobos | `TechnoClass_AI` | 0x5 | src/Ext/Techno/Hooks.cpp |

**What it does.** The per-frame techno update entry point. **This is the
canonical benign shared call site** — all four frameworks hook the *function
start* and all return 0, so they chain in load order with no arbitration. It is
the right home for any "recompute a per-frame derived value" logic, e.g.
Antares' `PassengerTurret` update (`CurrentTurretNumber = min(NumPassengers,
TurretCount-1)`).

**What it does *not* do — easily mistaken.** Being hooked by four frameworks does
**not** make it a conflict: nobody redirects control flow here. Contrast
`0x4147F9` (Ext-Aircraft.md) where Kratos deliberately arbitrates Phobos. Adding
a fifth hook here is safe *provided you return 0*.

**Register / calling convention.** Function start; `ECX` = `TechnoClass*`
(the prologue is `sub esp,0x68 / push ebx / push ebp / push esi / mov esi,ecx`).
The first five bytes `83 EC 68 53 55` are `sub esp,0x68` + `push ebx` +
`push ebp` — an exact 5-byte steal, which is why every framework uses `0x5`.

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` (prologue bytes above);
name confirmed in the Antares PDB symbol map; consumer list from the registry.
**Used successfully** by PayloadExt for a range-driven turret selector.

---

### `0x6FDDC0` — TechnoClass::FireAt (before the shot is truly fired)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TechnoClass_FireAt_BeforeTruelyFire` | 0x6 | src/Ext/Techno/Hooks.Firing.cpp |

**What it does.** A point inside `TechnoClass::FireAt`, after the weapon has been
resolved and before the projectile is actually created. Phobos uses it for its
delayed-fire feature and can redirect to `SkipFiring = 0x6FDE03`.

**Why it is useful.** It is the cheapest place to learn **which weapon index** is
being fired: `ESI` = `TechnoClass*`, `EBX` = `WeaponTypeClass*`, and the weapon
index is the stack arg at `[EBP+0xC]` (`GET_BASE(int, weaponIndex, 0xC)`).

**What it does *not* do — easily mistaken.** It is **not** the weapon *selection*
point — that is `TechnoClass::WhatWeaponShouldIUse` (`0x6F36DB` and friends).
Hooking here tells you what is being fired *now*; it does not let you observe the
turret/weapon a unit would pick while idle.

**Interactions.** Phobos hooks this exact address and may redirect. A second hook
that always returns 0 chains safely, but be aware Phobos can still skip the shot
afterwards — do not assume your hook running means the shot happened.

**Register / calling convention.** `ESI`=Techno, `EBX`=Weapon,
`[EBP+0xC]`=weapon index. The 6 stolen bytes are exactly
`mov al, [ebx+0x144]` (`8A 83 44 01 00 00`).

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` for the instruction
boundary; registers/stack offset from Phobos's own hook at the same address.
Not present in the (partial) Antares PDB map.

---

### `0x70DC70` — TechnoClass::SwitchGunner  ← the per-weapon turret mapping is applied HERE (and only here)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_SwitchGunner` | 0x6 | src/Ext/TechnoType/Hooks.Weapons.cpp |

**What it does.** Antares replaces the body to set both
`CurrentTurretNumber = *GetWeaponTurretIndex(index)` and
`CurrentWeaponNumber = index`, guarded by `if(!pType->IsChargeTurret)`.

**What it does *not* do — the important one.** This is the **only** place the
per-weapon turret mapping is applied, and the engine calls `SwitchGunner` on the
**gunner (IFV/passenger) path**. An ordinary vehicle with `Primary=`/`Secondary=`
never reaches it, so *its* turret never changes when it switches weapons — even
though `WeaponTurretIndex<N>=` is set and readable. Anyone wanting
"turret follows the firing weapon" on a normal vehicle must apply the mapping
themselves (e.g. from `0x6FDDC0`); the data is already there.

**Confirmed via.** Antares source read directly
(`src/Ext/TechnoType/Hooks.Weapons.cpp`); name confirmed in the Antares PDB map.

---

### `0x717890` / `0x7178B0` — TechnoTypeClass::Set/GetWeaponTurretIndex

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoTypeClass_SetWeaponTurretIndex` | 0x8 | src/Ext/TechnoType/Hooks.Weapons.cpp |
| Antares | `TechnoTypeClass_GetWeaponTurretIndex` | 0xB | src/Ext/TechnoType/Hooks.Weapons.cpp |

**What it does.** Accessors for the **per-weapon turret index**. `0x7178B0`
disassembles to:

```asm
mov eax, [esp+4]                 ; weapon index
mov eax, [ecx + eax*4 + 0x814]   ; array on TechnoTypeClass
retn 4
```

**Key fact — the array is VANILLA.** The storage lives at
`TechnoTypeClass + 0x814` in a stock `gamemd.exe`. Antares' hooks return early
for `index < TechnoTypeClass::MaxWeapons` (18) and only serve *overflow* weapon
indices from their own vector. Antares also supplies the INI surface
(`WeaponTurretIndex<N>=`, plus `<Name>TurretWeapon=`/`<Name>TurretIndex=` where
`<Name>` comes from the IFV list `Normal, Repair, MachineGun, Flak, Pistol,
Sniper, Shock, Explode, BrainBlast, RadCannon, Chrono, TerroristExplode, Cow,
Initiate, Virus, YuriPrime, Guardian`).

**What it does *not* do.** Reading the index does nothing on its own — see
`0x70DC70`. Also note it is a plain `__thiscall`, **not** a virtual, so it is
safe to call directly at its address from a third-party DLL (no R0-stub hazard).

**Confirmed via.** `objdump -d` of a clean `gamemd.exe` (bytes above); names from
the Antares PDB map; INI surface read from Antares `Ext/TechnoType/Body.cpp`.

---

### `0x73BA12` — UnitClass::DrawAsVXL — Phobos REPLACES the whole turret/barrel draw block

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `UnitClass_DrawAsVXL_RewriteTurretDrawing` | 0x6 | src/Ext/TechnoType/Hooks.MatrixOp.cpp |

**What it does.** Phobos rewrites voxel turret+barrel drawing wholesale and
returns `SkipGameCode = 0x73BEA4`, jumping past the **entire** vanilla block. It
rebuilds the matrices itself and picks the voxel via
`ChargerTurrets[currentTurretNumber]` (falling back to `TurretVoxel` when
`TurretCount <= 0 || IsGattling`), reading `currentTurretNumber` off the stack at
`STACK_OFFSET(0x1C4, -0x1A8)`.

**What it does *not* do — critical for anyone touching turret rendering.**
- On any Phobos build the **vanilla turret draw code never executes**. A hook
  that assumes it can tweak vanilla drawing here will do nothing.
- It does *not* implement per-section depth sorting: the turret is still drawn
  after the body, so **the body cannot occlude the turret at any HVA position**.
  Fixing that requires changing this rewrite (or superseding it), not adding a
  small additive hook.
- It reads `CurrentTurretNumber` rather than owning it — so third-party code that
  *sets* `CurrentTurretNumber` composes correctly with Phobos's drawing.

**Interactions.** Antares separately owns `UnitClass_DrawVXL_Turrets` (`0x73BD15`)
and `_Barrels1/2/3` (`0x73B90E`, `0x73BCCD`, `0x73BD6A`); Kratos hooks several
`UnitClass_DrawVoxel_TurretFacing` / `_HasChargeTurret` sites, and Phobos PR#1803
adds disguise-turret-facing hooks at overlapping addresses. This region is
**crowded** — check `registry/conflicts.md` before adding anything.

**Confirmed via.** Phobos source read directly (`Hooks.MatrixOp.cpp`, the
`SkipGameCode`/`getTurretVoxel`/`getBarrelVoxel` bodies). Draw-order claim is
from reading that rewrite, and is now corroborated by the blitter-flag survey
below.

---

### ★ Why a voxel body can never occlude its turret — the blitter flags settle it

**Source.** PayloadExt, 2026-09-25. `objdump` survey of every voxel blit in
`UnitClass::DrawAsVXL`. This is a NEGATIVE result, recorded deliberately: it
closes off the cheap fix that looks obviously available, and it is the reason the
"voxel body occludes turret" feature was shelved rather than attempted.

**Every voxel draw in the function pushes the same blitter flags — `0x2800`:**

```
73B69D  push $0x2800     ; body   (before Phobos's 0x73BA12 takeover point)
73B6F9  push $0x2800     ; body
73BCA0  push $0x2800     ; turret / barrel  (inside the block Phobos replaces)
73BCEE  push $0x2800
73BD47  push $0x2800
73BDDF  push $0x2800
73BE1E  push $0x2800
73BE76  push $0x2800
```

`0x2800` = `Alpha (0x800) | Flat (0x2000)`. **No `ZRead` (0x3000) and no
`ZReadWrite` (0x4000) appears anywhere in the function.**

**What that means.**
- Vanilla **never depth-tests voxel sub-objects against one another**. Body,
  turret and barrel are painted in a fixed order into the same surface, and
  whatever is painted last wins. The turret sits on top because it is drawn
  second, not because of any depth decision.
- So **turret-over-body is inherent to the vanilla renderer** — not a Phobos
  regression, and not a flag someone forgot to set.
- **Phobos is faithful here.** Its rewrite emits the same `Alpha | Flat`, so it
  neither introduced the behaviour nor can cheaply fix it.

**Why the obvious fix does not work — read this before trying it.** Setting the
turret draw to `ZRead` cannot help: it would test against a depth buffer the body
never wrote, because the body draw is `Flat` too. And switching *everything* to
`ZReadWrite` is not a small change either — these values **overlap bitwise**
(`ZRead` 0x3000 contains `Flat` 0x2000), which means they are **mode selectors,
not independent flags**. Changing the mode alters the blit for every voxel in the
game, shadows and translucency included, on the strength of a guess.

**What an actual fix would require**, in increasing order of cost:
1. **Facing-based ordering.** Draw the turret BEFORE the body when the turret is
   on the far side. Not true occlusion, but it is exactly the trick the engine
   already uses to order barrel vs turret, so it is idiomatic. Note the body is
   drawn *before* `0x73BA12`, so this needs a hook earlier in the function than
   Phobos's — you cannot get it from the existing takeover point.
2. **True per-voxel depth compositing.** Render body, turret and barrel through a
   shared depth-aware pass. Correct in all cases; a real renderer change in a
   region already carrying ~14 hooks across four frameworks.

**Confirmed via.** `objdump -D` of a clean `gamemd.exe`; all eight pushes read
directly. Flag arithmetic from the `BlitterFlags` enum. Not in-game tested,
because the conclusion is that there is nothing to test.

---

## Practical recipe: "make the turret change for reason X"

1. Decide the selector (weapon fired, target distance, veterancy, …).
2. Write `CurrentTurretNumber` from a hook that has the data —
   `0x6FDDC0` (weapon index) or `0x6F9E50` (per-frame state).
3. **Guard**: skip when `TurretCount <= 0`, and skip when
   `IsGattling || IsChargeTurret` (the engine owns the field on those).
4. **Clamp** to `TurretCount` — an out-of-range value indexes past
   `ChargerTurrets[]` during drawing.
5. Drawing then follows automatically, including under Phobos's rewrite.

*Recipe derived while implementing PayloadExt's turret selectors; steps 3–4 are
reasoned from the source above and are **not yet in-game verified**.*
