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
countries, because many houses may share one country. **The country axis has its
own page** — see [Countries-Taunts.md](Countries-Taunts.md), which documents the
32-country bitfield, its single parser (`0x4750D0`) and four write sites, and a
*second*, narrower country-index limit (a 4-bit nibble) in the taunt wire format.

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

### `0x50DEF0` / `0x50DF30` / `0x50E000` — the house base cell: where start position actually becomes a map location

**Framework names** — *no framework hooks these.* Absent from the registry and
from the Antares PDB symbol map, despite ~12 call sites between them.

**What they do.** Placement does **not** read `ScenarioClass::StartingPoints`.
It reads a per-house **base cell** stored on `HouseClass`:

| Field | Meaning |
|---|---|
| `HouseClass + 0x5490` | base cell (fallback / home) |
| `HouseClass + 0x5494` | base cell (current) — `.X` at `+0x5494`, `.Y` at `+0x5496` |

| Address | Signature | Purpose |
|---|---|---|
| `0x50DEF0` | `__thiscall(CellStruct* out)`, `ret $0x4` | returns the base **cell** |
| `0x50DF30` | `__thiscall(CoordStruct* out)`, `ret $0x4` | same, converted to world **coords** |
| `0x50DFE0` | `__thiscall(CellStruct)`, `ret $0x4` | sets `+0x5494` (two instructions) |
| `0x50E000` | `__thiscall(...)` | the widely-called setter (~8 call sites) |

Both getters select `+0x5494` when valid, else fall back to `+0x5490`; validity
is a compare against the invalid-cell sentinel at `0xA8EF98`/`0xA8EF9A`.

**The full pipeline**, end to end:

```
[Header] Waypoint1..N
  -> 0x689F64   parser (loops on NumberStartingPoints, see its entry)
  -> StartingPoints[8] @ ScenarioClass+0x1140
  -> 0x5D6C21   EDX = table[house->+0x16058]   <-- start index becomes a cell
  -> 0x5D6C25   SetBaseCell (0x50E000); 0x5D6C2F sets HouseIndices[startIdx]
  -> HouseClass +0x5490 / +0x5494
  -> 0x50DEF0 (cell) / 0x50DF30 (coord)
  -> 0x5D7098  MCV Unlimbo   (vtable+0xD8, after ctor 0x7353C0, sizeof 0x8E8)
```

**Why this is the useful lever.** Everything that wants to move, share or add a
start position converges on the `start location -> base cell` step around
**`0x5D6C25`–`0x5D6D3A`**. Offsetting a house's spawn, seating two houses on one
start point, or honouring a start index past the vanilla 8 are all the *same*
edit at that step — none of them require touching placement, the parser, or
`StartingPoints` itself. Note `mmtrt/yrpp-spawner` independently hooks
`0x5D6CBF` / `0x5D6D02` (as `Waypoint_HouseLoad` / `Waypoint_NotFoundSkip`),
i.e. the same region, which is useful corroboration.

**What they do *not* do — easily mistaken.** Searching for consumers of
`ScenarioClass::StartingPoints` in order to find placement **will not find it**,
and this is a genuine time sink: the only scale-8 indexed reads of that array in
the whole binary belong to the *map-preview renderer* (`0x6408F5`/`0x64093B`).
`StartingPoints` is an **input consumed once** during scenario setup, not a
runtime source of truth. Likewise the four readers of the house's start-location
*index* (`HouseClass+0x1605C`) are all diagnostics or the auto-ally pass at
`0x5D74AF` — none of them place anything.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-25 — field offsets and both getters read from instruction bytes; the
MCV path traced from `0x5D7064` (`push $0x8e8` -> `operator new` -> ctor
`0x7353C0` -> `0x50DF30` -> `call *0xd8(%ebx)`). **Confirmed.** The precise
semantics of `+0x5490` vs `+0x5494` (fallback vs current) are **inferred** from
the getters' selection logic.

**The single instruction that turns a start index into a cell is `0x5D6C21`**
(`mov (%eax,%esi,4),%edx`), where `ESI` = `house->+0x16058`, `EAX` = a cell
table passed at `0xC(%esp)`, and `ECX` = the house. It runs once per house per
game. Hooking `0x5D6C1D` (7 bytes, covering both `mov`s and returning to the
intact `push %edx` at `0x5D6C24`) is therefore sufficient to relocate, offset or
share any house's spawn — no placement, parser or `StartingPoints` changes
required. **Confirmed** from instruction bytes.

---

### `0x5D6C1D` / `0x5D6D3F` — how a house actually gets its spawn cell

**Framework names** — *no framework hooks either.* Not in the registry.

**What they do.** Two different paths assign a house's base cell, and **which
one runs depends on whether the player chose a start position or left it
Random**:

| Path | Runs for | Return address seen in a trace |
|---|---|---|
| `0x5D6C21` → `SetBaseCell` | houses with an **explicit** start index | `0x5D6C2A` |
| `0x5D6D3A` → `SetBaseCell` | **every** house, later | `0x5D6D3F` |

Observed in one game (1 human + 7 AI, two players on explicit starts):

