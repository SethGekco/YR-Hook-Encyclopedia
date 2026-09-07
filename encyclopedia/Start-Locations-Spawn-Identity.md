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
does this house hold?" you must **invert** it — there is no house→start *field*.

> **There is, however, an inverting helper: `HouseClass::GetSpawnPosition()`.**
> Not a game function — an inline helper in YRpp's `HouseClass.h`. It scans
> `HouseIndices` comparing each entry against `this->ArrayIndex` and returns the
> first match, or `-1`:
>
> ```cpp
> int GetSpawnPosition() const {
>     const int currentIndex = this->ArrayIndex;
>     const int* houseIndices = ScenarioClass::Instance->HouseIndices;
>     for (int i = 0; i < 8; i++)
>         if (houseIndices[i] == currentIndex) return i;
>     return -1;
> }
> ```
>
> Three things worth extracting from it:
>
> - **It compares the raw stored int against `ArrayIndex` rather than resolving
>   the value through `HouseClass::Array`.** Given observation 5 below — the
>   table can hold cell values — this is the safer of the two possible readings:
>   a corrupt entry simply fails to match, where resolving it would be a wild
>   read. **Prefer comparison over resolution when inverting this table.**
> - **It is bounded at 8 and returns only the FIRST match**, so it cannot express
>   more than 8 starts or a house holding several. Fine for vanilla; not a
>   substitute for a set-valued reading if either of those is in play.
> - **It has a real consumer**, `HouseClass::IsInitiallyObserver()`
>   (`HouseClass.h:734`), which is `IsHumanPlayer && GetSpawnPosition() == -1` —
>   i.e. *an observer is a human house matching no start index*. That an
>   observer check is built on this inversion is meaningful evidence that
>   `HouseIndices` **is** populated with house `ArrayIndex` values during normal
>   play, which observation 5's corruption warning might otherwise cast doubt on.
>   (Evidence, not proof: still worth confirming in a live game.)

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

**5. ⚠ `HouseIndices` does not always contain house indices.** The
`mmtrt/yrpp-spawner` 16-player module lists among its own jobs *"rewrite the
waypoint house-index table when it holds cell values"* and *"repair corrupt
`HouseIndices`"* (its waypoint hooks `0x5D6CBF` / `0x5D6D02` exist for this).
So in some states the array holds **cell values** rather than house-array
indices, and can be corrupt outright. **Any reader must validate before
dereferencing** — range-check each entry against `HouseClass::Array` count and
treat out-of-range as unassigned. Code that indexes `HouseClass::Array` blind
with a value from this table has a wild read. The exact states that produce cell
values are **not yet characterised** — an acquisition target.

**6. `AssignHouses` runs twice, tearing the house array down in between.** Per
the runtime-instrumented findings in
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md), `0x687F10` executes
twice per game start with `HouseClass::Array.Count` back at 0 on the second
entry. Anything that caches start↔house state at scenario init must be
**idempotent or explicitly one-shot**, and must not hold `HouseClass*` across the
boundary. Resolving lazily at point of use avoids the problem entirely.

**Confirmed via.** YRpp `ScenarioClass.h` read directly (declaration order and
array widths quoted above). **Confirmed.** The many-to-one *consumer* behaviour
(observation 3) is **explicitly unverified**.

### ✅ RUNTIME-CONFIRMED (2026-09-06): the table is populated as described

Live skirmish, 1 human + 1 AI, read on the first logic frame (`0x55B6B3`) by a
third-party DLL that inverts the table independently:

```
NumberStartingPoints = 8
HouseClass::Array.Count = 4
  HouseIndices[ 0] = 0
  HouseIndices[ 7] = 1
  (all other 14 slots = -1)
  house[ 0] Americans    human=1  starts=0       GetSpawnPosition=0
  house[ 1] Yugoslavia   human=0  starts=7       GetSpawnPosition=7
  house[ 2] Neutral      human=0  starts=(none)  GetSpawnPosition=-1
  house[ 3] Special      human=0  starts=(none)  GetSpawnPosition=-1
```

Four claims on this page move from inferred to **confirmed**:

1. **`HouseIndices` really does hold house `ArrayIndex` values during play**, and
   is indexed by *start position*. Previously only inferred from
   `IsInitiallyObserver()` being built on the inversion.
