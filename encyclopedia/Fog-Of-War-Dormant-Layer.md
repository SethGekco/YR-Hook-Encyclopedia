# Fog of War — the dormant Tiberian Sun layer in YR

**Summary.** Yuri's Revenge still contains Tiberian Sun's fog-of-war system:
per-cell fog verbs, a per-cell fogged-object snapshot list, a foggedness byte
indexing `fog.shp`, regrow rates, and **three separate `FogOfWar` toggles** that
are real vanilla INI tags. RA2/YR ship with it switched off.

**But it is switched off because it is broken, not merely unused.** Turning the
tag on does not get you working fog — see the warning section below before
planning any work here. **The state layer is fine and this is now measured, not
inferred; the renderer is what fails.**

Read this page in both directions: "add fog of war" is not a from-scratch
project (the machinery exists), and it is also not a small one (making the rest
of the renderer respect it has defeated three attempts).

---

## The toggles — `FogOfWar` is a vanilla tag, in three places

| Field | Header | Read at |
|---|---|---|
| `RulesClass::FogOfWar` | `RulesClass.h:798` | `0x6721E7` |
| `GameModeOptionsClass::FogOfWar` | `GameModeOptionsClass.h:40` | `0x6B8C1B`, `0x6B8E6F` |
| `ScenarioClass::SpecialFlags.FogOfWar` | `ScenarioClass.h:39`, a bit in `ScenarioFlags` — **not** a direct member | — (fed from `[SpecialFlags]`; this is the LIVE gate, see below) |

Three levels — rules default, per-session game option, per-scenario bit — which
is the same shape as other TS-era session options (`Shroud`, `Crates`,
`ShortGame`). A *map* can therefore demand fog independently of the rules
default, **and in practice the map is what decides** — see the verified section
on which toggle is the live gate. The registry lists `FogOfWar` as scope `map|ra2|rules|ts`, consistent
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

### VERIFIED IN GAME — the fog STATE works; the renderer is what fails

Measured with the scenario bit armed (IntelExt forced
`ScenarioClass::SpecialFlags.FogOfWar`), fog rendering visibly on screen:

| Signal | Fog off | Fog on |
|---|---|---|
| `shrouded` (`ShroudCounter > 0`) | 5983 | 3724 |
| `obscured` (`Foggedness != -1`) | 6047 | 5083 |
| **excess** (obscured − shrouded) | **64** | **1359** |
| `FoggedObjects` snapshots | 0 | **10** |
| `CellClass::IsFogged()` | 0 | **0** ⚠ |

So the state layer is **live**: cells are obscured well beyond what shroud
explains, and the per-cell object snapshot is being built. Fog is not inert in
YR — it engages fine once the scenario bit is actually set.

**⚠ `CellClass::IsFogged()` (`0x4879B0`) is not a usable "is this cell fogged"
test.** It returned false for every cell in a match where fog was rendering on
screen and `FoggedObjects` were being created. Anything measuring fog should use
the obscured-over-shroud excess and the `FoggedObjects` count instead; reading
`IsFogged() == 0` as "no fog" produces a confident false negative. (Phobos uses
it as a *draw* guard in `FlyingStrings.cpp`, which may be why its narrowness has
gone unnoticed.)

**The observed renderer failures**, reproduced independently of #28's list and
matching it:

* Infantry and buildings **both visible inside fog** — #28's headline bug.
* Buildings **redraw live under fog** instead of being replaced by their
  `FoggedObjectClass` proxy. The snapshots exist (`fogobjs > 0`, measured up to
  172 concurrently); the draw path simply does not use them. Observed concretely
  as **AI repair being visible through fog**, and **building animations that
  never stop**.
* **Structures under fog cannot be targeted.** Ordering units to attack a
  fogged building makes them *move into the area* instead of attacking — an
  independent reproduction of #28's targeting bug, and the clearest proof that
  fog is not merely cosmetic: it breaks command resolution too.
* **Partial-cell shroud edges.** Not a clean outline — *half* a cell renders as
  shroud and fades, leaving a sawtooth boundary along the fog/shroud frontier.
  This is #28's "black outline of cell remains until we scroll away and back",
  and it points at the `Foggedness` byte (the `0..48` fog.shp/shroud.shp frame
  index) being resolved per-cell without a consistent edge rule.

That last point is the sharpest confirmation of this page's thesis: the
snapshot machinery is *running and correct*, and the drawing code ignores it.
The work is repair, not reimplementation — but it is the long tail, which is
what has defeated three attempts.

