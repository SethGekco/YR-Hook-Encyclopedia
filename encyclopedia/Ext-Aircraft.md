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
