# Subsystem: Start Locations & Spawn Identity

Where a player *spawns*, how the engine records it, and how that relates to the
other two identities a player carries (country and house slot).

This page exists because "spawn identity" is routinely conflated with house or
country identity — they are **three independent axes** with different widths,
different caps, and different failure modes. It also collects the `ScenarioClass`
start-location fields, which are referenced from
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) but never laid out in
full.

---

## The organising fact: three identity axes, not two

[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) warns "do not confuse
the two bitfield axes" (house-indexed vs country-indexed). There is a **third**
axis that is not a bitfield at all, and conflating it with either of the others
is the most common mistake in this subsystem.

| Axis | Keyed by | Where it lives | Cap | Cap mechanism |
|---|---|---|---|---|
| **Country** | `HouseTypeClass::ArrayIndex2` | `Owners=`, `RequiredHouses=`, `ForbiddenHouses=` (`1u << ArrayIndex2`) | 32 | 32-bit bitfield width |
| **House / player slot** | `HouseClass::ArrayIndex` | `Allies`, `AltAllies`, `DisplayProductionTo`; the `<Player @ A>`…`<Player @ H>` name form | 32 (practically 8) | 32-bit bitfield width |
| **Start location** | index into `ScenarioClass::StartingPoints` / `HouseIndices` | `ScenarioClass` (below) | 8 | **counting loops**, not a bitfield |

Consequences that follow from the table:

- **Start location is not derivable from country.** Two players of the same
  country routinely hold different starts, so nothing country-indexed
  (`Owners=`, `RequiredHouses=`) can distinguish them. This is the same
  `HouseTypeClass`-vs-`HouseClass` split that
  [PR#1853](#pr1853--player--x-as-trigger-owner) was written to work around.
- **Start location is not the `@`-letter either.** The `<Player @ X>` letter
  tracks the *house slot*, which is assigned from lobby order; the physical start
  waypoint is a separate assignment that random-start shuffles. They coincide only
  in the sequential, non-random case — which is why code that treats "spawn 0" and
  "`<Player @ A>`" as synonyms breaks the moment random start positions are on.
- **The start-location cap behaves differently from the other two.** The bitfield
  axes fail by *aliasing* (index ≥ 32 shifts out of range and silently shares
  bits). The start axis fails by *clamping* — the counting loops at `0x68AF45`
  and `0x6883E6` simply stop at 8. Different symptom, different fix: widening a
  bitfield does nothing for start locations, and lifting a loop bound does nothing
  for alliances.

---

## `ScenarioClass` start-location fields (structural, no hook)

Verified from YRpp `ScenarioClass.h`, declaration order:

```cpp
CellStruct Waypoints [702];          // all waypoints; starts are a prefix of these

//Map Header
int   StartX, StartY, Width, Height;
int   NumberStartingPoints;
Point2D StartingPoints [0x8];        // 8
int   HouseIndices [0x10];           // 16 — "starting position => HouseClass::Array->GetItem(#)"
CellStruct HouseHomeCells [0x8];     // 8
bool  TeamsPresent;
int   NumCoopHumanStartSpots;
```

Four observations worth recording:

**1. `HouseIndices` is 16 wide while `StartingPoints` is 8.** The asymmetry is in
the vanilla header and appears to be Westwood headroom. Anyone sizing a
replacement structure by analogy with `StartingPoints[8]` will mis-size this one.

**2. `HouseIndices` maps start → house, not house → start.** The YRpp comment is
explicit: *"starting position => `HouseClass::Array->GetItem(#)`"*. Index it by
start position; the value is a **house array index**. To answer "which start(s)
does this house hold?" you must **invert** it — there is no direct house→start
field.

**3. The mapping direction structurally permits many-to-one.** Because it is a
function *from* start position *to* house, nothing in the storage prevents two
start indices naming the same house. Whether any *consumer* honours that (unit
placement, camera, radar, AI base planning) is **unverified** — the storage
permitting it is not the same as the engine supporting it. Recorded here as a
lead, not a capability.

**4. `HouseHomeCells[8]` and `NumCoopHumanStartSpots` are separate from the
above.** `HomeCell`/`AltHomeCell` (earlier in the class) are scenario-level, not
per-start. Co-op missions carry their own human-start-spot count. A change to
start locations that updates `StartingPoints`/`HouseIndices` but leaves these
untouched will behave inconsistently between skirmish and co-op.

**Confirmed via.** YRpp `ScenarioClass.h` read directly (declaration order and
array widths quoted above). **Confirmed.** The many-to-one *consumer* behaviour
(observation 3) is **explicitly unverified**.

---

## ⚠ `NumberStartingPoints` is the engine's de-facto player count

The most consequential trap on this page.

`ScenarioClass::NumberStartingPoints` is *named* as a count of start positions,
but downstream code reads it as **"how many players are in this game."** Concrete,
citable instance — Phobos' dynamic team-delay feature
(`src/Ext/House/Hooks.cpp:475`):

```cpp
int playerCount = ScenarioClass::Instance->NumberStartingPoints;

if (playerCount >= 2 && !SessionClass::IsCampaign())
```

The variable is literally named `playerCount`, and the feature exposes a
`DynamicTeamDelayType::StartingPoint` mode meaning "derive the count this way."
The vanilla engine reinforces the equivalence: at `0x6883E6` the counted
starting-point total is `min`'d against
`(Players.Count − observers + AIPlayers)`, so the two quantities are deliberately
tied together.

**What this means — easily mistaken.** Raising the number of *selectable start
positions* is **not** a cosmetic map-authoring change. It moves a value that other
subsystems consume as the player count, so it can perturb AI team delays and
anything else reading `NumberStartingPoints`. Conversely, anyone raising the
player count who does not also lift the start counters stays clamped at 8 by the
`min`. **The two quantities cannot be varied independently in the vanilla model.**

**Confirmed via.** Phobos source `src/Ext/House/Hooks.cpp:475` and the
`DynamicTeamDelayType` enum, read directly (develop). **Confirmed.** The
`0x6883E6` `min` behaviour: disassembly quoted in
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md). **Confirmed** there.
Which *other* subsystems read `NumberStartingPoints` is **not exhaustively
surveyed** — the Phobos site is one confirmed instance, not the full set.