```
[trace] home house@… start=7  cell=(178,111) <- caller 0x005D6C2A
[trace] home house@… start=0  cell=(111,178) <- caller 0x005D6C2A
[trace] home house@… start=-2 cell=(35,102)  <- caller 0x005D6D3F     (-2 = Random)
… 16 calls from 0x5D6D3F vs 3 from 0x5D6C2A …
```

**`0x5D6D3F` is the last writer and it wins.** It runs for every house after the
explicit-start pass, so anything written at `0x5D6C21` is overwritten. Anyone
trying to relocate a spawn must act here, not at the earlier and more
obvious-looking site.

**The start-cell table is a stack argument, exposed only at `0x5D6C1D`.** It
arrives at `0xC(%esp)` and is indexed by start position. It is **not**
`ScenarioClass::StartingPoints` — on one map `StartingPoints` read
`(222,145) (227,120) …` while the cells actually assigned were
`(111,178) (35,102) (178,111) …`. If you need "the cell of start position N",
this table is the only place to get it, so capture the pointer while you can.

**⚠ Three traps this subsystem sets, all verified the hard way.**

1. **A hook that is silent is not necessarily dead.** `0x5D6C1D` produced zero
   log lines in a test where every player was on Random, and was written off as
   unreachable. It fires only for *explicit* start indices. Test with the
   configuration your feature targets before concluding an address is dead.
2. **`HouseIndices[start] = house` means one house per start.** Written at
   `0x5D6C2F`. Point two houses at the same start index and the engine
   **relocates one of them to a free position** — which looks exactly like "my
   start selection was ignored and I got a random free slot". Sharing a start
   position therefore cannot be done by writing the index; override the *cell*
   after assignment instead.
3. **The map-header rectangle is not cell space.** `StartX`/`StartY`/`Width`/
   `Height` (`+0x112C`…`+0x1138`) cannot be used to bounds-check a cell: on the
   same map every genuine spawn cell had `X` in `35..178` while the header read
   `x[206,305)`. A validity check built on it rejects perfectly valid positions.

**Also relevant.** `0x007398D3` writes base cells again slightly later, offset
by `(-1,-1)` from the values `0x5D6D3F` set — purpose unconfirmed, but it is a
third writer and worth knowing about before assuming yours is final.

**Confirmed via.** Runtime tracing of the two `SetBaseCell` stores
(`0x50DFE4`, `0x50E004`) with caller return addresses, plus in-game verification
that overriding at `0x5D6D3F` relocates a spawn as intended. **Confirmed.** The
role of `0x007398D3` is **unverified**.

---

### `0x688508` — the "start waypoint deficiency" search never terminates

**Framework names** — *no framework hooks this.* Not in the registry.

**What it does.** When there are more houses than the map declares start
positions, the engine logs

```
Multiplayer start waypoint deficiency - looking for more start positions
```

and then tries to **invent** the missing positions by scanning the map
(`0x6885B5` → `MapClass` at `0x56DC20`, with `MapClass::Instance` = `0x87F7E8`
in `ECX`).

**That search does not come back.** Observed with 9 houses on an 8-start map:
the game sat on a black screen indefinitely, and sampling the process showed the
main thread pegged at 100% — 35,000+ CPU ticks — in `0x56E838` / `0x57854E`
while every other thread idled in `__kernel_vsyscall`. It is a single-threaded
spin, not slow work, so waiting does not help.

**How to skip it safely.** The surrounding shape is:

```asm
688502:  jle  0x68864d      ; vanilla "no deficiency" exit
688508:  push $0x83dcd4     ; the deficiency message  <- hook here, 5 bytes
688521:  mov  $0x8,%edi     ; start generating from position 8
6885b5:  call 0x56dc20      ; the search
...
68864d:  xor  %eax,%eax     ; normal continuation
```

Returning `0x68864D` from a hook at `0x688508` takes **exactly the branch
vanilla takes when no house is short** — not a novel path, which is what makes
it safe.

**⚠ Only skip it if something else is supplying the positions.** The search
exists for a reason: suppress it with nothing in its place and the surplus house
simply gets no position, spawns nothing, and is eliminated before the player
sees it — presenting as "the extra player never showed up" rather than as a
placement bug.

**Useful neighbours for anyone doing that.**

| Address | Use |
|---|---|
| `0x578460` | `MapClass::IsWithinUsableArea(const CellStruct&, bool)`, `__thiscall` — the engine's own "can something stand here". Use this to validate a synthesised cell. |
| `0x568300` | `MapClass::CoordinatesLegal(const CellStruct&)` |
| `HouseTypeClass + 0x1A6` | non-zero for Neutral/Special. Vanilla tests it at `0x5D74C9`; use the same test or those two houses will consume start positions meant for players. |

