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

**The limit is on HOUSES, not on "players" — and the house array itself is not
the limit.** `HouseClass::Array` (`0xA80228`) is a
`DynamicVectorClass<HouseClass*>` — it **grows without bound**, so nothing caps
house *storage*. What caps houses is the bit-shift: every one of the bitfields
above does `1u << ArrayIndex` into a `DWORD`, so **`ArrayIndex` ≥ 32 shifts out
of range** (on x86, `shl` masks the count to 5 bits, so index 32 aliases onto
index 0 — houses silently start sharing alliance/spy bits rather than crashing).
Since every player *and* every computer is a `HouseClass`, plus Neutral and
Special, the ceiling is on the combined count.

**Do not confuse the two bitfield axes.** `IndexBitfield<HouseClass*>` is
indexed by *house* `ArrayIndex` (caps **houses** at 32); `IndexBitfield<HouseTypeClass*>`
— e.g. `ObjectClass::GetTypeOwners` / the `Owners=` tag, and
`HouseClass::InRequiredHouses` / `InForbiddenHouses` which shift
`Type->ArrayIndex2` — is indexed by *country* index and caps **countries** at 32.
Those are independent limits; raising the player count does not require more
countries, because many houses may share one country.

**Confirmed via.** YRpp headers: `Helpers/Template.h` `IndexBitfield::Contains/Add/Remove`
= `1u << obj->ArrayIndex` over a `DWORD data`; `HouseClass.h:935`
`DWORD Allies; //flags, one bit per HouseClass instance`; `HouseClass.h:197`
`IsAlliedWith` = `((1u << idxHouse) & this->Allies) != 0u`; `HouseClass.h:708`
`AltAllies` as `DWORD`; `HouseClass.h:143` `Array` as
`constant_ptr<DynamicVectorClass<HouseClass*>, 0xA80228u>`;
`TechnoClass.h:523` `DisplayProductionTo`; `HouseClass.h:868` `RadarVisibleTo`;
`ObjectClass.h:84` `GetTypeOwners`; `HouseClass.h:565/569` country-indexed
`InRequiredHouses`/`InForbiddenHouses`. **Confirmed** from source.
The "~25" practical ceiling is **inferred** from the +2 (Neutral/Special) houses
and the 32-bit width, not measured in-game — the arithmetic ceiling is 30
players, and where between 25 and 30 it actually breaks is untested.

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
`AIPlayers` option. So NOP-ing "an 8" here is not how you raise the cap.
(Superseded in detail by the disassembly below: the human loop is genuinely
dynamic, and the one hard cap in this function is the **AI-loop pointer bound at
`0x6882C5`**, not a scratch array or a colour picker. Reimplementing the whole
function is still the cleanest route, but the minimal patch surface is now
known.)

**VERIFIED YR DISASSEMBLY (2026-08-20).** `0x687F10` has now been disassembled
from vanilla `gamemd.exe` (sha1 `189a5a868b3cef8d3d1a58ac3cf0a5241675e4ea`,
md5 `fe2301a1f48841aa084aade100b25335`, 4,813,072 bytes) via
`objdump -D -b binary -m i386 --adjust-vma=0x400000` (file offset == RVA).
**The function spans `0x687F10`–`0x68837D`** (single `ret` at `0x68837D`).
This resolves several previously-unverified claims and **corrects one of them**.

Structure, in order:

| Stage | Addresses | Bound |
|---|---|---|
| Human/player houses | `0x687F59`–`0x688146` | `Session.Players.Count` — **dynamic** |
| AI houses | `0x68814C`–`0x6882CB` | **pointer-bounded to exactly 8** (below) |
| Neutral house | `0x6882D1`–`0x688320` | unconditional |
| Special house | `0x688325`–`0x68836B` | unconditional |

Concrete facts recovered:

- **`HouseClass::HouseClass(HouseTypeClass*)` is at `0x4F54A0`**, `__thiscall`
  (`ECX` = this, one stack arg = the `HouseTypeClass*`). Called **4×** at
  `0x687FC3`, `0x6881A0`, `0x6882FE`, `0x688351`.
- **`sizeof(HouseClass) == 0x160B8`** (90,296 bytes) — the literal pushed to
  `operator new` (`0x7C8E17`) at all four sites. This is the allocation size a
  reimplementation must use.
