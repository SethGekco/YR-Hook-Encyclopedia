# Subsystem: Aircraft

Hooks in `AircraftClass` and aircraft rendering. Entries sorted by address.

---

### `0x4147F9` — AircraftClass::Draw (shadow branch)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `AircraftClass_Draw_Shadow` | 0x6 | `Hooks.MatrixOp.cpp` |
| Kratos | `AircraftClass_Draw_Shadow_SkipPhobos` | 0x6 | `Hooks/AircraftExtHook.cpp` |

**What it does.** This address sits at the point in `AircraftClass::Draw` where
the game is about to draw the aircraft's ground shadow. Phobos hooks it to run
its own **matrix-based** shadow rendering: it pulls the locomotor's shadow matrix
(`loco->Shadow_Matrix`) and applies height-based scaling driven by RulesExt
globals (`AirShadowBaseScale_log`, `HeightShadowScaling`, per-type
`ShadowSizeCharacteristicHeight`). So Phobos *replaces* the vanilla shadow draw
with a scaled, locomotor-aware one, and returns `0x4148A5` (past the whole shadow
block) when the aircraft should have no shadow.

**What it does *not* do — easily mistaken.**
- It is **not** a general "draw the aircraft" hook — it is specifically the
  *shadow* branch. The body sprite/voxel is drawn elsewhere.
- Hooking it does **not** by itself suppress the shadow. Vanilla still has its
  own shadow path after this point; to actually cancel a shadow you must return
  to the address *past* the whole shadow block, not just skip one framework's
  hook (see Kratos's two different return targets below).
- Phobos's presence here means a naive third hook at `0x4147F9` will **fight
  Phobos**, not vanilla.

**Used by / interactions — this is a real conflict, by design.** Both Phobos and
Kratos hook this exact address; it appears in `registry/conflicts.md`. This is
not the benign "everyone hooks the same call site" case — Kratos hooks it
*specifically to arbitrate Phobos*:

- Gated behind `AudioVisual::AllowTakeoverPhobosShadowMaker`. When **off**,
  Kratos returns `0` (fall through) and Phobos's shadow logic runs normally.
- When **on**, Kratos decides per-aircraft:
  - if the aircraft should have no shadow (`Type->NoShadow`, cloaked, sinking,
    or the locomotor reports no shadow) it returns **`0x4148A5`** — jumping
    clean past the *entire* shadow block, vanilla **and** Phobos.
  - otherwise it returns **`0x4147FF`**, which skips only Phobos's hook and lets
    the vanilla shadow draw proceed.

  So on a Kratos+Phobos build, load order and that one INI-driven flag decide
  whose shadow code wins. This is the canonical example of why the registry
  keys on address: the collision is invisible in a per-framework hook list and
  obvious the moment you group by address.

**Confirmed via.**
- Kratos behaviour: read directly from `Kratos/src/Hooks/AircraftExtHook.cpp`
  (the `return 0x4148A5;` / `return 0x4147FF;` branches and the
  `AllowTakeoverPhobosShadowMaker` gate). **Confirmed.**
- Phobos behaviour: read directly from cloned upstream
  `Phobos/src/Ext/TechnoType/Hooks.MatrixOp.cpp` (the `DEFINE_HOOK(0x4147F9, …)`
  body — matrix shadow, RulesExt scaling, and the `FinishDrawing = 0x4148A5`
  skip on cloak/sink/`NoShadow`/no-shadow-locomotor). **Confirmed.** Note Phobos
  and Kratos independently use the *same* skip conditions and the *same*
  `0x4148A5` exit, which cross-validates both.
- Return address `0x4148A5`: confirmed as the shadow-block exit by **both**
  Phobos and Kratos source. `0x4147FF` (skip-Phobos-only) is Kratos-specific and
  is the instruction right after the hooked bytes. Not re-derived from
  `gamemd.exe` disassembly here, but corroborated across two frameworks.

---

### `0x4157C0` — AircraftClass spy-plane / paradrop overfly  ⚠ five passes are hardcoded

Not a hook recommendation — a behavioural fact that reads as a bug and costs real
debugging time. Reported in game as **"the spy plane circles its target instead of
doing a flyby."**

**The mechanism.** The overfly mission (function start `0x4157C0`, ends `0x41595C`)
re-tests distance every tick rather than following a fixed trail:

```
415934:  mov ecx, ds:0x8871E0          ; RulesClass::Instance
41593a:  cmp eax, [ecx+0x54C]          ; distance vs [General]ParadropRadius
415940:  jg  0x415956                  ; too far -> keep flying
415942:  ...call [edx+0x1E8]...        ; in range -> do the pass
415950:  dec BYTE PTR [esi+0x6D3]      ; <-- passes remaining
415956:  mov eax,3 ; pop esi ; ret
```

`[esi+0x6D3]` is `AircraftClass::NumParadropsLeft` (`sizeof(FootClass)` is `0x6C0`;
the field sits at +0x13 into `AircraftClass`). **Exactly one site initialises it:**

```
0x413D74:  mov byte ptr [esi+0x6D3], 5     ; inside AircraftClass::AircraftClass (0x413D20)
```

So every aircraft is born with five passes, and a spy plane makes all five unless
something caps it. Five passes over one target is what looks like orbiting. The
flight path itself is fine — it simply repeats.

**The cap is a Phobos tag, on the WEAPON, not the aircraft.**
`CheckSpyPlaneCameraCount` (Phobos `Ext/Aircraft/Hooks.cpp`, hooks at `0x415666`
and `0x4157EB`) returns "no limit" when `Strafing.Shots` is unset, so a stock
configuration inherits the hardcoded 5:

```ini
[SpyCameraWeapon]      ; the aircraft's Primary, NOT the aircraft section
Strafing.Shots=1       ; one pass, then leave
```

✅ **Verified in game:** that single line turned persistent circling into a clean
flyby.

**Ruled out along the way, so nobody repeats it:**
- **Speed.** The plane's `Speed` had been doubled (15 → 30) with `ROT` left at 2 —
  a very plausible "wider turn radius" story. Reverting it changed nothing: speed
  alters how wide each loop is, not how many there are.
- **A third-party DLL.** Settled by uninjecting the suspect DLL entirely and
  observing identical behaviour, with its absence confirmed in the log.

**Confirmed via.** objdump of `gamemd.exe` at the cited addresses; a byte-pattern
search for writes to `+0x6D3` (exactly one — the constructor); Phobos source; and
an in-game before/after.
