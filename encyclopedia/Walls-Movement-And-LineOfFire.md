# Subsystem: Walls — movement blocking vs line-of-fire blocking

Two **completely separate** engine paths decide "can this cross a wall?" and
"can this shot pass a wall?". Conflating them is the first mistake anyone
makes here. Addresses for standard YR `gamemd.exe`, imagebase `0x400000`,
read with objdump 2026-10-16 (same binary provenance as
`Projectile-Scatter.md`).

## Vanilla decides this from the UNIT and PROJECTILE side, never the wall

| Question | Decided by | Not by |
|---|---|---|
| can this unit cross? | the **unit's** `MovementZone` (`InfantryDestroyer`, `CrusherAll`, …) and `Crusher`/`OmniCrusher` | the wall |
| does this shot stop? | the **projectile's** `BulletTypeClass::SubjectToWalls` | the wall |

`OverlayTypeClass` carries only `Wall` (bool) and `Strength`. There is no
vanilla way to say "*this* wall blocks vehicles but not infantry".

## ✅ `[General] AlliedWallTransparency` is REAL and WIRED UP

Often assumed vestigial. It is not.

- INI string at `.data 0x83B39C`, read once from `0x66D21C`, stored by
  `mov [esi+0x1850],al` at `0x66D22E` → **`RulesClass::AlliedWallTransparency`
  is at `+0x1850`**.
- Six byte-access sites: the CTOR default (`0x667825`), the INI read/store
  pair, and **three genuine reads** at `0x4CC45E`, `0x4CC627`, `0x4CC715`.
- Each read is followed by an alliance test against the wall's owning house:

```
4cc458  mov  ecx, ds:0x8871e0      ; RulesClass::Instance
4cc45e  mov  al,  [ecx+0x1850]     ; AlliedWallTransparency
4cc464  test al,  al
4cc466  je   0x4cc489              ; OFF -> ordinary wall blocking
4cc468  mov  edx, [esi+0x50]       ; cell's owner-house index
4cc46b  mov  eax, ds:0xa8022c      ; HouseClass::Array
4cc470  mov  ecx, [eax+edx*4]      ; -> the wall's owner HouseClass*
4cc47c  call 0x4f9a50              ; HouseClass::IsAlliedWith
```

So `AlliedWallTransparency=yes` genuinely means "allied walls do not block
allied units' shots". It is **global** (all walls), **projectile-only** (it
does not affect movement), and **house-relative**.

## The wall line-of-fire function: `~0x4CC400`–`0x4CC800`

The three `AlliedWallTransparency` reads live here, which makes this the
vanilla **shot-blocking** path — the place to extend if you want per-wall
projectile rules. Note the height compare just before the first read
(`cmp [ebp+0x11b], [ebx+0x11b]` / `jg`), i.e. firing from higher ground is
already part of this decision.

⚠ Unhooked by Phobos/Ares/Antares/Kratos. Phobos reimplements the equivalent
logic inside its own trajectories instead
(`Ext/Bullet/Trajectories/StraightTrajectory.cpp:586`,
`ParabolaTrajectory.cpp:1091`), where the pattern is worth copying because it
already resolves the specific wall:
`pBullet->Type->SubjectToWalls && pCell->OverlayTypeIndex != -1 &&
OverlayTypeClass::Array.GetItem(pCell->OverlayTypeIndex)->Wall`.

## The movement side is a DIFFERENT, and partly cached, mechanism

| Seat | Scope | Can express per-unit-type rules? |
|---|---|---|
| `CellClass::CheckPassability` — `0x483D8E` (Phobos, destroyable obstacle), `0x483D94` (Antares, firewall), `0x483DDF` (Phobos, passable terrain) | cell-level and **cached** — Antares names its hook `CellClass_UpdatePassability` | **No.** The cache cannot know which unit is asking. |
| `CellClass::IsClearToMove` — `0x4834E5` (Phobos) | cell-level | no |
| `InfantryClass::CanEnterCell` — `0x51C1F1` (Phobos, `_WallWeapon`), plus the UnitClass equivalent | **per-unit × per-cell** | **Yes** — this is the only correct seat for "blocks vehicles but not infantry" |
| `LocomotionClass::PassableCheck` — `0x4B3569` (Phobos PR#1616, CrusherAll) | per-locomotor | partly |

Structurally identical precedent to copy: Phobos's `IsDestroyableBlockage`
makes a *building* a pathfinding obstacle per unit capability.

⚠ This path is consulted constantly by the pathfinder and by the AI, and is
sync-critical. It is hotter and higher-risk than the projectile side.