**⚠ Do NOT validate cells with the map-header rectangle.** `StartX`/`StartY`/
`Width`/`Height` (`ScenarioClass +0x112C`…`+0x1138`) are not cell coordinates:
on one map every genuine spawn cell had `X` in `35..178` while the header read
`x[206,305)`. A check built on it rejects every valid position.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`) for the
instruction shape; live process sampling for the spin; in-game verification that
suppressing it plus supplying positions yields a working 9-house game.
**Confirmed.** Why the search fails to terminate is **not established** — only
that it does.

---

### `0x5D74AF` — houses sharing a start location are silently auto-allied

**Framework names** — *no framework hooks this address.* Not in the registry.

**⚠ There are TWO adjacent start-location fields on `HouseClass`, and they are
not interchangeable.** Both are written by `AssignHouses`:

| Field | Read by | Written at |
|---|---|---|
| `+0x16058` | **placement** — the `start index -> base cell` loop at `0x5D6C12` | `0x6880F2` (human), `0x6881EC` (AI) |
| `+0x1605C` | **this auto-ally pass** | `0x688101` (human), `0x6881FB` (AI) |

Which is "resolved" versus "requested" is **not established**; what matters is
that a hook changing where a house *spawns* must target `+0x16058`, while one
changing who it *allies with* must target `+0x1605C`. Changing one does not
affect the other.

**What it does.** A double loop over `HouseClass::Array` (items ptr `0xA8022C`,
count `0xA80238`) comparing every pair of houses' `+0x1605C`. When two match, it
**mutually allies them**:

```asm
5d74d4:  mov  0x1605c(%ecx),%ecx      ; A's start location
5d74da:  cmp  $0xfffffffe,%ecx        ; -2 (random) -> skip
5d74df:  cmp  $0xffffffff,%ecx        ; -1 (none)   -> skip
...
5d74fd:  mov  0x1605c(%ecx),%ecx      ; A's start
5d7503:  cmp  0x1605c(%edx),%ecx      ; == B's start?
5d7509:  jne  0x5d7524                ; differ -> next pair
5d750b:  push $0x0; push %esi; mov %ebx,%ecx; call 0x4f9b70   ; A.MakeAlly(B,false)
5d7515:  push $0x0; push %ebx; mov %esi,%ecx; call 0x4f9b70   ; B.MakeAlly(A,false)
```

`0x4F9B70` is `HouseClass::MakeAlly(HouseClass*, bool bAnnounce)` (YRpp
`HouseClass.h:219-220`), called with `bAnnounce = false` — hence *silently*.
Neutral/Special are excluded by the `Type + 0x1A6` test.

**Why this matters for >8 players.** It establishes that **duplicate start
locations are an expected engine state, not an error condition**. Any scheme
that seats more houses than the map has start positions — the obvious approach
when you want 16 players on an 8-spawn map — will land here, and the engine
will not crash or corrupt: it will quietly make those players allies.

**What it does *not* do — easily mistaken.** This is **not** a co-op or team
setting; it fires purely on start-location equality, ignores lobby alliances
entirely, and announces nothing. So "my extra players all started allied" has a
cause that is invisible in the lobby, in `spawn.ini`, and in any team setting —
which makes it very easy to misattribute to the alliance UI or to a mod. Anyone
implementing shared spawn points **must suppress or post-correct this pass**, or
every house sharing a point is permanently allied from frame 0.

Also note it does not *place* anything: it only reads start locations. It is not
the code that turns a start index into map coordinates.

**Nearby.** `0x5D7550` is a small accessor —
`GetHouseStartLocation(int houseIndex)`, `ret $0x4`, returning
`HouseClass::Array[idx] + 0x1605C`.

**Confirmed via.** `objdump` disassembly of vanilla `gamemd.exe`
(sha1 `189a5a86…`), 2026-08-24 — instruction bytes quoted. `0x4F9B70`
identified from YRpp `HouseClass.h`. `+0x1605C` as the start-location field is
**confirmed** from its writers inside `AssignHouses` (`0x688101` human path,
`0x6881FB` AI path). **Confirmed.** The `-2` sentinel meaning "random start" is
**inferred** from context, not verified.

---

### `0x689F64` — map-header start-point reader (generic) + `0x689D66` (the 8)

**Framework names** — *no framework hooks either address.* Not in the registry.

**What it does.** `ScenarioClass::ReadMapHeader` (~`0x689D30`) initialises the
map-header fields and then reads `[Header] Waypoint1..N` into
`StartingPoints[]`:

```asm
689d40:  lea  0x1140(%esi),%edi        ; &StartingPoints[0]
689d66:  mov  $0x8,%ecx                ; <<< clear loop: hardcoded 8 entries
689d6b:  mov %edx,(%eax); mov %ebx,0x4(%eax); add $0x8,%eax; dec %ecx; jne
...
689f64:  mov  0x113c(%esi),%ecx        ; NumberStartingPoints
689f70:  lea  0x1140(%esi),%ebx        ; &StartingPoints[0]
689f76:  inc  %eax                     ; 1-based ("Waypoint1" is index 0)
689f80:  push $0x83de24                ; "Waypoint%d"
689faa:  mov  %ecx,(%ebx)              ; StartingPoints[i].X
689fac:  mov  %eax,0x4(%ebx)           ; StartingPoints[i].Y
689fb9:  add  $0x8,%ebx                ; stride 8 = sizeof(Point2D)
689fbc:  cmp  %ecx,%eax
689fbe:  jl   0x689f76                 ; while i < NumberStartingPoints
```

**The read loop is bounded by `NumberStartingPoints`, not by 8.** It is already
generic over N — the parser will happily read `Waypoint9=`, `Waypoint12=` … if
the map's `[Header]` declares a larger `NumberStartingPoints`.

**⚠ LATENT VANILLA BUFFER OVERFLOW.** `ScenarioClass::StartingPoints` is only
**8** `Point2D` entries (`+0x1140`..`+0x117F`), immediately followed by
`HouseIndices[0x10]` (`+0x1180`). Because the reader trusts
`NumberStartingPoints` without clamping, **a map declaring more than 8 starting
points overwrites `HouseIndices[]`** — start position 9 lands on
`HouseIndices[0]` and `[1]`, and so on. This is a vanilla defect, not something
introduced by raising a player cap, and it means "just author a 12-spawn map"
silently corrupts the start→house table rather than failing cleanly. Note the
*clear* loop at `0x689D66` is separately hardcoded to 8, so entries past 8 are
also never initialised.

**Consequence for >8 start positions.** The parser needs no change. What must
change is the storage and the small number of sites that address it:
`0x689D40` and `0x689F70` (the two `lea` bases), `0x689D66` (the clear count),
and the preview renderer's `0x6408F5`/`0x64093B` (see `0x6408E2`). Widening or
relocating `StartingPoints` is therefore a bounded patch, **not** a hunt through
dozens of consumers.

**What it does *not* do — easily mistaken.** These are the map-*header*
start points, which are **not** `ScenarioClass::Waypoints[702]`. The 702-entry
waypoint array is for triggers and scripting and is **empty in multiplayer**
(verified in-game: every entry reads the `(0,0)` undefined sentinel while
`StartingPoints[8]` is populated). Any plan to gain start positions by writing
unused entries of `Waypoints[702]` targets the wrong array.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-24 — instruction bytes quoted. `StartingPoints`/`HouseIndices` adjacency
from YRpp `ScenarioClass.h:112-113` plus the runtime-probed field offsets
(`NumberStartingPoints` at `+0x113C`). **Confirmed.** The overflow is
**inferred** from the unclamped loop bound and the adjacency; **not yet
triggered deliberately** with a >8-start map.

---

### `0x6408E2` — start-marker draw: the `>8` early-out that blanks the preview

**Framework names** — *no framework hooks this address.* Not in the registry,
and no Antares PDB symbol nearby.

**What it does.** Inside the routine that draws start-position markers onto the
map preview / loading screen, this is a guard that **abandons the entire draw**
when the map has more than 8 starting points:

```asm
6408d4:  8b 81 3c 11 00 00  mov  0x113c(%ecx),%eax   ; NumberStartingPoints
6408da:  85 c0              test %eax,%eax
6408dc:  0f 8e 4d 01 00 00  jle  0x640a2f            ; <=0 -> bail
6408e2:  83 f8 08           cmp  $0x8,%eax
6408e5:  0f 8f 44 01 00 00  jg   0x640a2f            ; >8  -> BAIL ENTIRELY
6408eb:  33 f6              xor  %esi,%esi
6408f5:  8b 84 f1 40 11 00 00  mov 0x1140(%ecx,%esi,8),%eax   ; StartingPoints[i].X
...
640a23:  3b b1 3c 11 00 00  cmp  0x113c(%ecx),%esi   ; loop while i < NumberStartingPoints
640a29:  0f 8c c6 fe ff ff  jl   0x6408f5
640a2f:  5f 5e 5d 5b ...    pop/pop/pop/pop; add $0x80,%esp; ret $0x4   ; EPILOGUE
```

`0x640A2F` is the function's own epilogue, so `jg` there is an immediate return.

**The important part: the draw loop is NOT capped at 8.** Its bound is
`NumberStartingPoints` (`0x640A23`), and the body indexes
`StartingPoints[i]` at `0x1140(%ecx,%esi,8)` with `Point2D` scale 8. The
renderer is already generic over N markers — **only the early-out at `0x6408E2`
stops it**. Widening or removing that single compare should let the existing
loop draw 9+ markers unchanged.

**What it does *not* do — easily mistaken.** This is **not** the loading-screen
*progress* path. Attempts to fix ">8 player indicators" by hooking the progress
bar (e.g. `0x552D60` / `0x553687`) will not touch this, because the failure is
not mis-drawing — it is **drawing nothing at all**. The symptom to expect with
>8 starts is *no start markers whatsoever*, not garbled ones, and that
distinction is the quickest way to tell the two paths apart.

It also reads `StartX`/`StartY`/`Width`/`Height` (`0x112C`/`0x1130`/`0x1134`/
`0x1138`) purely to scale map coordinates into preview pixels — those are not
player-count related.

**Register / calling convention.** `ECX` = `ScenarioClass::Instance`
(`0xA8B230`), one stack argument, `ret $0x4`. `ESI` is the marker index.

**Confirmed via.** `objdump` disassembly of vanilla `gamemd.exe`
(sha1 `189a5a86…`), 2026-08-24 — instruction bytes quoted above, and the skip
target verified to be the epilogue. **Confirmed.** That this is the cause of the
commonly-reported ">8 loading-screen player indicators don't work" is
**inferred** from the guard's placement and effect; **not yet tested in-game**
with `NumberStartingPoints > 8`.

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

**RUNTIME-VALIDATED IN A LIVE GAME (2026-08-23).** The address map below was
confirmed in-game by read-only logging hooks on this function's entry
(`0x687F10`) and epilogue (`0x688378`), in a 1-human + 2-AI skirmish under
Antares + Phobos + the CnCNet spawner. Observed:

```
GameMode      = 5 (Skirmish)          [0xA8B238]
Players.Count = 1                     [0xA8DA84]
AIPlayers     = 2                     [0xA8B274]
AISlots.Countries[8] @0xA8B29C = -1 0 6 -1 -1 -1 -1 -1
HouseClass::Array.Count: 0 -> 5
  house[0] ArrayIndex=0 human=1 country=French     color(yrpp)=29 color(+0x16054)=29
  house[1] ArrayIndex=1 human=0 country=Americans  color(yrpp)=3  color(+0x16054)=3
  house[2] ArrayIndex=2 human=0 country=Australia  color(yrpp)=13 color(+0x16054)=13
  house[3] ArrayIndex=3 human=0 country=Neutral    color(yrpp)=5  color(+0x16054)=5
  house[4] ArrayIndex=4 human=0 country=Special    color(yrpp)=5  color(+0x16054)=5