**Confirmed via** IntelExt's fog probe (26 samples, scenario bit forced) plus
direct visual observation.

### RE — the fog draw path, from disassembly

Disassembled from `gamemd.exe` md5 `fe2301a1f48841aa084aade100b25335`, verified
against the documented `CreateGap` prologue before trusting anything.

**The scenario gate, exactly.** `CellClass::FogCell` (`0x486A70`) opens with:

```
mov  eax, ds:0xA8B230      ; ScenarioClass::Instance
mov  edx, [eax]            ; SpecialFlags dword
test dh, 0x10              ; bit 12
je   <bail>
```

`dh & 0x10` is **bit 12**, which is exactly where `FogOfWar` sits in YRpp's
`ScenarioFlags` (after `CTFMode`, `Inert`, `TiberiumGrows`, `TiberiumSpreads`,
`MCVDeploy`, `InitialVeteran`, `FixedAlliance`, `HarvesterImmune`). The YRpp
layout is correct, and no cell can fog while that bit is clear.

**⚠ CORRECTION — what `FogCell` actually allocates.** An earlier revision of
this page read the `push 0x18; call 0x7C8E17` in `FogCell` as constructing a
`FoggedObjectClass` and reported vtable `0x7E44F4` with methods
`0x45A070`–`0x45AC90`. That was wrong, and the tell was `0x4D2790` reading
`[ecx+0x30]` and `[ecx+0x60]` on a supposedly 24-byte object.

`0x45A680` (the method called immediately after that allocation) is
`VectorClass::SetCapacity` — it allocates `count*4` bytes for pointers and
clears `IsAllocated`. So the 0x18 bytes are a **`DynamicVectorClass`**, whose
field initialisation matches exactly: `+0x04` Items, `+0x08` Capacity, `+0x0C`
IsAllocated, `+0x10` Count, `+0x14` CapacityIncrement (`0xA`).

| Fact | Value |
|---|---|
| `CellClass +0x28` | `DynamicVectorClass<FoggedObjectClass*>*` — the vector |
| Vector vtable | `0x7E44F4` (generic vector, methods `0x45A070`–`0x45AC90`) |
| Vector instance size | `0x18` |

`FogCell` therefore *lazily creates the cell's vector*, then walks the cell's
objects (from `CellClass +0xE4`) to populate it.

**`FoggedObjectClass` itself is much larger**, and is only partly mapped:

| Offset | Meaning |
|---|---|
| `+0x00` | `CellStruct` (X,Y words; `0x7FFF,0x7FFF` is the sentinel) |
| `+0x30` | a type/RTTI enum — `0x4D2790` branches on `== 6` |
| `+0x34` | coordinate triple (X, Y, Z dwords) |
| `+0x60` | pointer to the object being represented |

`0x4D2790` is thus a small accessor: *if this fogged object is type 6, return
`vtable+0x90` of the object at `+0x60`, else 0* — not a fog helper as first
assumed.

**The real per-cell fog flag is `CellClass +0x140`, bit `0x400000`** — `FogCell`
sets it with `or [ebp+0x140], 0x400000`. That, not `IsFogged()`, is what the
engine itself uses.

**⚠ `CellClass::IsFogged()` (`0x4879B0`) has ZERO callers in the binary.** It is
dead code. That is why it returns false even in a match where fog is visibly
rendering and snapshots are being built. Never use it as a fog predicate; read
`+0x140 & 0x400000` instead.

### RE — `FoggedObjectClass` fully mapped, and it has NO draw method

Constructor `0x4D0EF0`, allocated `push 0x78` in `0x457AA0`.

| Fact | Value |
|---|---|
| Instance size | **`0x78`** |
| Vtable | **`0x7E8B38`** (+ COM vtables at `+0x04`/`+0x08`/`+0x0C`) |
| Constructor | `0x4D0EF0` |
| Created by | `0x457AA0`, called from `FogCell` |

Field layout, read off the constructor:

| Offset | Meaning |
|---|---|
| `+0x24` | `-1` |
| `+0x28` | `HouseClass*` owner — copied from `ObjectClass +0x21C` |
| `+0x2C` | `0` |
| `+0x30` | type tag — the ctor hardcodes **`6`** |
| `+0x34` | `CoordStruct` — copied from `ObjectClass +0x9C` (`Location`) |
| `+0x60` | pointer to the represented object |

**The decisive finding: its vtable contains no Draw.** The only
FoggedObject-specific overrides are

