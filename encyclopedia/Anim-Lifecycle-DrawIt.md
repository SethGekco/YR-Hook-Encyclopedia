# Subsystem: Anim lifecycle & `AnimClass::DrawIt`

Where an `AnimClass` is constructed/destroyed, and the map of every known seat
inside `AnimClass::DrawIt` — including which ones **always return non-zero**
and so may starve a same-address co-hook. Addresses for standard YR
`gamemd.exe`, imagebase `0x400000`.

**Provenance:** hook rows from `registry/hooks.csv`; handler bodies, registers
and return values from Phobos `develop` as read 2026-09-25
(`src/Ext/Anim/Body.cpp`, `src/Ext/Anim/Hooks.cpp`). YRpp `AnimClass.h` /
`StageClass.h` (commit `3ba9495`) for fields. **Not independently
disassembled.**

## Construction / destruction

| Address | Size | Owner(s) | Registers | Returns |
|---|---|---|---|---|
| `0x421EA0` | 0x6 | Phobos `AnimClass_CTOR_SetContext` | caller return address at `[esp]`, `CoordStruct*` at `[esp+0x8]` | 0 |
| `0x421EF4` / `0x42276D` | 0x6 | Phobos `AnimClass_CTOR_ClearD0` | ESI = anim | `R->Origin() + 6` (skips its own stolen bytes) |
| `0x422126` | 0x5 | Phobos `AnimClass_CTOR_NullType`, Kratos | — | 0 (logs a null-Type creation) |
| `0x4226F6` | 0x6 | Phobos `AnimClass_CTOR` | ESI = anim; **`Type` is already set** (Phobos reads `pItem->Type` here) | 0 |
| `0x422707`, `0x4228D2` | 0x5 | Kratos `AnimClass_CTOR` | — | — |
| `0x422967` | 0x6 | Phobos + Kratos `AnimClass_DTOR` | ESI = anim | 0 |

## `AnimClass::DrawIt` seat map

| Address | Size | Owner(s) | Registers / stack | Returns |
|---|---|---|---|---|
| `0x422C70` | 0x6 | Phobos PR#1969 `DrawIfVisible_DontDrawIfOwnerInLimbo` | — | (PR, unmerged) |
| `0x422CD8` | 0x6 | Phobos `AnimClass_DrawIt_DrawOffset` (`DEFINE_HOOK_AGAIN`) | ESI = anim, `Point2D*` screen location at `STACK_OFFSET(0x110, 0x4)` = `[esp+0x114]` | **always 0** |
| `0x422FCC` | 0x5 | Antares / Ares / CnCNet-Spawner `AnimClass_Draw_Details` (perf) | — | — |
| `0x423061` | 0x6 | Phobos `AnimClass_DrawIt_Visibility` | ESI = anim | 0, or `SkipDrawing` = `0x4238A3` |
| `0x423122` | 0x6 | Phobos `AnimClass_DrawIt_DrawOffset` (same handler as `0x422CD8`) | as `0x422CD8` | **always 0** |
| `0x42312A`, `0x423136` | 0x6 | Kratos `AnimClass_Draw_Remap(2)` | — | — |
| `0x423183` | 0x6 | Phobos `AnimClass_DrawIt_Translucency` | ESI = anim, **EBX = `BlitterFlags`** | `SkipGameCode` = `0x4230FE`, or `ReturnFromFunction` = `0x4238A3` when translucency > 15 |
| `0x4232BF` | 0x6 | Phobos `AnimClass_DrawIt_MakeInfantry` | — | — |
| `0x4232CE` | 0x6 | Antares / Ares `AnimClass_Draw_SetPalette` | — | palette chosen here |
| `0x4232E2` | 0x6 | Phobos `AnimClass_DrawIt_AltPalette` | ESI = anim | **always** `SkipGameCode` = `0x4232EA` |
| `0x423365` | 0x8 | Phobos `AnimClass_DrawIt_ExtraShadow` | ESI = anim | **always non-zero**: `DrawExtraShadow` = `0x42336D` / `SkipExtraShadow` = `0x4233EE` |
| `0x423420` | 0x6 | Phobos `AnimClass_Draw_TintColor` | — | — |
| `0x423630` | 0x6 | Kratos `AnimClass_Draw_Colour` | — | — |
| `0x423654` / `0x423660` / `0x4236F0` | 0x5/0x5/0x6 | Phobos `DrawIt_Tiled_Interval` / `_Center` / `_Palette` | tiled path; `0x423654`: EAX = `RectangleStruct*` bounds, EDI = `const int*` | — |
| `0x423855` | 0x7 | Phobos `AnimClass_DrawIt_ShadowLocation` | ESI = anim, EDI = `Point2D*` | **always** `SkipGameCode` = `0x42385D` |