```

Every claim below is therefore **runtime-confirmed**, not merely disassembled:
`0xA8B238` (GameMode, and the enum values), `0xA8DA78`/`0xA8DA84`, `0xA8B274`,
`0xA8B29C`, the `0x20` AISlots stride, and **`+0x16054`** — the last by reading
`ColorSchemeIndex` twice, once via YRpp's struct and once via the raw offset,
which agreed for all five houses. Neutral and Special are confirmed created
unconditionally and last, both taking colour 5 (the `"LightGrey"` lookup).

**⚠ `AssignHouses` runs TWICE per game start.** The instrumentation captured two
complete, identical entry/exit blocks, with `HouseClass::Array.Count` back at
**0** at the start of the second — i.e. the array is torn down and rebuilt, not
appended to. This matches the two known call sites (`0x68745E` Read_Scenario_INI
and `0x68ACFF` ScenarioClass::Read_INI) and is why any implementation that
mutates `AISlots` must save and restore the originals across the second call.
**Anything hooking this function must be idempotent or explicitly one-shot.**

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
68815d:  cmp    0x20(%esp),%eax                       ; EAX = houses CREATED so far
688161:  0f 8d 5b 01 00 00  jge    0x6882c2           ; enough AI -> CONTINUE (not break)
688167:  mov    (%ebx),%edi                           ; EDI = Countries[i]
688169:  cmp    $0xffffffff,%edi
68816c:  0f 84 50 01 00 00  je     0x6882c2           ; -1  -> SKIP this slot
688172:  cmp    $0xfffffffd,%edi
688175:  0f 84 47 01 00 00  je     0x6882c2           ; -3  -> SKIP this slot
68817b:  mov    0x20(%ebx),%esi                       ; ESI = Colors[i]  (+0x20 = 8 ints)
68817e:  40                 inc    %eax               ; only on the CREATE path
...
6882c2:  83 c3 04           add    $0x4,%ebx          ; <-- all three jumps land HERE
6882c5:  81 fb bc b2 a8 00  cmp    $0xa8b2bc,%ebx     ; <<< THE CAP
6882cb:  0f 8c 8c fe ff ff  jl     0x68815d
```