---

## Counting loops (cross-reference, not duplicated)

The two independent 8-bounded starting-point counters — `0x68AF45` (Phobos hooks
it but leaves `for (i = 0; i < 8; ++i)` in place) and `0x6883E6` (**no framework
hooks it**) — are documented in full in
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md). Both must be lifted for
any >8-start work; Phobos' dynamic waypoint map makes waypoints *storable* past 8,
not *countable*.

For the buildability side of spawn-conditional logic, see
[Buildability-Prerequisites.md](Buildability-Prerequisites.md): hook the
`0x4F8361` epilogue, never `0x4F7870` (Ares-lineage fully replaces it).

---

## PR#1853 — `<Player @ X>` as trigger owner

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `TriggerTypeClass_ReadINI_PlayerAtX` (`0x727292`) | 0x5 | `src/Ext/Trigger/Hooks.cpp` |
| Phobos | `TriggerClass_CTOR_PlayerAtX` (`0x725FC7`) | 0x7 | `src/Ext/Trigger/Hooks.cpp` |
| Phobos | `TriggerClass_Logic_PlayerAtX` (`0x72652D`, `0x7265F7`) | 0x6 | `src/Ext/Trigger/Hooks.cpp` |
| Phobos | `TriggerClass_Destroy_PlayerAtX` (`0x726727`) | 0x5 | `src/Ext/Trigger/Hooks.cpp` |

**Channel: `PR#1853`, not release.** Open PR by @Starkku, approved and labelled
"needs testing" as of this writing. Supersedes the closed PR#746, which proposed
the same idea (owner values `4475`–`4482` → `<Player @ A>`…`<Player @ G>`) and was
closed in favour of #1853.

**What it does.** Lets skirmish/MP maps name an individual player slot as a
*trigger owner*, resolving `<Player @ X>` to the live `HouseClass` at runtime. If
that player is not present in the game, the trigger is destroyed and never
springs. The motivating problem, in the PR author's framing: the engine stores
trigger owner as a `HouseTypeClass` (a **country**), and multiple players can pick
the same country, so country lookup cannot identify an individual player. Changing
the stored type outright would break existing maps and editors, so the `<Player @
X>` string form is resolved at the trigger sites instead.

**What it does *not* do — easily mistaken.** This is the misconception this page
most needs to head off:

- It does **not** add spawn- or player-conditional **buildability**. It is scoped
  to the trigger/tag/event path only. Nothing in it touches `CanBuild`
  (`0x4F8361`), prerequisites, or `Owner=`. A `Rulesmd.ini` ownership tag keyed on
  spawn position is *not* provided by this PR — it would be new work at the
  buildability gate.
- It resolves the **house slot** (Axis 2 above), *not* the physical start
  waypoint. `<Player @ A>` means "the player in slot A," not "whoever spawned at
  the north position." With random start positions those are different players.
- It is **PR-channel**, so it is absent from any release build. Do not assume its
  addresses are occupied in a stock Phobos install.

**Used by / interactions.** All five addresses are in the `0x725xxx`–`0x727xxx`
trigger cluster and are PR-only; no release framework hooks them. A third-party
DLL touching trigger ownership should expect to collide with this cluster **if**
the user runs a build including PR#1853.

**Confirmed via.** Registry `hooks.csv` (5 rows, channel `PR#1853`, with stolen
byte counts and source file as quoted); `registry/pr-hooks.md` for the PR title
and author; the PR description on GitHub for behaviour and the
`HouseTypeClass`-vs-`HouseClass` rationale. **Unverified:** the actual handler
bodies were not read (PR branch not cloned locally), and no in-game testing —
consistent with the PR's own "needs testing" label.

---

## Open acquisition targets for this page

Recorded so the next person does not re-derive them:

1. **The starting-unit / MCV placement loop** — the code that reads a house's
   start position and places its initial units there. Not yet located; it is the
   consumer that would determine whether `HouseIndices`' many-to-one capability
   (observation 3) is real. **No address.**
2. **The lobby spawn-picker** — where a player's chosen start position is written
   into `HouseIndices`. **No address.**
3. **Random start assignment** — which RNG assigns starts when random positions
   are enabled, and whether it is the synced `ScenarioClass::Random`. Relevant to
   sync-safety for anything that varies start assignment. **No address.**
4. **Full survey of `NumberStartingPoints` readers** — one confirmed (Phobos team
   delays); the rest unknown.
