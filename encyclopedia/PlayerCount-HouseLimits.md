# Subsystem: Player Count & House-Array Limits

Everything governing **how many houses/players a game can hold** and where the
vanilla "8" is actually enforced. This page exists because the 8-player limit is
not one constant — it is a scattered set of fixed-size arrays, `MAX_PLAYERS`
loop bounds, and a 32-bit house bitfield ceiling, each enforced at a different
address. Anyone trying to raise the limit (or debugging why a >8-house game
crashes/hangs) needs the whole set, not one hook.

Entries sorted by address where a specific hook exists; structural findings
(no single address) are grouped at the end.

---

## The one structural fact that organises this page

**A house set in YR is a single 32-bit bitfield indexed by
`HouseClass::ArrayIndex`.** `HouseClass::Allies`, `AltAllies`,
`TechnoClass::DisplayProductionTo`, and `CellClass::BaseSpacerOfHouses` are all
`IndexBitfield` / `DWORD` values with one bit per house. In multiplayer the
house array is [players + Neutral + Special], so the hard ceiling is:

```
players + Neutral(1) + Special(1)  ≤  32   →   ~25–29 real players max
```

This is almost certainly why the known Tiberian Sun ">8 players" work topped out
around 25: it is the widest that fits without widening every per-house bitfield
in the engine. Raising it *past* ~30 means auditing and widening those bitfields
everywhere — a much larger job than the array/loop changes below.

**Confirmed via.** YRpp headers (`HouseClass.h` — `Allies`/`AltAllies` as
`IndexBitfield<HouseClass*>`; `TechnoClass.h:638` `DisplayProductionTo` with the
per-ArrayIndex bit comment; `CellClass.h` `BaseSpacerOfHouses`; `Helpers/Template.h`
`IndexBitfield` = `1u << index` over a `DWORD`). **Confirmed** from source. The
"~25" practical ceiling is **inferred** from the +2 (Neutral/Special) houses and
the 32-bit width, not measured in-game.

---

### `0x687F10` — ScenarioClass::AssignHouses (vanilla, static)

**Framework names** — *no release framework currently reimplements this on YR.*
The CnCNet spawner (`yrpp-spawner`) *wraps around* it (reads the houses it
produces) but does not replace it. Listed here because it is the central
function for any player-count change.

**What it does.** Static function that builds the multiplayer `HouseClass`
instances at scenario start: iterates the player list assigning each a house,
color, country and start slot; then iterates AI players creating computer
houses; then creates the Neutral and Special houses last. This is where the
house array is populated.

**What it does *not* do.** It does **not** read the player count from a single
editable constant — the count comes from the session player list + the
`AIPlayers` option, and the *limits* are enforced by `MAX_PLAYERS`-sized scratch
arrays and the color picker inside the function (see structural notes). So
NOP-ing "an 8" here is not how you raise the cap; the whole function must be
reimplemented.

**Blueprint for a reimplementation.** **Vinifera** (the Tiberian Sun engine
extension by tomsons26/CCHyper — the same reverse-engineers credited by Phobos
for YR binary mappings) contains a *fully reimplemented, readable*
`Assign_Houses()` in `src/extensions/scenario/scenarioext.cpp` (~lines 874–1105),
installed via `Patch_Call`. TS is YR's ancestor engine, so this is the closest
readable relative of YR's `0x687F10`. Key structure it reveals:
- house creation is plain `new HouseClass(HouseTypes[idx])`;
- AI loop bound is `Players.Count() + Session.Options.AIPlayers`;
- each AI house is wired with `Init_Data(color, country, credits)` +
  `Assign_Handicap(difficulty)` — the "full native wiring" that a bolt-on,
  after-the-fact house creation would miss;
- **the color picker is the real color wall**: `color = Random_Pick(0, MAX_PLAYERS-1)`
  inside a `while(true)` loop that spins until it finds an unused color — past 8
  houses every color is taken and **this loop hangs forever**. A >8 port must
  widen the color pool, not just the loop bounds.
- Neutral + Special created unconditionally at the end.

