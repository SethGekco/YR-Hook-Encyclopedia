# Syringe hook chaining — how a shared address silently loses a handler

Two DLLs hooking the **same** address is legal and normal: Syringe chains the
handlers. `registry/conflicts.md` and `tools/check_hook_overlap.py` both say so,
and both frame the danger as *overwrite* or *stolen-byte overlap*.

There is a third failure mode neither covers, and it is the quiet one.

---

## The mechanism

Syringe's chain is **return-value driven**:

| Handler returns | What happens |
|---|---|
| `0` | the next handler in the chain runs, then the stolen original instructions are replayed |
| non-zero | **jump to that address immediately** — remaining handlers never run, stolen instructions are never replayed |

So at a shared address, the first handler to return non-zero **truncates the
chain**. Everything downstream is silently skipped.

Nothing is malformed when this happens. Your bytes are correct, theirs are
correct, every bounds check and range-overlap check passes. There is no crash
and no module to blame — only behaviour that quietly stops working, on whatever
code path your handler decided to take over.

**This is the failure mode that the "move onto their exact address so you chain"
advice creates.** That advice is still right for fixing a range overlap; it just
hands you this problem next.

---

## Sharing an address is routine — it is the return that matters

Measured by intersecting `DEFINE_HOOK`/`DEFINE_JUMP` addresses across the three
extension sources (2026-10-16):

```
Kratos   456 hooks        Kratos  ∩ Antares : 108 shared addresses
Antares 1506 hooks        Kratos  ∩ Phobos  : 210
Phobos  1634 hooks        Antares ∩ Phobos  : 171
```

Ares and Phobos share **171** hook addresses and coexist cleanly — Phobos' own
position is that it "won't introduce incompatibilities" with Ares, and that
holds. So co-hooking an address is not the problem. Returning non-zero there is.

`DEFINE_JUMP` is worse: it never chains at all. A `DEFINE_JUMP` at an address
another framework hooks always removes their handler.

---

## Worked example — IntelExt vs Phobos ⚠ Unverified

Found by `scripts/check_hook_chain.py`, 2026-10-16. **Reasoned from source; the
in-game consequence has not been observed.**

`IntelExt/src/Ext/Techno/Hooks.AbilityReaders.cpp`:

```cpp
DEFINE_HOOK(0x6FDBE2, IntelExt_Firepower_Damage, 0x6)
{
    GET(TechnoClass* const, pThis, ESI);
    DWORD const target = Decide(pThis, Ability::Firepower, 0x6FDC42, 0x6FDC5A);
    if (!target)
        return 0;               // chain continues — Phobos runs
    R->EBP(R->ESI() + 0x150);
    R->Stack(0x1C, R->EAX());
    return target;              // jumps — Phobos never runs
}
```

Phobos hooks `0x6FDBE2` with `TechnoClass_FirepowerMultiplier`. So Phobos'
firepower multiplier should stop applying **exactly to units that have the
veteran Firepower ability**, and apply normally to everything else. Conditional,
silent, and invisible to every existing check.

Three more of the same shape:

| Address | IntelExt | Phobos handler lost |
|---|---|---|
| `0x6FDBE2` | `IntelExt_Firepower_Damage` | `TechnoClass_FirepowerMultiplier` |
| `0x6FE352` | `IntelExt_Firepower_Damage2` | `TechnoClass_FirepowerMultiplier` |
| `0x6FDC87` | `IntelExt_Stronger_Damage` | `TechnoClass_AdjustDamage_ArmorMultiplier` |
| `0x701966` | `IntelExt_Stronger_Damage2` | `TechnoClass_ReceiveDamage_ArmorMultiplier` |

`0x6FE352` is the same site named in `check_hook_overlap.py`'s own docstring: the
hook was moved onto Phobos' exact address to fix a range overlap, and the source
comment above it says *"THIS HOOK MUST STAY AT 0x6FE352 WITH SIZE 8"*. The
overlap fix was correct. It produced this.

Also found: `CommandBarExt` `0x6CFD08`
`ShapeButtonClass_FindIndex_NewButtons` returns `SkipDefaultIndex`, sharing with
Phobos.

---

## Prior art — Kratos designs around exactly this

KratosPP treats chain truncation as a first-class constraint:

- A design note records a first version hooking `0x424CB0` (Phobos' site) and
  realising it would have *"silently cut off Phobos' `Layer_UseObjectLayer`"*,
  so it moved to `0x424CCA`, chosen to overlap none of Ares/Phobos/Kratos.
- Its command-registration hook at `0x533066` **returns 0 unconditionally**,
  with the stated reason that Ares' and Phobos' commands must still register.
- Command IDs are partitioned so nobody collides: vanilla `0x00-0x2F`, CnCNet
  `0x30-0x3F`, Phobos `0x40-0x41`, Ares `0x60-0x61`, Kratos taking only
  `0x50-0x51`.
- Takeovers that are genuinely wanted are gated behind opt-in switches
  (`AllowTakeoverPhobosShadowMaker`, `AllowAnimDamageTakeOverByKratos`).

That last one is the pattern worth copying: make a takeover explicit and
switchable rather than implicit in a return value.

---

## The check

```bash
scripts/check_hook_chain.py registry/hooks.csv <repo>/src --project=<RepoName>
```

Flags every project hook that shares an exact address with another framework and
can return non-zero, plus any `DEFINE_JUMP` at a shared address. `--project`
excludes that framework's own registry rows so a catalogued repo does not match
itself.

A deliberate takeover is waived by annotating the return:

```cpp
if (ShouldOverride) return 0x6FE360;   // CHAIN-OK: replaces Phobos' handler
```

### What it does not cover

- **Load order.** It says a handler *can* break the chain, not whether yours runs
  before or after theirs. Syringe order depends on DLL load order, which this
  does not model.
- **Whether the takeover is wrong.** Sometimes you want to replace their
  handler. The tool asks you to say so out loud.
- **Reachability.** A non-zero return behind a condition that never fires is
  still reported; it cannot prove the branch is dead.
- **Indirect returns.** It classifies the return *expression*; a function that
  returns an address computed elsewhere reads as non-zero, which is the safe
  direction but may be noisy.
- **Non-`.cpp` hooks.** It scans `*.cpp` only, matching the other tools.

---

## Confirmed via

- **Chaining semantics** — KratosPP design notes (`docs/替身渲染层级与遮挡-2026-10-04.md`,
  `docs/快捷键附加AE-2026-10-05.md`), which state that a non-zero return jumps
  immediately and skips both the rest of the chain and the original-instruction
  replay. Third-party source reading, not independently executed here.
- **Address-sharing counts** — intersection of `DEFINE_HOOK`/`DEFINE_JUMP`
  address literals in the Kratos, Antares and Phobos source trees, 2026-10-16.
- **Kratos' non-interference design** — `src/Version.h` (`"Ares-like"`),
  `src/Utilities/*.h` (Ares BSD attribution), `docs/设计文档.md` §7, and the two
  design notes above.
- **IntelExt / CommandBarExt findings** — `scripts/check_hook_chain.py` against
  `registry/hooks.csv`, cross-read against the cited source lines. **⚠ The
  in-game effect was not observed** — no save was loaded and no damage number
  was compared.