| Slot | Address | What it is |
|---|---|---|
| `+0x20` | `0x4D2910` | scalar deleting destructor |
| `+0x34` | `0x4D2810` | **Save** — streams `+0x24`, `+0x2C`, `+0x30` via `0x4A1D50` |
| `+0x18` | `0x4D24A0` | **Load** |
| `+0x0C`, `+0x2C`, `+0x30` | `0x4D27D0`, `0x4D27B0`, `0x4D27C0` | tiny constant accessors |

Everything else is inherited `AbstractClass` (`0x410xxx`). So the class is a
**pure serialisable data snapshot** — it records what stood where, and survives
save/load, but nothing in it renders anything.

That reframes the whole feature. The snapshots are built correctly and are
*queryable*, but there is no proxy-drawing code to re-enable. Anything wanting
"buildings stay drawn but frozen" has to supply the drawing itself, using the
snapshot as its data source.

### `FogCell`'s two treatments — and the `+0x150` lever

`FogCell` walks the cell's object list (head at `CellClass +0xE4`, chained via
`ObjectClass +0x30`) and dispatches on RTTI:

* **type `6`** → `call 0x457AA0`, which builds the snapshot
* **types `1`, `2`, `0xF`** → `call [vtable+0x150]` only

and `0x457AA0` *also* calls `[vtable+0x150]` on its object before snapshotting.

So **`ObjectClass` vtable slot `+0x150` is the engine's own "this object is now
under fog" call, applied uniformly to every object type it fogs.** That is the
single convergence point for fog-related object suppression, rather than a
per-subsystem check — worth identifying before writing any fog draw work.
**Unverified:** what `+0x150` actually does; it has not yet been resolved to a
concrete function.

### RESOLVED — `+0x14C` / `+0x150` are `Select` / `Unselect`, NOT show/hide

⚠ **This section previously claimed `+0x150` was `Hide()`, that `ObjectClass
+0x83` was an "on display" flag, and that the engine therefore already
suppresses drawing for fogged objects. All of that was wrong.** The corrected
result matters, because the wrong version made fog look far closer to working
than it is.

| Slot | Address | Actually is |
|---|---|---|
| `+0x14C` | `0x5F4520` | **`ObjectClass::Select`** (TechnoClass overrides at `0x6FBFA0`) |
| `+0x150` | `0x5F44A0` | **`ObjectClass::Unselect`** |

| Global | Meaning |
|---|---|
| `0xA8ECB8` / `0xA8ECBC` / `0xA8ECC8` | the **selection list** object / items / count |
| `ObjectClass +0x83` | **IsSelected** |

**How to check this without guessing** — the registry already knew:

```
0x5F45A0  Kratos  TechnoClass_Select
0x5F45AF  Phobos  ObjectClass_Select_MultiSelectNotOwned
0x6FBFA3  Phobos  TechnoClass_Select_SkipLimboDelivery
```

All three sit *inside* these functions. Confirming behaviourally, `0x4AC2F1`
calls `+0x14C` from inside `DisplayClass::LeftMouseButtonUp` — the click-to-select
path — and the other callers are state changes that legitimately re-select or
drop selection: `UnitClass::ReceiveDamage`, `UnitClass::Deploy`, building
selling, parasite exit.

**So what `FogCell` does with `[vtable+0x150]` is *deselect* objects that become
fogged** — you lose control of units you can no longer see. Sensible, and
nothing to do with rendering.

`BuildingClass::DrawVisible` testing `+0x83` is therefore testing *is this
building selected*, before calling `[eax+0x458]` to draw the **selection box and
health bar**. It is "draw the visible indicators", not "draw the building".

### The corrected bottom line for fog

The engine provides, for fogged cells:

* ✅ a per-cell fog flag (`CellClass +0x140` bit `0x400000`)
* ✅ object **snapshots** for type-6 objects (`FoggedObjectClass`, correct and
  serialisable)
* ✅ **deselection** of fogged objects
* ❌ **no draw suppression** for fogged objects
* ❌ **no proxy drawing** of the snapshots (the class has no Draw method)

Both of the last two have to be written. There is no dormant rendering path to
re-enable — the snapshots are data with no consumer, and nothing stops a fogged
object drawing normally.

**Method note, since this cost two corrections on one page:** resolve vtable
slots against `registry/hooks.csv` *first*. Framework hook names are the cheapest
ground truth available for any address, and both errors here would have been
caught immediately by checking it before reasoning from disassembly shape.