`0x4238A3` is the function's exit (both `SkipDrawing` and `ReturnFromFunction`
jump there).

**Where the main SHP is drawn (unverified).** The palette is final after
`0x4232E2`→`0x4232EA`, and the extra-shadow branch starts at `0x423365`. The
main shape-draw call should lie between `0x4232EA` and `0x423365`, and the
shadow draw after `0x42385D`. Neither call has been located in a disassembly.

## What it does *not* do — easily mistaken

- **DrawIt has two entry paths into the offset seat.** `0x422CD8` and
  `0x423122` share one Phobos handler. A probe on only one of them misses
  every anim that takes the other path.
- **You can't make an anim draw bigger with blitter flags or palette seats.**
  The engine's SHP blit is 1:1. Scaling means replacing the shape-draw call
  itself: draw 1:1 to a scratch surface, then stretch onto the target, and
  grow the anim's redraw/dirty bounds or large frames clip and trail. No
  public framework does this (as of 2026-09-25).
- **Several seats here starve co-hooks** (always non-zero: `0x423183`,
  `0x4232E2`, `0x423365`, `0x423855`). Whether a non-zero return stops *later*
  same-address handlers is unresolved — see `Syringe-Stub-Semantics.md`.
  Co-hook the always-0 `0x422CD8` / `0x423122` / `0x4226F6` / `0x422967`
  instead where possible.
- **Anims are not linked back to the warhead or bullet that made them.** A
  bullet's damage anim is chosen at `0x469C46` (EBX) and created right after
  (see `Bullet-Detonate-DamageArea.md`). To tag the resulting anim, hand the
  data across in a one-shot slot that the next `AnimClass_CTOR` (`0x4226F6`,
  `Type` already set) consumes only if `Type` matches and it's the same frame.
- For draw **order** (anims drawing over units, Y-sort) see
  `Render-Layers-YSort.md`. This page is only about *how* one anim is drawn.

## Used by / interactions

- Phobos owns the bulk of `DrawIt`; Kratos adds remap/colour; Antares/Ares/
  CnCNet-Spawner share `0x422FCC` and `0x4232CE`.
- Incidental consumer: the private WeaponExt DLL co-hooks `0x4226F6`,
  `0x422967` and a read-only probe on `0x422CD8` + `0x423122` (logging the
  first draws of tagged anims). CI overlap/bounds checks pass. **No in-game
  confirmation yet.**

## ⚠ The iteration countdown in `AnimClass::AI` — the fall-through is a RESTART

**VERIFIED (2026-11-08, IntelExt)**, the hard way: a feature that wanted to hold
an anim on its last frame seated here and wrote the engine's infinite marker, and
the result was anims that **looped forever**.