**Register / calling convention.** `__fastcall`/static at `0x687F10`
(from YRpp `ScenarioClass::AssignHouses` `JMP_STD(0x687F10)`). Called from
`0x68745E` (Read_Scenario_INI) and `0x68ACFF` (ScenarioClass::Read_INI) — both
shown as `Patch_Call` targets by the spawner.

**Confirmed via.** Address + call sites: YRpp `ScenarioClass.h` and the spawner's
`Spawner.Hook.cpp` (`Apply_CALL(0x68745E …)`, `Apply_CALL(0x68ACFF …)`).
**Confirmed.** The TS structure: Vinifera `scenarioext.cpp` @ current main.
**Confirmed** as TS; its exact mapping onto YR's `0x687F10` internals (esp. the
YR equivalent of `Init_Data`) is **unverified** — YR's `HouseClass` exposes
`AssignHandicap` and `ColorSchemeIndex` but no single `Init_Data`, so YR likely
folds that init into the constructor (`0x4F54A0`) or an adjacent call. Needs a
YR disassembly of `0x687F10` to confirm.

---

### `0x68AF45` — ScenarioClass starting-point counter (Phobos hook)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `Scen_Waypoint_Call_4` | 0x6 | `Ext/Scenario/Hooks.Waypoints.cpp` |

**What it does.** Recomputes the number of starting points by walking waypoints
`0..7` and counting defined ones (stops at the first undefined). Returns the
count in `EDX`. Part of Phobos's broader waypoint-subsystem reimplementation.

**What it does *not* do.** Despite Phobos moving waypoints into a dynamic map
(see below), **this counter is still hardcoded `for (i = 0; i < 8; ++i)`** — so
even with Phobos, the *starting-point* count saturates at 8. Anyone raising the
player cap must also lift this loop; it is the value
`ScenarioClass::NumberStartingPoints` ends up reflecting, which other systems
(e.g. Phobos team-delays at `0x…`, see below) read as "player count."

**Confirmed via.** Phobos `Hooks.Waypoints.cpp` (`DEFINE_HOOK(0x68AF45, …)`,
the `i < 8` loop, `R->EDX(nStartingPoints)`). **Confirmed** from source.

---

### Phobos waypoint subsystem — dynamic `Waypoints` map (many addresses)

**Framework names**
| Framework | Function name(s) | Source file |
|---|---|---|
| Phobos | `ScenarioClass_Get_Waypoint_*`, `ScenarioClass_ReadWaypoints`, `ScenarioClass_Set_Waypoint`, `Waypoint_To_String`, `String_To_Waypoint`, … | `Ext/Scenario/Hooks.Waypoints.cpp` |

**What it does.** Phobos **replaces the vanilla fixed waypoint array with a
dynamic map** (`ScenarioExt::Global()->Waypoints`) and lifts the waypoint
*string* format from 2 letters to support far more waypoints. Relevant hook
addresses (all release Phobos):
`0x68BCC0`, `0x68BCE4`, `0x68BD08`, `0x68BD60`, `0x68BD80` (IsWaypointValid),
`0x68BDC0` (ReadWaypoints), `0x68BE90` (WriteWaypoints), `0x68BF50` (SetWaypoint),
`0x68BF74`, `0x68BF90`, `0x684CB7`, `0x6855E4`, `0x68AFE7`, `0x763610`
(Waypoint_To_String), `0x763690` (String_To_Waypoint), `0x6883B7`, `0x68843B`.

**Why it matters for player count.** Start positions **are** waypoints 0..N.
Vanilla maps can already *store* start waypoints up to index 701
(`IsDefinedWaypoint` valid range 0..701 per YRpp), and Phobos's dynamic map
removes the storage limit entirely. So the map-format side of ">8 start
positions" is **already solved by Phobos** — the remaining wall is the counting
loop at `0x68AF45` and the house-assignment/`MAX_PLAYERS` machinery, not
waypoint storage.

**What it does *not* do.** It does **not** raise the player cap — it makes more
waypoints *storable and addressable*, but `AssignHouses`, the start-point
counter, and the per-house bitfields still cap actual players. Waypoint
expansion is necessary-but-not-sufficient for >8 players.

**Confirmed via.** Phobos `Hooks.Waypoints.cpp` (the full hook set + the
`ScenarioExt::Global()->Waypoints[...]` dynamic-map accesses). **Confirmed** from
source. The 0..701 vanilla waypoint range: YRpp `ScenarioClass.h` comment.
**Confirmed** from header.