### FOUND — the object draw dispatch, and the one seam for fog suppression

Resolved by locating `BuildingClass::Draw` (`0x43D290`, from the registry's
Phobos hooks at `0x43D29D`/`0x43D2B5`) inside the vtables:

| Slot | Meaning | Base implementation |
|---|---|---|
| `+0x104` | **`ObjectClass::DrawIfVisible`** — the visibility gate | **`0x5F4B10`, used by 16 of 21 classes** |
| `+0x114` | **`ObjectClass::Draw`** — the actual render | per-class, 17 distinct implementations |

Only four classes override the *gate*:

| Class | `DrawIfVisible` override |
|---|---|
| AnimClass | `0x422C70` |
| BuildingClass | `0x43CEA0` |
| TerrainClass | `0x71CC50` |
| UnitClass | `0x73B0B0` |
| (one more) | `0x749B20` |

`ObjectClass::DrawIfVisible` reads:

```
mov  al, ds:0xA8ED6B       ; global override -- skips all checks when set
mov  eax, ds:0xB73550      ; second global gate
mov  al, [esi+0x80]        ; redraw flag; 0 -> do not draw
mov  al, [esi+0x81]        ; set -> do not draw
mov  BYTE PTR [esi+0x80],0 ; CLEARED after use -- dirty-flag pattern
call [edx+0xAC]            ; get bounding rect
call 0x6D2140              ; viewport intersection test (ds:0x887324)
```

**The three flags, confirmed independently by YRpp's field order** (`ObjectClass.h`,
the run `NeedsRedraw`, `InLimbo`, `InOpenToppedTransport`, `IsSelected`):

| Offset | YRpp name | Role here |
|---|---|---|
| `+0x80` | `NeedsRedraw` | dirty flag — **cleared by the gate after use** |
| `+0x81` | `InLimbo` | "act as if it doesn't exist"; set → never drawn |
| `+0x83` | `IsSelected` | drives `Select`/`Unselect`, and the indicator draw |

That cross-check matters: it independently confirms the corrected reading above
(`+0x83` is selection, not display) from a source that was not the disassembly.
Two of the three flags were also mis-read here at first, and the header settles
all three.

Note the same `ds:0xA8ED6B` global short-circuits `ObjectClass::Select`, so it is
a broad "ignore visibility rules" switch.

**Why this matters for fog.** This is the per-object draw gate that every
drawable type funnels through — five functions total (one base plus four
overrides), not fourteen subsystems. A fog check placed here suppresses units,
infantry, buildings, terrain, overlays and animations uniformly, using the
`CellClass +0x140 & 0x400000` predicate.

That is the correct seam for fog draw-suppression. It does **not** solve proxy
drawing — `FoggedObjectClass` still has no Draw, so "buildings stay drawn but
frozen" needs a separate decal/proxy layer fed from the snapshots.

**Unverified:** whether the four overrides chain to the base or reimplement the
gate; each must be read before hooking, or the override classes will silently
keep drawing.

### Why objects show through fog — the root cause

`BuildingClass::DrawVisible` (`0x43E7B0`) decides to draw from
**`ObjectClass +0x210`, `DiscoveredByHouses`**:

```
mov  eax, [esi+0x210]          ; DiscoveredByHouses
mov  ecx, [ecx+0xB8]           ; CurrentPlayer house index
shl  edx, cl
test eax, edx                  ; discovered by me?
```

It never consults shroud or fog. Neither does anything else in the draw path —
`CellClass::IsShrouded()` (`0x487950`) has 9 callers and **none of them are
drawing code**; they are targeting and AI checks.

So **shroud does not hide objects by skipping their draw. It paints an opaque
layer over them afterwards.** Objects are drawn whenever they have been
discovered, and shroud simply covers the result.

This is the actual explanation for "everything is visible under fog": the fog
layer is *translucent by design* — that is the entire point of fog — so the
objects drawn underneath show straight through it. It is not fourteen
subsystems each forgetting a fog check; it is one architectural consequence of
concealment being a paint-over rather than a draw-suppression.

The engine's intended answer is the snapshot: a fogged cell should draw its
`FoggedObjectClass` proxies *instead of* the live objects. The snapshots are
built correctly (`fogobjs > 0` measured in game). **Unverified:** whether
anything still draws them — the class's methods are reachable only through the
vtable, so their zero direct xrefs proves nothing either way, and the consumer
has not yet been located.