**⚠ The sentinels SKIP; they do not terminate the loop.** All three conditional
jumps target `0x6882C2`, which is the `add $0x4,%ebx` **increment** — so a `-1`
or `-3` country means "skip this slot and keep going", not "stop". Equally,
`EAX` is **not** a slot index: it is incremented only on the create path
(`0x68817E`), so it counts *houses created so far*, and the
`cmp 0x20(%esp),%eax` test is "have I made enough AI yet?" — also a continue.

Net behaviour: **the loop always walks all 8 slots**, creating up to `AIPlayers`
houses from whichever slots hold a valid country. An earlier revision of this
entry described the sentinels as terminating the loop; that was wrong and is
corrected here. **Runtime-proven** — see the validation note below, where a live
game had `Countries[] = {-1, 0, 6, -1, -1, -1, -1, -1}` and still produced two
AI houses from slots 1 and 2.

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

**How to lift it — INDEPENDENTLY CONFIRMED, and there is a better way than
relocation.** This page originally recommended relocating `AISlots` into a
larger allocation and rewriting both the base (`0x688158`) and this bound
(`0x6882C5`). A working third-party implementation
(`mmtrt/yrpp-spawner`, `src/Spawner/PlayerLimit16.cpp`, GPL-3.0) hooks
**exactly those two addresses** — arrived at independently — but uses a
**batch-refill** strategy that avoids relocation entirely:

```cpp
DEFINE_HOOK(0x6882C5, PlayerLimit16_AICreate_EndBound, 6)
{
    if (ebx < ADDR_AIS_END) return 0x68815D;   // not done yet, keep looping
    CaptureTemplates();
    int need = aiPlayers - created;
    if (need > 0 && !g_BatchDone && g_TplCount > 0) {
        g_BatchDone = true;
        if (need > EngineAISlots) need = EngineAISlots;
        RefillEngineSlots(need);        // rewrite the SAME 8 slots
        R->EBX(ADDR_AIS_COUNTRY);       // rewind the pointer to the base
        return 0x68815D;                // re-enter the loop
    }
    return 0x6882D1;                    // fall through to Neutral creation
}
```