---

## Downstream break sites past house creation (RE-vet roadmap)

**Provenance.** This checklist comes from a reverse-engineering veteran in the
community, relayed by the project owner. It is a *predicted* ordering of what
breaks after you widen the player count, **not yet verified in-game** — each
item is a place to expect the *next* crash/glitch on the road to a 9-house game,
and each should get its own address-keyed entry here once a real crash address
or disassembled function pins it down. The vet's phrasing: "just slap more
player nodes for starters, then it will probably fail in scenario setup; once
that is fixed you'll probably need to fix a few GUIs."

The empirical approach the vet endorses — **widen the player-node count, let it
fail, fix the failure** — is the *same* path as the handoff's "reimplement
`AssignHouses`" decision, not a competing one: widening the node array keeps the
engine doing its own native house wiring (the thing the abandoned bolt-on
approach lost); the loop bound and color picker inside `0x687F10` are simply the
first thing that fails. "Slap more nodes → fails in scenario setup" **is**
`0x687F10`.

Predicted break order, with what we can already anchor:

1. **Scenario setup — `AssignHouses` (`0x687F10`).** *Known / documented above.*
   The loop bound `< 8` and the `MAX_PLAYERS`-bounded color-picker `while(true)`
   hang. This is "fails in scenario setup." **Confirmed** as the wall (TS via
   Vinifera; YR pending disasm).

2. **Recon — radar / minimap per-house display.** *Predicted; partially
   anchored.* Per-house radar state and colour run through the `Radar*` INI-tag
   surface — e.g. `RadarColor` (`0x5fe93e`, `0x71e003`), `LocalRadarColor`
   (`0x66b75b`), `RadarOn`/`RadarOff` (`0x66aae1`/`0x66ab23`) — and the `RADAR`
   render code at `0x475b00`/`0x47726f` (registry `engine-string-surface`). These
   are the closest existing anchors; the *minimap dot-per-house* draw loop that
   would actually overflow past 8 houses is **not yet located**. Expect colour /
   dot glitches or an out-of-range read here first among the GUIs.

3. **Diplomacy screen ("diplo").** *Predicted; unanchored.* The in-game
   diplomacy dialog lays out one row per house; a fixed 8-row layout or an
   8-bounded loop is the likely failure. **No address located yet.**

4. **Score screen.** *Predicted; unanchored.* End-of-game stats are per-house
   and read `SessionClass::MPStats[8]` (see structural note below) — the `[8]`
   stat array is the concrete thing that would overflow. **Render/loop address
   not located yet;** `MPStats[8]` is the anchor to widen.

5. **Loading screen.** *Predicted; unanchored.* The multiplayer load screen
   draws a per-player slot list; a fixed 8-slot layout is the suspected wall.
   **No address located yet.**

6. **`session/queue.cpp` frame sync — online only.** *Predicted; anchored,
   out of scope.* The vet notes the frame-sync queue is "per player, so size 7"
   — this is the `IPXManagerClass::Connection[7]` / `ListAddress::Array[8]`
   network layer (see the networking-cap structural note). **An offline
   1-human + N-AI game never reaches this**, so it stays untouched for
   MegaSkirmish; recorded here only so a future >8-*humans* effort knows where it
   lives.

**How to use this list.** Milestone 9 is a crash-walk: get 9 houses created,
then each GUI crash address that comes back gets looked up against the registry
and written up as a proper entry above. Items 3–5 are the ones with no address
yet — they are the encyclopedia's next acquisition targets for this subsystem.

**Confirmed via.** Item 1: as documented under `0x687F10`. Item 2 anchors:
registry `engine-string-surface.csv` / `vanilla-tags.csv` (`Radar*` tags, `RADAR`
code). Item 4 anchor: YRpp `SessionClass.h` (`MPStats[8]`). Item 6 anchor: YRpp
`NetHack.h` / `IPXManagerClass`. **The break *ordering* and the diplo/score/
loading GUI targets themselves are unverified** — a community RE vet's
prediction, pending in-game crash-walking.

---

## Structural findings (no single hook address)

