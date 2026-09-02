# Spy Infiltration & Stolen Tech

Building infiltration by a spy, the effects it dispatches, and the stolen-tech
index model the Ares-lineage frameworks built on top of it.

---

### `0x4571E0` — BuildingClass::Infiltrate

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `BuildingClass_Infiltrate` | 0x5 | `src/Ext/Building/Hooks.Infiltrate.cpp` |
| Antares | `BuildingClass_Infiltrate_Standard` (`0x4574D2`, `0x457533`) | 0x6 | same |

**What it does.** Vanilla dispatches the hardcoded spy effects (power outage,
radar outage, credits steal, veterancy boost, reset build timer, …) according to
the victim building's type. Antares hooks the entry, runs its own
`BuildingExt::InfiltratedBy(pEnterer)` dispatch, and returns **`0x4575A2`** to
skip the vanilla body when its own handler consumed the event.

**What it does *not* do — easily mistaken.**

* **Engineers do not come through here.** Capture is a different code path
  entirely (`InfantryClass::UpdatePosition` multi-engineer handling around
  `0x519D9C`, then `BuildingClass::ChangeOwnership` — labels at `0x448312` /
  `0x448D95`). "Give an engineer spy-like effects" therefore cannot be done by
  making the engineer look like a spy; the effect dispatch has to be lifted out
  and called from both paths.
* **It is not a general "building was entered" event** — only infiltration.
* The two `_Standard` sites (`0x4574D2`, `0x457533`) exist because the *vanilla*
  effects do not repaint the sidebar; Antares forces `SidebarNeedsRepaint()`
  there. Anything that changes buildability from an infiltration needs the same
  repaint or the cameo state lags until the next unrelated repaint.

**Interactions — co-hooking is safe here, conditionally.** Syringe runs **every**
registered handler for an address; only the **first non-zero return** decides
control flow. A third-party DLL that hooks `0x4571E0` and always returns 0 will
run its own effects and then let Antares (or vanilla) decide the jump, in either
load order. The moment it wants to *suppress* the vanilla/Antares effects it must
return a jump target, and then load order decides the winner — a real conflict.