2. **`-1` is the empty-slot sentinel** — 14 of 16 slots held it.
3. **The array is sparse.** Only *occupied* starts carry a value; an 8-start map
   with 2 players leaves six `-1` holes *between* live entries (here 0 and 7).
   Consumers must skip holes, not stop at the first one.
4. **Non-player houses resolve to no start.** Neutral and Special both returned
   `-1`, matching the `IsInitiallyObserver()` shape.

An independent inversion agreed with `GetSpawnPosition()` on all four houses.
**No out-of-range or cell-value entries appeared in this run** — which does not
disprove observation 5, only shows the corrupt state was not reached here.

---

## ⚠ `NumberStartingPoints` did NOT equal the player count in a live run

The section above ("`NumberStartingPoints` is the engine's de-facto player
count") needs qualifying. In the 2026-09-06 run it read **8** while the game held
**2 real houses** (1 human + 1 AI, plus Neutral and Special). All eight
`StartingPoints[0..7]` carried distinct coordinates, so 8 is the number of start
positions **the map defines** — not the number of players.

That is not a contradiction of the Phobos citation, which remains a fact:
`src/Ext/House/Hooks.cpp:475` really does assign this field to a local named
`playerCount`. It does mean **the two readings can disagree**, and on this
evidence the field tracks the *map*, at least at first-logic-frame time.

What remains **unresolved**:

- Whether the value is later narrowed toward the house total (the `min` against
  `players − observers + AIPlayers` at `0x6883E6` runs during scenario setup —
  the observation above is from the first logic frame, which is after that, so a
  narrowing would have to happen elsewhere or not at all).
- Whether Phobos' team-delay feature is therefore reading a map-derived number
  where it intends a player count. On this run it would have seen 8 for a
  2-player game. Not investigated; flagged because the feature's
  `DynamicTeamDelayType::StartingPoint` mode is explicitly documented as deriving
  player count this way.

**Practical guidance:** do not treat `NumberStartingPoints` as a player count.
Use it for what it demonstrably is — a bound on how many entries of
`HouseIndices` / `StartingPoints` are meaningful — and get the house count from
`HouseClass::Array.Count`.

**Confirmed via.** Live skirmish under Antares + Phobos + 16 co-loaded DLLs,
logged at `0x55B6B3` on the first logic frame; full dump quoted above.
**Confirmed** as an observation. The two unresolved points are explicitly **not**
investigated.

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
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md). Phobos' dynamic waypoint
map makes waypoints *storable* past 8, not *countable*.

### ⚠ The counter either/or is scoped to player count, **not** start count

[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) now presents two routes
past 8: lift both counters, **or** keep the stock 8 cap and repair `HouseIndices`
downstream — the latter because the working `mmtrt/yrpp-spawner` 16-player build
hooks neither counter and does exactly that.

**That second route does not generalise to raising the number of start
positions**, and the reason is structural rather than a matter of effort:

| | >8 **players** | >8 **start positions** |
|---|---|---|
| Goal | more houses | more distinct start positions |
| Start positions | keeps 8, **forces houses to co-spawn** — `eStart[i] = (tplStart + i) % 8`, *"Keep starts in 0..7 so parallel assign path never OOB"* | needs > 8 to exist |
| Counters | may stay capped | **must be lifted — the counter *is* the quantity** |

The 16-player implementation buys extra houses by *spending* start-position
distinctness: it deliberately packs multiple houses onto the stock 8 positions.
So for anyone whose goal is *more distinct places to start*, the cap-and-repair
route removes the very thing they are trying to add, and lifting `0x68AF45` +
`0x6883E6` remains necessary.

**Corollary, and a useful one:** because that build assigns several houses to the
same start index and reportedly works, **start → house is evidently not required
to be a bijection**. That is direct (if indirect-in-direction) evidence bearing on
observation 3 above — it demonstrates non-uniqueness in the many-houses-to-one-start
direction, *not* the one-house-to-many-starts direction, so it weakens the
assumption of bijectivity without establishing the converse. Still **unverified**
for the direction that matters to multi-spawn.

**Confirmed via.** The `eStart` expression and its comment are quoted in
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) from
`mmtrt/yrpp-spawner` `src/Spawner/PlayerLimit16.cpp`. **Confirmed** as that
implementation's behaviour. That the build "works" is **the author's report**, not
independently tested here — and its author confirms **no online testing**.

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