i.e. when the pointer reaches the end bound, refill the stock 8-wide array with
the next batch of AI and rewind `EBX` to the base. The engine's own loop then
runs a second time over fresh data. No relocation, and no need to find every
other consumer of `0xA8B29C`.

**This is why such builds cap at 16 rather than 25.** The limit is
`2 passes × 8 slots`, enforced by `need` being clamped to `EngineAISlots` and
`g_BatchDone` permitting a single refill — **not** the 32-bit bitfield ceiling,
which sits far above at 30. Turning `g_BatchDone` into a counter would yield
N×8; the bitfield ceiling only becomes the binding constraint past ~30 houses.

**Verified jump targets** (they match the disassembly above instruction for
instruction): `0x68815D` is the loop-condition test
(`cmp 0x20(%esp),%eax`); `0x6882D1` is the `push $0x160b8` that begins Neutral
house creation.

**Downsides of batch-refill — what the second batch loses.** In the reference
implementation the refilled slots are *derived*, not configured:
`eColor[i] = (tplColor + 8 + i) & 15` (colours computed, not user-chosen, and
masked to 16), `t = i % g_TplCount` (countries/teams/difficulty cycle batch 1's
values), and `eStart[i] = (tplStart + i) % 8` with the comment *"Keep starts in
0..7 so parallel assign path never OOB"* — so all houses share the stock 8
start positions and some necessarily co-spawn. It also carries mutable global
state (`g_HaveOrig`, `g_BatchDone`, `g_TplCount`) with a save/restore dance
because `AssignHouses` is called twice. **None of this is inherent to the
technique** — it is a property of that refill function. Since `spawn.ini` now
carries `Multi1..Multi16`, per-house config for the second batch already exists
and a refill that read it would give fully independent countries/colours/teams.

**Confirmed via.** Ghidra-free `objdump` disassembly of vanilla `gamemd.exe`
(sha1 `189a5a86…`), 2026-08-20 — instruction bytes quoted above. **Confirmed.**
Independently corroborated 2026-08-23 by `mmtrt/yrpp-spawner`
`src/Spawner/PlayerLimit16.cpp`, which hooks the same two addresses and whose
`ADDR_AIS_END` constant is `0x00A8B2BC` with the comment *"end of Country[]
scan"* — matching the `Colors[8]`-adjacency conclusion this entry previously
derived arithmetically. That adjacency is therefore now **confirmed**, not
inferred.

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

**Now pinned to real addresses.** The five sub-arrays are contiguous at a
`0x20` (8 × `int`) stride, and the AI count sits just below them:

| Address | Array |
|---|---|
| `0xA8B274` | AI player **count** (not part of the struct) |
| `0xA8B27C` | `Difficulties[8]` |
| `0xA8B29C` | `Countries[8]` |
| `0xA8B2BC` | `Colors[8]` — **also the loop end-bound** at `0x6882C5` |
| `0xA8B2DC` | `Starts[8]` |
| `0xA8B2FC` | `Teams[8]` |

The consumer that enforces the 8 is the pointer compare at **`0x6882C5`** — see
its own entry above for the patch site and the batch-refill alternative.

**⚠ YRpp's `AISlotsStruct` appears mislabelled at this offset.** YRpp declares
`AIDifficulties[8]; StartingSpots[8]; Colours[8]; Starts[8]; Teams[8];`, which
would place `Colours` at `Difficulties + 0x40`. Both the disassembly and the
reference implementation agree `Colours` is at `+0x40` — but that makes YRpp's
**`StartingSpots[8]` the array the engine actually uses as `Countries[8]`**
(`0xA8B29C`). The disassembly is unambiguous on this point: the AI loop does
`mov (%ebx),%edi` then `mov 0xa83c9c,%edx; mov (%edx,%edi,4),%ecx`, i.e. it
indexes `HouseTypeClass::Array` with that value — it is a country index, not a
starting spot. Prefer the raw addresses above over YRpp's field names here.

**Confirmed** from disassembly (2026-08-20) and corroborated by
`mmtrt/yrpp-spawner` `PlayerLimit16.cpp`, whose `ADDR_AIS_*` constants are
exactly the five addresses above.

#### How `spawn.ini` maps onto these arrays — RUNTIME-CONFIRMED

The CnCNet client writes the AI configuration into `spawn.ini`, which the host
broadcasts in a networked game. The mapping to the engine arrays is:

```
AISlots[i]  <->  Multi(i + 1)          (MultiN is 1-BASED)
```

with slots belonging to **human** players left at `-1`. Sections:

| `spawn.ini` section | Engine array |
|---|---|
| `[HouseCountries] MultiN=` | `Countries[8]` @ `0xA8B29C` |
| `[HouseColors] MultiN=` | `Colors[8]` @ `0xA8B2BC` |
| `[HouseHandicaps] MultiN=` | `Difficulties[8]` @ `0xA8B27C` |
| `[SpawnLocations] MultiN=` | `Starts[8]` @ `0xA8B2DC` |
| `[Settings] AIPlayers=` | AI count @ `0xA8B274` |