**Hook contention:** `0x43E7B0` is already held by **Antares and Ares**
(`BuildingClass_DrawVisible`, 5 bytes, `Ext/Building/Hooks.Infiltrate.cpp`).
Chain with `return 0`; do not contest it.

### VERIFIED — a full map reveal clears SHROUD but not FOG

Not on #28's list, and it explains a confusing late-game symptom: *the fog
visually disappears, but buildings keep behaving as though fogged.*

Measured across one match, sampling every 450 frames. Between frame 34200 and
34650 the map was fully revealed:

| Frame | shrouded | mapped | obscured | fogobjs |
|---|---|---|---|---|
| 34200 | 16495 | 25239 | 33817 | 302 |
| **34650** | **0** | **41734** | 31225 | 307 |
| 35550 | 0 | 41734 | 23123 | 309 |

`cells` was 41734, so `mapped` reaching 41734 is *every cell on the map*, and
`shrouded` fell to exactly zero in a single sample window — an instantaneous
full reveal.

**What survived the reveal:**

* `ScenarioClass::SpecialFlags.FogOfWar` — still set.
* `FoggedObjects` — **unaffected** (307, and still ~340 twenty samples later).
  The per-cell object snapshots were neither cleared nor rebuilt.
* `Foggedness != -1` — still true on tens of thousands of cells, decaying only
  slowly afterwards.

So the reveal path clears `ShroudCounter` and sets `Mapped`, but does **not**
call `CleanFog` / `ClearFoggedObjects` for the revealed cells. Shroud and fog
are separate states, and revealing the map only unwinds one of them.

**The consequence is worse than a cosmetic glitch.** With shroud gone there is
nothing to composite the translucent layer against, so fog stops being *visible*
— while the fog *state* remains live, so everything driven by it continues:
buildings still render from stale snapshots, still fail to update, and are still
mis-targeted (units move instead of attacking). The player loses the only visual
cue that fog is in effect while keeping all of its gameplay consequences.

Anything enabling fog needs to clear fog state wherever it clears shroud, or the
two drift apart permanently the first time anything reveals the map — a spy
satellite, a reveal trigger, or a map-wide reveal superweapon.

**Confirmed via** IntelExt's fog probe, one match, 450-frame sampling.
**Unverified:** which specific reveal path fired here; the correlation is with a
full-map reveal in general, not with an identified caller.

### VERIFIED — `AnimTypeClass::Layer = Layer::Surface` stops an anim drawing

Bisected in game across four builds. An `AnimClass` whose type is set to
`Layer::Surface` is **not drawn at all** — the object exists (counted live in
`AnimClass::Array` every frame), it simply never appears.

The sequence, because the failure mimics several other bugs:

| Build | Layer | Result |
|---|---|---|
| palette fix | untouched | bodies **visible** |
| z-order "fix" | `Layer::Surface` | bodies invisible |
| +3 lifetime fixes | `Layer::Surface` | still invisible |
| layer reverted | untouched | bodies **visible** again |

**Why this is worth writing down:** an anim on `Surface` that never draws looks
exactly like an anim that expired early. Three separate lifetime theories
(`Rate` semantics, `RemainingIterations`, `Paused`/`NeedsRedraw`) were each
plausible, each produced a real fix for a real bug, and none of them was the
cause. The census that proved the objects were alive the whole time is what
eventually separated "not drawn" from "not there".

`Layer::Surface` (1) sits below `Ground` (2) in the enum, but the layer is
evidently not part of the normal anim draw pass.

**⚠ And `ZAdjust` is not the safe alternative either.** The obvious follow-up —
keep the default layer and bias depth with `AnimTypeClass::ZAdjust` — was tried
next and produced the SAME disappearance at `ZAdjust = 128`, reverting to
visible at `0`. Two independent depth controls, same result.

So an `AnimClass` carrier gives reliable **visibility** but no usable **depth
control**: any attempt to push it back in the sort order so far removes it from
the draw entirely. Anything needing a ground-hugging decal under units should
expect to solve depth some other way, and should not assume these two knobs
behave like a sort bias.

**Unverified:** whether a *negative* `ZAdjust` behaves differently (only the
positive direction was tested), and whether the cut-off is a threshold or any
non-zero value at all.

**Confirmed via** IntelExt corpse carriers, four in-game builds with a per-frame
census distinguishing existence from visibility. **Unverified:** whether
`Surface` is drawn by some other pass entirely (smudges/craters live there), or
never drawn for `AnimClass` specifically.

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