- **`HouseClass::ColorSchemeIndex` is at offset `+0x16054`** (written from the
  return of `0x69A310` at `0x6880D9` / `0x6881DA`, and at `0x68831A`).
- Globals: **`0xA8DA78`/`0xA8DA84`** = `Session.Players` data ptr / count;
  **`0xA8B274`** = AI-player count; **`0xA8B29C`** = `AISlots.Countries[8]`;
  **`0xA8B238`** = `SessionClass` instance.
- Neutral/Special are looked up **by name string** — `"Neutral"` @ `0x82BA08`,
  `"Special"` @ `0x817318` — through `0x5117D0` (HouseType-index-by-name), then
  constructed. Their colour comes from `"LightGrey"` @ `0x836ECC` via `0x68CAB0`.

**CORRECTION — YR has no colour-picker hang.** The earlier text on this page
(and the Vinifera-derived warning below) predicted a `Random_Pick` +
`while(true)` "spin until a free colour" loop that hangs past 8 houses. **YR does
not do this.** YR reads a *stored* colour index — `[player+0x53]` for humans,
`AISlots.Colors[i]` for AI — and converts it with a single call to
`SessionClass::GetPlayerColorScheme` (`0x69A310`) at `0x6880D2` and `0x6881D3`.
There is no retry loop and no `MAX_PLAYERS`-bounded RNG inside `0x687F10`.
The TS behaviour did not carry over. **This claim was previously marked
"inferred for YR pending disasm" — the disasm has now refuted it.**
(The colour *randomisation* that does exist lives elsewhere, in the lobby /
random-player path — see the Antares note under "Color scheme pool" — and
Antares has already lifted those bounds.)

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

### `0x6882C5` — AssignHouses AI-loop bound (**the real >7-AI wall**)

**Framework names** — *no framework hooks this address.* Not in the registry.

**What it does.** This is the loop-back test of the AI-house creation loop
inside `AssignHouses`. It is the single instruction that caps AI players at 8,
and it is **not** a `cmp $0x8`:

```asm
688158:  bb 9c b2 a8 00     mov    $0xa8b29c,%ebx     ; EBX = &AISlots.Countries[0]
68815d:  cmp    0x20(%esp),%eax                       ; i >= AIPlayers count?  -> done
688167:  mov    (%ebx),%edi                           ; EDI = Countries[i]
688169:  cmp    $0xffffffff,%edi                      ; -1 sentinel -> done
688172:  cmp    $0xfffffffd,%edi                      ; -3 sentinel -> done
68817b:  mov    0x20(%ebx),%esi                       ; ESI = Colors[i]  (+0x20 = 8 ints)
...
6882c2:  83 c3 04           add    $0x4,%ebx
6882c5:  81 fb bc b2 a8 00  cmp    $0xa8b2bc,%ebx     ; <<< THE CAP
6882cb:  0f 8c 8c fe ff ff  jl     0x68815d
```

`0xA8B2BC − 0xA8B29C = 0x20` = **32 bytes = exactly 8 `int`s**. The loop is
bounded by walking a pointer to the *end address of the `Countries[8]` array*,
baked into the instruction as an absolute immediate.

**What it does *not* do — easily mistaken.** **The AI cap is not a numeric `8`
anywhere in this function.** Anyone grepping the disassembly for `cmp $0x8` /
`83 f8 08` to find "the AI limit" will not find it — the limit is encoded as the
*address* `0xA8B2BC`. Equally, the loop's *other* bound (`0x68815D`, against the
AI-player count at `0xA8B274`) **is** dynamic, which invites the wrong
conclusion that raising the AI count alone is sufficient. It is not.

Note also the layout consequence: `0xA8B2BC` is simultaneously the end of
`Countries[8]` **and the start of `Colors[8]`** (reached as `0x20(%ebx)`). The
sub-arrays are contiguous, so an overrun does not run off into unmapped memory —
it **silently reads the neighbouring array**, i.e. AI #9's "country" would be
read out of `Colors[0]`. That is a data-corruption failure, not a clean crash,
which makes it far nastier to diagnose.

**How to lift it.** Relocate `AISlots` into a larger allocation and rewrite both
the base (`0x688158`) and this bound (`0x6882C5`) — or bypass the loop entirely
by reimplementing `AssignHouses` and creating AI houses directly, which is the
route this subsystem's practical summary recommends.