**Confirmed** by logging both sides of the mapping in two separate live skirmish
games and comparing per slot. Run 2: `spawn.ini` held
`HouseCountries Multi2=2, Multi3=7` and `HouseColors Multi2=0, Multi3=2`, while
the engine read `Countries[] = {-1, 2, 7, -1, …}` and
`Colors[] = {-1, 0, 2, -1, …}` — agreement on every populated slot, across two
runs with different countries and different seeds. This also independently
confirms `0xA8B2BC` is `Colors` (not merely the loop end-bound).

Note the pleasant coincidence that **the engine's "empty slot" sentinel is also
`-1`**, so a config reader that maps "key absent" to `-1` round-trips naturally
against the engine's own convention.

**⚠ Reading these keys with `GetPrivateProfileInt` is unsafe.** That API parses
the value as *unsigned* and documents that a value below zero returns zero — and
`0` is a valid country index (Americans). Read the raw string and parse it.
Likewise, `GetPrivateProfile*` resolves a **bare** filename against the Windows
directory rather than the game directory, so the path must be given as
`.\spawn.ini` or every lookup silently returns its default.

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

## Reference implementation: a working 16-player build (third-party, GPL-3.0)

**`mmtrt/yrpp-spawner`** — a fork of the official CnCNet spawner adding
`src/Spawner/PlayerLimit16.cpp` (~1000 lines), paired with
**`mmtrt/xna-cncnet-client`** (branch `testing`) for the lobby side. Both are
GPL-3.0 forks of the official CnCNet repos. This is currently the most complete
public >8-house implementation for YR and is the best cross-check for anything
on this page.

**Its shape.** Engine-side changes are confined to one file. Per its own header:
expand the `HouseClass` vector to 16; batch-refill `AISlots` so `AIPlayers > 7`
create; rewrite the waypoint house-index table when it holds cell values; cap
`StartingPoints` to the stock 8 and repair corrupt `HouseIndices`; expand
end-game score buffers. Activation is gated on `AIPlayers > 7`,
`NumberStartingPoints > 8`, or an explicit force flag.

**Hook map** (all `DEFINE_HOOK`, YR 1.001):

| Cluster | Addresses | Purpose |
|---|---|---|
| House array | `0x4F61E6`, `0x5EEA19`, `0x640F46` | expand `HouseClass::Array` to 16 |
| AI creation | `0x688158`, `0x6882C5` | the batch-refill loop (see entry above) |
| Waypoints | `0x5D6CBF`, `0x5D6D02` | house-index table repair |
| Load screen | `0x552D60`, `0x553687` | progress draw + re-clamp |
| Score screen | `0x5C98F1`, `0x5C9911`, `0x5C9AA0`, `0x5C9D47`, `0x5C9DF4`, `0x5C9E8A`, `0x5C9EC9`, `0x5C9F25`, `0x5C9FDD`, `0x46DAE4` | 16-row score buffers |
| Misc guards | `0x4F6032`, `0x650B5A`, `0x686A2E`, `0x687572` | null-checks / redirects |

`HouseClass::Array` field offsets it relies on (consistent with the
`0xA80228` object address documented above): items `+0x4` (`0xA8022C`),
capacity `+0x8`, `IsAllocated` `+0xC`, count `+0x10` (`0xA80238`).

**It contradicts this page on the starting-point counters.** This page
recommended lifting both `i < 8` counters (`0x68AF45`, `0x6883E6`). The
reference implementation hooks **neither** — it deliberately *keeps* the stock
8 cap and repairs the downstream `HouseIndices` table instead, and forces AI
start slots into `0..7`. Since that build reportedly works, **lifting the
counters is evidently not required**, and the recommendation in this page's
practical summary should be treated as one option rather than a prerequisite.

**Two known-unsolved problems** (per its author, 2026-08): the loading-screen
player indicators and the score screen both still cap at 8 in *display*, even
though the score *buffers* were widened to 16 rows.
- For the loading screen, the module's own header states the minimap
  multi-colour marks come from the **map Preview on the client side**, not the
  engine — so that one is likely not fixable in a spawner/DLL at all.
- For the score screen, its hooks span `0x5C98F1`–`0x5C9FDD`. **The Antares PDB
  symbol map names `0x5CA110` `Game_GetMultiplayerScoreScreenBar`** — an
  unhooked draw-side function immediately past the end of that range. If the
  16-row buffers are correct but the display still caps, that is the obvious
  next candidate. **Untested lead**, offered here because it comes from a
  symbol source (the Antares PDB) that upstream may not have.

**Online status: UNTESTED.** The fork's spawn.ini schema is widened to 16
(`[Other1]..[Other15]`, `Multi1..Multi16`, `MultiN_Alliances`), but **no
network-layer files are modified**, and its author confirms (2026-08) that no
online testing has been done. Do **not** assume >8 works in a networked game on
the strength of this implementation — see the section below for why desync, not
connection count, is the thing to establish.