These are the fixed-size-8 structures a >8-player build must widen. None is a
"hook" — they are the places the limit physically lives.

### `GameModeOptionsClass::AISlots` — 8-wide AI slot arrays
`Difficulties[8] Countries[8] Colors[8] Starts[8] Allies[8]`
(YRpp `GameModeOptionsClass.h`). This is **how AI players enter a skirmish**:
slot 0 is the human, so the stock maximum is 7 AI. The CnCNet spawner fills
these in a `for slotIndex < std::size(pAISlots->Allies)` loop
(`Spawner.cpp` ~234). For >7 AI this array (or its consumer) must be bypassed —
the AssignHouses-reimplementation path sidesteps it by creating AI houses
directly. **Confirmed** from YRpp header + spawner source.

### `ScenarioClass::StartingPoints[8]` + `HouseIndices[0x10]`
Start-position storage (8) and start→house map (curiously **16**, not 8 — Westwood
left headroom). The spawner iterates `HouseIndices` with
`std::size(pScenarioClass->HouseIndices)` (`Spawner.cpp` ~155) and clamps
spawn locations `std::clamp(nSpawnLocations, 0, 7)` (~146). **Confirmed** from
YRpp `ScenarioClass.h` + spawner source.

### `SessionClass` — `SlotData[8]`, `MPStats[8]`; `NumberStartingPoints`
`SlotData[8]` and `MPStats[8]` are lobby/stat arrays (YRpp `SessionClass.h`).
`ScenarioClass::NumberStartingPoints` is the engine's effective "player count"
proxy — Phobos reads it as such in its team-delay feature
(`Ext/House/Hooks.cpp` ~567, which itself clamps `playerCount > 8 → return`).
Low priority for a pure skirmish trial but part of the full picture.
**Confirmed** from YRpp header + Phobos source.

### Color scheme pool
`ColorScheme::Array` is INI-driven and *can* exceed 8 (mods add schemes;
Antares — the Ares-superset reimplementation — reads `Slot8`/`Slot12`/`Slot14`
colors in its `UISettings` code, inherited from the Ares lineage), and Phobos
guards color access with `color >= ColorScheme::Array.Count ? 0 : color`
(`Misc/MessageColumn.cpp`). **But** the vanilla AssignHouses color *picker* is
bounded by `MAX_PLAYERS` and loops until it finds a free slot — the hang
described under `0x687F10`. So the color *storage* isn't the wall; the vanilla
*picker* is. **Confirmed** from Antares/Phobos source; the picker-hang is
**confirmed** as TS behaviour (Vinifera), **inferred** for YR pending disasm.

### CnCNet-Spawner networking cap (out of scope for offline)
The spawner's human-player path is bounded by `ListAddress::Array[8]`
(`NetHack.h`) and `IPXManagerClass::Connection[7]` (YRpp) — i.e. 7 remote + self
= 8 humans, with frame-sync/queue loops sized to match. **A 1-human + N-AI
offline game never touches this layer**, which is why >8 *AI* is far more
tractable than >8 *humans*. **Confirmed** from spawner source + YRpp header.

---

## Practical summary: what a >8-player (offline, AI) build must change

1. Reimplement `AssignHouses` (`0x687F10`) looping past 8 — the Vinifera
   `Assign_Houses()` is the blueprint; **widen the color picker** to avoid the
   infinite loop.
2. Lift the starting-point counter loop at `0x68AF45` (`i < 8`).
3. Adopt/borrow Phobos's dynamic-waypoint subsystem (or place start waypoints
   0..N on the map) so >8 start positions exist.
4. Widen or bypass `GameModeOptionsClass::AISlots[8]` and
   `ScenarioClass::StartingPoints[8]` / `HouseIndices[16]`.
5. Stay under ~30 total houses unless you also widen every per-house 32-bit
   bitfield (`HouseClass::Allies` et al.).
6. Offline only — leaving the `ListAddress[8]` / `Connection[7]` network layer
   untouched is fine and expected.

**Overall status: partially confirmed.** The addresses, array sizes, and Phobos
waypoint hooks are confirmed from source. The AssignHouses *internals* on YR
(the `Init_Data` equivalent) and the practical player ceiling are unverified
pending a YR disassembly of `0x687F10` and in-game testing.