**Register / calling convention.** `ECX = BuildingClass*` (the building entered),
`[ESP+0x4] = HouseClass*` (the infiltrator's house).

**Confirmed via** Antares source (`develop`, `src/Ext/Building/Hooks.Infiltrate.cpp`)
and the PDB symbol map (`0x4571E0 BuildingClass_Infiltrate`). The co-hooking
claim above is no longer inference — see the runtime verification below.

---

## VERIFIED — co-hooking `0x4571E0` alongside Antares

The conditional-safety claim above was originally reasoned from Syringe's
documented behaviour. It has since been **confirmed at runtime**, which is worth
recording because the opposite assumption is very easy to reach and leads people
to hunt for a "post-infiltration seam" that is not needed.

**The tempting wrong conclusion.** Antares wraps the whole function and returns
`0x4575A2`. If Syringe *stopped* the chain at the first non-zero return, every
later-registered handler at this address would be dead code — silently, with no
handshake failure and no log line. That reasoning is wrong, but it is wrong in a
way that produces a confident-sounding "do not hook `0x4571E0`" conclusion.

**The evidence.** A third-party DLL (`IntelExt`) registers a handler at
`0x4571E0` that logs a line and returns `0`. In the deployed Linux setup the
Syringe inject list is ordered `-i=Antares.dll … -i=IntelExt.dll`, so **Antares
registers first and returns `0x4575A2`**. Its log line nevertheless appears in
real games:

```
[Phobos] [IntelExt] French infiltrated NATECH: ledger now tops out at index 130.
[Phobos] [IntelExt] French infiltrated GATECH: ledger now tops out at index 11.
```

8 occurrences across the `RA2/debug/debug.*.log` history.

**Therefore:** Syringe invokes **every** registered handler for an address. The
first non-zero return decides only where control ultimately transfers; it does
**not** prevent subsequent handlers from executing.

**Practical rule.** Co-hooking a fully-wrapped function entry is fine as an
*observer* — return `0` and you will run in either load order. It stops being
fine the moment you want to *suppress* the upstream effect, because then you must
return a jump target and load order decides the winner.

**⚠ This generalises beyond this address.** Any page claiming a chained hook
"never runs" because an incumbent returns a jump target is overstating the case.
Compare the wording at `0x4F7870` in
[Buildability-Prerequisites.md](Buildability-Prerequisites.md), which is right
that a second handler there cannot usefully *extend the verdict* (it would fight
over `EAX`, and Antares' `return` bypasses the vanilla body) — but a handler
there does still execute.

**Confirmed via** `RA2/debug/debug.*.log` from live games with Antares + Phobos +
several third-party DLLs co-loaded; the inject list in
`Resources/Compatibility/Unix/wine-game.sh` for registration order; IntelExt
source for the `return 0`. **Not** derived from Syringe's own source.

---

## Structural note — the stolen-tech index ceiling is 31, and it is a storage choice

Vanilla tracks only three flags: `HouseClass::Side0TechInfiltrated` /
`Side1` / `Side2`, consumed by `HouseClass::HasAllStolenTech` against
`TechnoTypeClass::RequiresStolenAlliedTech` / `…SovietTech` / `…ThirdTech`
(YRpp `HouseClass.h:625`).

The Ares-lineage frameworks generalise this to *indexed* stolen tech:

| | Storage | Ceiling |
|---|---|---|
| Antares — building grant | `BuildingTypeExt::StolenTechIndex`, a **`DWORD` bitfield** (`src/Ext/BuildingType/Body.cpp:230`) | index ≤ 31, logged as an error above that |
| Antares — house ledger | `HouseExt::StolenTech`, `std::bitset<32>` | 32 |
| Antares — requirement | `TechnoTypeExt::RequiredStolenTech`, `std::bitset<32>`, from `Prerequisite.StolenTechs=` | 32 |

Two things worth knowing before designing around this:

1. **The 32 ceiling is arbitrary** — it is the width of the chosen integer, not
   an engine constraint. Nothing in `gamemd.exe` knows what a "tech index" is;
   the whole system lives in framework ext data.
2. **A building may already grant several indices at once.** Antares parses
   `SpyEffect.StolenTechIndex=` as a *comma list*, OR-ing the bits
   (`Body.cpp:230-239`). The common belief that it is one index per building is
   wrong for Antares.

**Confirmed via** Antares source (`develop`) and YRpp headers. **Unverified:**
classic Ares' parser (not in the registry; the docs describe the same tag).

---

## The cost of `return 0` — effects ADD, they do not replace

The "co-hooking is safe, just return 0" result above has a consequence that is
easy to miss when *adding* an effect that a co-loaded framework already
implements: returning 0 buys compatibility by giving up exclusivity. Both
handlers run, so both effects happen.

The concrete case is the **money steal**. Antares' infiltration body takes
credits from the victim and gives them to the infiltrator
(`src/Ext/Building/Body.cpp:650-668`, driven by `SpyEffect.StolenMoneyAmount=`
or `SpyEffect.StolenMoneyPercentage=`). A third-party DLL that adds its own
money steal at `0x4571E0` and returns 0 does **not** override that — the victim
is robbed twice, once per handler, on a single infiltration.

The failure mode is nasty because it is quiet: no crash, no log, and in game it
reads as "my amount tag is wrong" rather than "two DLLs are both firing". The
symptom scales with the other framework's tag, so it also disappears the moment
you test on a building where only your own tag is set.

Rules that fall out of this, for any effect at this site:

* Adding an effect the other framework does **not** implement (stolen tech
  indices, limbo, gap vision) composes cleanly with `return 0`.
* Adding an effect it **does** implement means either (a) detect the other
  framework's INI keys at parse time and warn the modder to pick one family, or
  (b) return a jump target to suppress it and accept a load-order fight.
  Option (a) keeps `return 0` and is what IntelExt does.
* This generalises past money to every entry in the shared spy-effect set —
  power/radar outage, veterancy, superweapon reset.

## Randomness at this site is SYNCED — use `ScenarioClass::Random`

Infiltration effects run inside synced game logic on every client, and anything
they write (credits, veterancy, ledger state) is simulation state. A randomised
effect here must therefore draw from **`ScenarioClass::Random`** (YRpp
`ScenarioClass.h:137`), whose draw sequence is part of the sync stream, so every
client produces the same number.

Two traps:

* **`Randomizer::Global` (`0x886B88`) is the wrong generator.** YRpp's own
  comment in `Randomizer.h` says it is for RMG and other out-of-match
  randomness. Using it for an in-match effect desyncs.
* **Draw unconditionally.** Bailing out before the draw on a client-varying
  condition consumes a different number of draws per client, which desyncs just
  as thoroughly as using the wrong generator. Draw first, then clamp or discard.

This is the opposite of the rule for gap/vision code, which runs in an *unsynced
render* path and must hash rather than draw — see `Gap-Generator-Vision.md`.

**Confirmed via** YRpp headers, Antares source (`develop`), and IntelExt's
`SpyEffect.StolenMoney.*` implementation. **Unverified:** no deliberate
desync reproduction was run to prove the `Randomizer::Global` failure; the
claim rests on the generator's documented role and the sync-stream argument.

---

## Related

* `Gap-Generator-Vision.md` — the inverse randomness rule (render path → hash).
* `Buildability-Prerequisites.md` — where stolen tech is consumed
  (`HouseClass::CanBuild`, and the `0x4F8361` epilogue trap).
* `Veterancy-Abilities.md` — `TechnoClass::HasAbility`, the choke point for
  ability-based effects.