---

## Online (>8 houses in a networked game) — what actually gates it

The networking cap noted above bounds **human connections**, not houses. YR
multiplayer is lockstep-deterministic: each client transmits only its own
commands and every client simulates the whole world, AI included. AI houses are
therefore *not* network peers. A game of, say, 4 humans + 20 AI never approaches
`Connection[7]` / `ListAddress[8]`. **So ">8 houses online" is tractable in the
comp-stomp shape (few humans, many AI) even though ">8 humans" is not.**

**The gating problem online is desync, not connection count.** Three concrete
requirements fall out:

1. **The house set must come from a host-authoritative, broadcast channel**
   (`spawn.ini`), never from a client-local config file. If two clients disagree
   on how many AI exist, they build different house arrays and desync
   immediately. This is the single biggest architectural constraint — a
   "read our own INI" design that works offline is unusable online.
2. **Only the synced RNG may touch game state** —
   `ScenarioClass::Instance->Random`. A private RNG (or one shared between game
   logic and render-time randomness) desyncs. This is a known, repeatedly-hit
   failure mode in YR DLLs.
3. **Identical builds on every client**, with deterministic iteration order
   (never iterate by pointer address or hash order when creating houses).

**Unverified / open.** Whether the per-player frame-sync queues are sized per
*connection* (harmless — humans stay ≤8) or per *house* (a hard blocker) is
**not established**. A community RE vet described them as "per player, so size 7,"
which reads as per-connection, but this has not been confirmed against the
binary. **Anyone attempting online >8 houses must settle this first.**

### `SessionClass::GameMode` — the offline/online gate

The engine's own online/offline discriminator, useful for staging a rollout or
providing a kill-switch, and reusable by any YR DLL:

```cpp
// YRpp GeneralDefinitions.h
enum class GameMode : unsigned int {
    Campaign = 0x0, LAN = 0x3, Internet = 0x4, Skirmish = 0x5,
};
// YRpp SessionClass.h
static constexpr reference<SessionClass, 0xA8B238u> const Instance{};
GameMode GameMode;   // first field, offset 0
```

So `SessionClass::Instance->GameMode` is simply the DWORD at `0xA8B238`.
**Vanilla `AssignHouses` already branches on it** — `0x687FCE` is
`cmpl $0x4,0xa8b238`, i.e. `GameMode == Internet` — which makes this a
well-precedented place to diverge behaviour. A DLL can go inert online with
`if (SessionClass::Instance->GameMode == GameMode::Internet) return 0;`.

**What it does *not* tell you — easily mistaken.** `GameMode` distinguishes the
*lobby/session type*, **not** whether the simulation must be deterministic.
`LAN` (3) and `Internet` (4) are both networked and both desync-sensitive;
`Skirmish` (5) and `Campaign` (0) are single-client. Gating only on `Internet`
therefore leaves LAN exposed — check for *both* networked modes if the intent is
"am I in a lockstep game." Note also this is a **runtime session** property: it
is meaningless before a session is set up, so do not read it at DLL-init time.

**Confirmed via.** YRpp `GeneralDefinitions.h:670` (enum) and `SessionClass.h:54,56`
(instance address `0xA8B238`, `GameMode` as first field); the `0x687FCE` branch
from the `gamemd.exe` disassembly above, where `0xA8B238` independently appears
as the `this` pointer passed to `0x69A310`. **Confirmed.**

---

## Practical summary: what a >8-player (offline, AI) build must change

1. Reimplement `AssignHouses` (`0x687F10`) looping past 8 — the Vinifera
   `Assign_Houses()` is the structural blueprint, but **use YR's own verified
   wiring**: allocate `0x160B8` bytes, call the ctor at `0x4F54A0`
   (`__thiscall`, arg = `HouseTypeClass*`). **No colour-picker fix is needed
   inside this function on YR** (see the correction) — but do lift the AI-loop
   pointer bound at `0x6882C5`, which is the actual >7-AI wall.
2. **Either** lift both starting-point counter loops — `0x68AF45` (`i < 8`) and
   `0x6883E6` (`i < 8`), the latter min'd against the house total at `0x68841F`
   — **or** do what the working reference implementation does and *keep* the
   stock 8 cap, repairing the downstream `HouseIndices` table and forcing start
   slots into `0..7` instead. The second route is proven to work; the first is
   untested. Note the trade-off: capping means houses share the 8 stock start
   positions, so some necessarily co-spawn.
3. Adopt/borrow Phobos's dynamic-waypoint subsystem (or place start waypoints
   0..N on the map) so >8 start positions exist.
4. Widen or bypass `GameModeOptionsClass::AISlots[8]` and
   `ScenarioClass::StartingPoints[8]` / `HouseIndices[16]`.
5. Stay under ~30 total houses unless you also widen every per-house 32-bit
   bitfield (`HouseClass::Allies` et al.).
6. **Offline first, but online is not ruled out** — the network layer bounds
   human *connections*, not houses, so a few humans + many AI stays under
   `ListAddress[8]` / `Connection[7]`. Going online turns desync (not the
   connection cap) into the gating problem — see the online section above.
   Leaving that network layer untouched is fine and expected either way.

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