**Confirmed via.** Ghidra-free `objdump` disassembly of vanilla `gamemd.exe`
(sha1 `189a5a86…`), 2026-08-20. **Confirmed** — instruction bytes quoted above.
The `Colors[8]`-adjacency conclusion follows from `0x20(%ebx)` reading Colors
while the bound equals base+0x20; **confirmed** arithmetically, **not** yet
observed as an in-game misread.

---

### `0x6883E6` — second starting-point counter (`i < 8`), distinct from `0x68AF45`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | (waypoint reimpl. hooks `0x6883B7`, `0x68843B` bracket this loop) | — | `Ext/Scenario/Hooks.Waypoints.cpp` |

**What it does.** Lives in the function at **`0x688380`–`0x6886AC`** — the
routine immediately *after* `AssignHouses`, not inside it. It walks the
scenario waypoint array (base `+0x632`) counting defined waypoints and stops at
the first undefined one, with a hard `i < 8` bound:

```asm
6883bd:  cmp    $0x2be,%eax        ; 0x2BE = 702, the vanilla waypoint ceiling
6883e6:  83 f8 08   cmp $0x8,%eax  ; <<< hardcoded 8
6883e9:  7c d2      jl  0x6883bd
```

The count it produces is then **min'd against the real house total**:

```asm
6883eb:  mov    0xa8da84,%eax      ; Players.Count
688400:  cmpl   $0xffffffff,0x6b(%ebx)  ; count players with [+0x6B] == -1 (observers)
68841b:  sub    %ebp,%eax          ; EAX = Players.Count - observers
68841d:  add    %ecx,%eax          ; EAX += AIPlayers  (0xA8B274)  = TOTAL HOUSES
68841f:  cmp    %eax,%esi          ; ESI = starting points counted above
688421:  jle    0x68842b           ; take the MINIMUM of the two
```

**Why it matters for player count.** Because of that `min`, **the `i < 8` at
`0x6883E6` is a binding constraint on the effective player count**, not merely a
cosmetic waypoint tally: however many houses you arrange for, the result is
`min(≤8, players + AI)`. Lifting `AssignHouses` without also lifting this leaves
the game clamped at 8.

**What it does *not* do — easily mistaken.** This is **not** the same loop as
the Phobos-hooked counter at `0x68AF45`, though the two are near-identical in
shape (`i < 8`, stop-at-first-undefined). **There are at least two independent
8-bounded starting-point counters in the binary** and a >8 build must lift both.
Reading this page's `0x68AF45` entry alone, or reading Phobos's waypoint hooks
alone, would leave this one in place. Note also that Phobos's waypoint hooks at
`0x6883B7` / `0x68843B` sit on *either side* of this loop but do **not** change
the `cmp $0x8` — Phobos makes the waypoints *storable*, not *countable* past 8.

**Confirmed via.** `objdump` disassembly of vanilla `gamemd.exe` (sha1
`189a5a86…`), 2026-08-20 — instruction bytes quoted. **Confirmed.** The
identification of `[player+0x6B] == -1` as the observer test is **inferred**
from context (it is subtracted from the player total before adding AI), not
confirmed against a struct definition.

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

**Now pinned to real addresses** (disasm 2026-08-20): `Countries[8]` lives at
**`0xA8B29C`** and `Colors[8]` immediately after it at **`0xA8B2BC`**; the AI
count is at **`0xA8B274`**. The consumer that enforces the 8 is the pointer
compare at **`0x6882C5`** — see its own entry above, which is the concrete patch
site. **Confirmed** from disassembly.

### `ScenarioClass::StartingPoints[8]` + `HouseIndices[0x10]`
Start-position storage (8) and start→house map (curiously **16**, not 8 — Westwood
left headroom). The spawner iterates `HouseIndices` with
`std::size(pScenarioClass->HouseIndices)` (`Spawner.cpp` ~155) and clamps
spawn locations `std::clamp(nSpawnLocations, 0, 7)` (~146). **Confirmed** from
YRpp `ScenarioClass.h` + spawner source.