```
424740  test dl,dl
...
42475a  test cl,cl
42475c  je  0x42476b
42475e  cmp cl,0xff            ; the infinite marker -- skips the decrement
424761  je  0x42476b
424763  dec cl
424765  mov [esi+0x195],cl     ; AnimClass::RemainingIterations
42476b  mov al,[esi+0x195]
424771  test al,al
424773  mov eax,[esi+0xc8]     ; pAnim->Type
424779  je  0x4247f3           ; ZERO -> Done
; ---------------- fall-through: iterations REMAIN, so RESTART ----------------
42477b  mov cl,[eax+0x371]     ; an AnimTypeClass flag
424781  test cl,cl
424783  jne 0x4247a5
424785  mov cl,[esi+0x120]     ; AnimClass::Reverse
42478b  test cl,cl
42478d  jne 0x4247a5
42478f  mov ecx,[eax+0x2b8]
424795  mov edx,[eax+0x2b4]
42479b  sub ecx,edx
42479d  mov [esi+0xac],ecx     ; Animation.Value = loop start
4247a3  jmp 0x4247b1
4247a5  mov edx,[eax+0x2bc]
4247ab  mov [esi+0xac],edx     ; Animation.Value = loop start
4247b1  ...continues
```

**The trap.** `test al,al` being non-zero does **not** mean "this anim is held".
It means "this anim has iterations left", and the engine's very next act is to
**reset `Animation.Value`** to the loop start. So writing `0xFF` into
`RemainingIterations` at `0x42476B` does not freeze an anim — it converts a
finite anim into an **infinite loop**, and any frame the handler writes is
overwritten a few instructions later, every iteration, forever.

This is a textbook case of checking which branch you avoid without checking
where the fall-through goes (trap 9's neighbourhood, and trap 10's lesson).

**`Paused` is not consulted anywhere on this path.** `AnimClass +0x120` is
**`Reverse`**, not `Paused` — YRpp's `PROTECTED_PROPERTY(BYTE, padding_121[0x7])`
immediately after `Reverse` is what names the offset. Pausing therefore cannot
rescue a handler seated here.

### What works instead: pause before the iteration completes

A paused anim does not advance, so it never completes an iteration, so the
engine reaches **neither** the restart nor `Done` — and consequently never frees
it either, so expiry has to be the mod's own job. This needs **no seat at all**:
poll `AnimClass::Array` from a post-logic tick and freeze the anim when
`Animation.Value` reaches its final frame.

⚠ Use **`AnimClass::Pause()` / `Unpause()`**, never the `Paused` bool. `Pause()`
also *clears* `Unpaused` (a separate field the engine uses to notice a resume)
and copies `Animation.Value` into `PausedAnimFrame`, so assign the frame
**before** calling it. Same family as
[Techno-Deactivation-Power.md](Techno-Deactivation-Power.md): a field the engine
maintains through a function is the function's business.

### Field offsets

| offset | field |
|---|---|
| `AnimClass +0xAC` | `Animation.Value` (the `StageClass` stage) |
| `AnimClass +0xC8` | `Type` |
| `AnimClass +0x120` | `Reverse` |
| `AnimClass +0x195` | `RemainingIterations` (`0xFF` = infinite; the decrement at `0x424763` is explicitly skipped for it) |
| `AnimTypeClass +0x2B4` / `+0x2B8` / `+0x2BC` | the loop-start sources read above |
| `AnimTypeClass +0x371` | flag selecting which loop-start source is used |

### Neighbouring claims

`0x4247F3` is the Done branch (Kratos independently named it `AnimClass_Done`);
Kratos also holds `0x424785` (`AnimClass_Loop`) and `0x4247EB`, and Phobos holds
`0x424807`. `0x42476B`–`0x424770` was unclaimed, and **is now unused by IntelExt
as well** — the seat was removed rather than re-pointed.

---

## RE-VERIFY

- [ ] Locate the main SHP draw call between `0x4232EA` and `0x423365`: address,
      argument layout (surface, SHP, frame, point, bounds, flags, Z,
      ConvertClass), stolen bytes.
- [ ] Locate the shadow draw after `0x42385D`.
- [ ] Find where DrawIt's redraw / dirty rectangle comes from (it must grow
      for a scaled draw).
- [ ] Confirm which DrawIt path (`0x422CD8` vs `0x423122`) ordinary warhead
      explosion anims take.
