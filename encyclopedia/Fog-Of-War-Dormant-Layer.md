# Fog of War — the dormant Tiberian Sun layer in YR

**Summary.** Yuri's Revenge still contains Tiberian Sun's fog-of-war system:
per-cell fog verbs, a per-cell fogged-object snapshot list, a foggedness byte
indexing `fog.shp`, regrow rates, and **three separate `FogOfWar` toggles** that
are real vanilla INI tags. RA2/YR ship with it switched off.

**But it is switched off because it is broken, not merely unused.** Turning the
tag on does not get you working fog — see the warning section below before
planning any work here. The state layer is fine; the renderer is what fails.

Read this page in both directions: "add fog of war" is not a from-scratch
project (the machinery exists), and it is also not a small one (making the rest
of the renderer respect it has defeated three attempts).

---

## The toggles — `FogOfWar` is a vanilla tag, in three places

| Field | Header | Read at |
|---|---|---|
| `RulesClass::FogOfWar` | `RulesClass.h:798` | `0x6721E7` |
| `GameModeOptionsClass::FogOfWar` | `GameModeOptionsClass.h:40` | `0x6B8C1B`, `0x6B8E6F` |
| `ScenarioClass::FogOfWar : 1` | `ScenarioClass.h:39` | — (scenario bitfield) |

Three levels — rules default, per-session game option, per-scenario bit — which
is the same shape as other TS-era session options (`Shroud`, `Crates`,
`ShortGame`). A *map* can therefore demand fog independently of the rules
default. The registry lists `FogOfWar` as scope `map|ra2|rules|ts`, consistent
with that.

Related vanilla tags, all already parsed:

| Tag | Field | Read at |
|---|---|---|
| `FogRate` | `RulesClass::FogRate` (double) | `0x66B4D7` |
| `ShroudRate` | `RulesClass::ShroudRate` (double) | — |
| `ShroudGrow` | `RulesClass.h:913` (bool) | — |
| `BlendedFog` | `RulesClass::BlendedFog` | `0x670F09` |
| `AircraftFogReveal` | `RulesClass::AircraftFogReveal` (int) | `0x66EB2F` |
| `ShouldFogRemove` | art-side | `0x4282CB` |

## The per-cell machinery

| Member / method | Address | Note |
|---|---|---|
| `CellClass::FogCell()` | `0x486A70` | fog a single cell |
| `CellClass::CleanFog()` | `0x486BF0` | |
| `CellClass::IsFogged()` | `0x4879B0` | |
| `CellClass::ClearFoggedObjects()` | `0x486C50` | |
| `CellClass::FoggedObjects` | — | `DynamicVectorClass<FoggedObjectClass*>` |
| `CellClass::Foggedness` | — | `char`: `-2` occluded, `-1` visible, `0..48` frame in `fog.shp` |
| `DisplayClass::RevealFogShroud` | virtual | takes `(CellStruct*, HouseClass*, bool)` |
| `DisplayClass::MapCellFoggedness` | virtual | |

**`FoggedObjectClass` is the interesting one.** It is the mechanism behind the
behaviour people actually want from fog: a fogged cell keeps a *snapshot* of the
objects that were in it, and the snapshot is drawn while the live object is
hidden. That is what produces "you can still see the building you scouted, but
it does not update until you re-sight it" — buildings frozen at their last known
state rather than vanishing. A mod does not need to implement that; it needs to
re-enable it.

Note YRpp only **forward-declares** `FoggedObjectClass` (`CellClass.h:22`); there
is no wrapper header. Anything driving it directly needs the layout reverse
engineered first.

## Frameworks already touch the fog path

* Antares' `MapRevealer` (`src/Misc/MapRevealer.cpp`) threads a `bool fog`
  parameter through `Reveal0`/`Reveal1`/`Process0`/`Process1`/`UpdateShroud`,
  and calls `MouseClass::MapCellFoggedness` and `RevealFogShroud`. So the reveal
  path is fog-aware in a maintained reimplementation, not just in the binary.
* Phobos reads `CellClass::IsFogged()` (`src/Misc/FlyingStrings.cpp:12`) and
  manipulates `AltCellFlags::Mapped | NoFog` (`Hooks.BugFixes.cpp:3452, 3474`).

## `AltCellFlags` — the explored/fogged bits