> Now covered in full — including the mapping *direction* (start→house, so
> answering "which start does this house hold?" requires inverting it), the
> `HouseHomeCells[8]` / `NumCoopHumanStartSpots` neighbours, and why
> `NumberStartingPoints` doubles as a player-count proxy — in
> [Start-Locations-Spawn-Identity.md](Start-Locations-Spawn-Identity.md).

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
**confirmed** as TS behaviour (Vinifera) and **REFUTED for YR** — see the
correction under `0x687F10`: YR's `AssignHouses` reads a stored colour index and
converts it via `0x69A310`, with no retry loop.

**Antares has already lifted the colour bounds that do exist.** The
randomise/assign paths outside `AssignHouses` are hooked by Antares in
`src/Misc/Interface.PlayerColors.cpp`, each replacing a `MAX_PLAYERS`-bounded
pick with one bounded by the INI-driven `Ares::UISettings::ColorCount`:

| Address | Antares hook |
|---|---|
| `0x4E43C0` | `Game_InitDropdownColors` (clears `ColorCount + 1` slots) |
| `0x69A310` | `SessionClass_GetPlayerColorScheme` (slot→scheme, observer-aware) |
| `0x69B69B` | `GameModeClass_PickRandomColor_Unlimited` |
| `0x69B7FF` | `Session_SetColor_Unlimited` |
| `0x69B949` / `0x69BA13` | `Game_ProcessRandomPlayers_ColorsA` / `…ColorsB` |
| `0x69B97D` | `Game_ProcessRandomPlayers_ObserverColor` |

So a >8 build running **on Antares inherits an unbounded colour pool for free**;
a standalone DLL must either replicate these seven hooks or accept Antares as a
dependency. **Confirmed** from Antares source @ current master (the same hooks
appear in the Antares PDB symbol map as `Session_SetColor_Unlimited` etc.).

### CnCNet-Spawner networking cap (out of scope for offline)
The spawner's human-player path is bounded by `ListAddress::Array[8]`
(`NetHack.h`) and `IPXManagerClass::Connection[7]` (YRpp) — i.e. 7 remote + self
= 8 humans, with frame-sync/queue loops sized to match. **A 1-human + N-AI
offline game never touches this layer**, which is why >8 *AI* is far more
tractable than >8 *humans*. **Confirmed** from spawner source + YRpp header.

---

## Practical summary: what a >8-player (offline, AI) build must change

1. Reimplement `AssignHouses` (`0x687F10`) looping past 8 — the Vinifera
   `Assign_Houses()` is the structural blueprint, but **use YR's own verified
   wiring**: allocate `0x160B8` bytes, call the ctor at `0x4F54A0`
   (`__thiscall`, arg = `HouseTypeClass*`). **No colour-picker fix is needed
   inside this function on YR** (see the correction) — but do lift the AI-loop
   pointer bound at `0x6882C5`, which is the actual >7-AI wall.
2. Lift **both** starting-point counter loops — `0x68AF45` (`i < 8`) *and*
   `0x6883E6` (`i < 8`), the latter of which is min'd against the house total at
   `0x68841F` and so directly clamps the effective player count.
3. Adopt/borrow Phobos's dynamic-waypoint subsystem (or place start waypoints
   0..N on the map) so >8 start positions exist.
4. Widen or bypass `GameModeOptionsClass::AISlots[8]` and
   `ScenarioClass::StartingPoints[8]` / `HouseIndices[16]`.
5. Stay under ~30 total houses unless you also widen every per-house 32-bit
   bitfield (`HouseClass::Allies` et al.).
6. Offline only — leaving the `ListAddress[8]` / `Connection[7]` network layer
   untouched is fine and expected.

**Overall status: substantially confirmed (disasm 2026-08-20).** The addresses,
array sizes, and Phobos waypoint hooks are confirmed from source. `0x687F10` has
now been **disassembled**: the house constructor (`0x4F54A0`), object size
(`0x160B8`), the AI-loop pointer cap (`0x6882C5`), the second starting-point
counter (`0x6883E6`), and the Neutral/Special tail are all confirmed from
instruction bytes, and the predicted YR colour-picker hang is **refuted**.

Still unverified: the practical player ceiling between 25 and 30 (arithmetic
says 30; untested in-game); the observer test `[player+0x6B] == -1`; and the
entire downstream GUI break list (recon / diplo / score / loading) from the
RE-vet roadmap. Those need a runtime crash-walk, not more disassembly.