```
Mapped = 0x8      // this cell has been explored
NoFog  = 0x10
Clear  = Mapped | NoFog
```

`Mapped` is the "has been explored" bit, and it is the difference between the
two kinds of concealment mods usually conflate:

* Concealment that **forces re-discovery** — the cell loses `Mapped`, so it
  stays black until something reveals it again. This is what gap generators do.
* Concealment that **restores itself** — `Mapped` is preserved, so the area
  comes back when the source goes away.

Anything implementing "temporary shroud" is really choosing whether to preserve
`Mapped`, not writing a new visibility state. Preserving it across a field's
lifetime wants a *snapshot* rather than a read-at-the-end, because a cell can be
legitimately explored while concealed.

---

## ⚠ The layer exists but is BROKEN in YR — do not budget it as a small job

The toggles and the per-cell machinery above are real. **The fog layer as
shipped in YR does not work correctly**, and the reason is not the fog state —
it is that the rest of the renderer does not respect it.

The authoritative bug list is Phobos issue
[#28](https://github.com/Phobos-developers/Phobos/issues/28), *"[bounty: 150$]
Fix vanilla YR Fog of War bugs & issues"* — **open since 2020-12-28**, with a
cash bounty on it, still open. Its opening line is the summary of this whole
page: *fog of war exists in YR's code but was disabled because it does not work
correctly.*

Attempts to fix it, none merged:

| PR | Title | Outcome |
|---|---|---|
| [#122](https://github.com/Phobos-developers/Phobos/pull/122) | "Refactor the FogOfWar feature in YR" (Mar 2021) — *"Fog in YR looks performance really stupid"* | **closed unmerged**, Feb 2022 |
| #530 | earlier fog attempt | closed, later picked up |
| [#1872](https://github.com/Phobos-developers/Phobos/pull/1872) | "Refactor Fog of War round 2" (Sep 2025) | **open draft**, +3275/−52 across **31 files** |
| [#2229](https://github.com/Phobos-developers/Phobos/pull/2229) | "Fix flying strings drawing through Fog of War" (May 2026) | **open draft** — 2 files, +16/−13, *"a narrow part of #28"* |

The gap between #1872 (31 files) and #2229 (2 files, one effect) is the shape of
the problem: a large rewrite that stalls, plus a long tail of single-effect
leak fixes.

### The vanilla bug list (from #28)

* **Units are still visible under fog** — the headline failure.
* Structures under fog render incorrectly (transparent triangles), including
  when a building's top is visible but its foundation is not.
* Structures under fog **cannot be properly targeted** — units issue a move
  order instead of attack/garrison/repair unless the cursor is on the top edge
  of the top foundation cell.
* Jumpjets and aircraft give vision only while moving or landed.
* Aircraft vision is globalised through `[General]AircraftFogReveal` rather than
  per-unit sight.
* `[AudioVisual]FogRate` is a lose-lose dial: high rates flicker (and
  effectively deny air units any vision), low rates leave a decaying trail of
  vision behind every moving unit.
* Residual drawing glitches — black cell outlines that persist until you scroll
  away and back.

Note `FogRate` lives in **`[AudioVisual]`**, not `[General]`.

### Why it does not converge

Fog state is one thing; **fog-correct drawing is per-effect and effectively
unbounded**. Every drawing subsystem has to independently learn not to draw
through fog. From #1872's own list, each needing separate work:

EBolt (incl. ownerless shrapnel bolts), NaturalParticleSystem,
RefinerySmokeParticleSystem, DamageParticleSystems, SparkParticleSystem,
LaserTrailClass (all three types), LaserDrawClass / DiskLaserClass, RadBeam,
CaptureManager mind-control links, flying strings, RadSite, `Sparky=yes`
warheads, voxel turrets on buildings, `IonBlastClass::Draw`.

Every new effect a mod or framework adds re-opens the list. That is the
structural reason this is a long project rather than a feature.

### Known-broken specifics (from #1872, still open)

* **Save/load crashes** under fog.
* **`Shroud=no` completely breaks it** — worked around there with a
  `RemoveShroudGlobally=yes` rules tag that strips shroud at game start while
  leaving fog intact.
* **Performance degrades** as fogged objects accumulate.
* Building fog proxies vanish when the building is destroyed (correct behaviour
  is for the silhouette to persist until re-sighted).
* `RevealToAll=yes` buildings get re-fogged shortly after reveal.

### VERIFIED — which toggle is the live gate, and which is only a default

Three `FogOfWar` fields exist, and they are **not** interchangeable. Measured in
game (IntelExt fog probe, 51 samples over ~25 minutes of play):

| Field | Fed from | Role |
|---|---|---|
| `RulesClass::FogOfWar` | `rulesmd.ini` **`[MultiplayerDialogSettings]`** | the lobby **default** only |
| `ScenarioClass::SpecialFlags.FogOfWar` | the map / `spawnmap.ini` **`[SpecialFlags]`** | the live **per-match gate** |
| `GameModeOptionsClass::FogOfWar` | `spawn.ini` | session option; the client rewrites this file at launch |

**`[SpecialFlags]` is `ScenarioClass::SpecialFlags` in INI form.** Its keys map
one-to-one onto YRpp's `ScenarioFlags` bitfield — `MCVDeploy`, `InitialVeteran`,
`FixedAlliance`, `HarvesterImmune`, `FogOfWar`, `Inert`, `IonStorms`,
`Meteorites`, `DestroyableBridges`. That is the section to edit for any of those
flags, and it explains why the struct looks like TS residue: it is the TS
scenario flag set, still wired to the INI.

**The trap this creates.** Setting `FogOfWar=yes` in `rulesmd.ini` makes
`RulesClass::FogOfWar` read 1 while the scenario bit stays 0, because the map's
`[SpecialFlags]FogOfWar=no` wins. A probe then observes "fog is on, nothing is
fogged" and concludes the fog layer is dead — a **false negative**, because fog
was never armed for that match. Any measurement here must report the scenario
bit, not the rules field, before drawing a conclusion.

Likewise `spawn.ini` is not a reliable place to set it: the CnCNet client
regenerates that file from the lobby immediately before launch (observed
overwriting a manual edit 4 seconds pre-launch).

**Confirmed via** IntelExt's fog probe reading both fields live, and the key/bit
correspondence between `spawnmap.ini [SpecialFlags]` and YRpp `ScenarioFlags`.
**Still unverified:** whether fog actually engages once the *scenario* bit is
armed — that measurement has not yet been taken, so nothing on this page should
be read as proof the state layer is dead.

### The asymmetry worth designing around: shroud works, fog does not

The single most useful takeaway for anyone planning concealment work in YR:

* **Shroud is a first-class visibility state the renderer fully respects.** Units
  under shroud are hidden, targeting behaves, effects do not leak through. Gap
  generators are built on it and work.
* **Fog is a second-class state the renderer half-honours.** Units draw through
  it, structures mis-render and mis-target, and every effect subsystem needs its
  own opt-in check.

So a mod wanting fog-*like* presentation ("see the terrain and remembered
buildings, but nothing live") is usually better served by keeping **shroud
semantics** — which are correct and free — and changing only how shrouded cells
are *drawn*, than by enabling the fog state and then chasing every leak. The
work moves from "make ~14 unbounded effect subsystems respect a state" to "draw
one state differently, and remember buildings". That is a much more bounded
problem, though it does mean re-implementing the remembered-object snapshot that
`FoggedObjectClass` already provides for the broken path.

Unverified: no implementation has validated that inversion; it is a design
inference from the two states' differing renderer support.

### The one cheap lever that does work

`FogOfWar` is reachable as a **spawn/session option**, so it can be exposed in
the CnCNet client without touching the game — a lobby checkbox with:

```
SpawnIniOption=FogOfWar
Checked=True
```

**Confirmed via** YRpp headers (`RulesClass.h`, `CellClass.h`, `ScenarioClass.h`,
`GameModeOptionsClass.h`, `GeneralDefinitions.h`), this repo's
`registry/vanilla-tags.csv` and `engine-string-surface.csv` for the read sites,
Antares (`develop`) + Phobos source for current usage, and Phobos PRs #122 /
#1872 for the broken-state evidence. **Unverified:** no fog game was run
first-hand for this writeup; the "does not work" conclusion rests on the PR
history and the mod author's report, not on a local repro.

---

## Related

* `Gap-Generator-Vision.md` — gap is the *forces-re-discovery* concealment, and
  is computed client-side against `CurrentPlayer` only.
* `Map-Reveal-Sight.md` — `MapClass::RevealArea0/1/2` and the stride-512 trap.
