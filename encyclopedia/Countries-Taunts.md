# Subsystem: Countries & Taunts

Everything governing **how many countries (`HouseTypeClass`) the engine can
actually address**, and the taunt playback path — which is here because taunts
turn out to be a *country-index* problem, not an audio problem.

This page exists because "the country limit" is not one number. Country
*storage* is unbounded; what is bounded is the **width of the fields the index
is packed into**, and there are exactly two of them, at two different widths, in
two unrelated subsystems.

Entries sorted by address. Structural findings with no single address are
grouped at the end.

---

## The one structural fact that organises this page

**Nothing caps the number of countries. Two field widths cap the number of
*addressable* countries.**

`HouseTypeClass::Array` (`0xA83C98`) is an `AbstractTypeClass` array that grows
without bound, so `[CountryName]` sections keep loading and their per-country
tags keep working past any limit. What breaks is every place the engine stores a
country *index* or a country *set*:

| Representation | Width | Ceiling | What breaks |
|---|---|---|---|
| `1u << HouseTypeClass::ArrayIndex2` into a `DWORD` | 32 bits | **32 countries** | `Owner=`, `RequiredHouses=`, `ForbiddenHouses=`, `SecretHouses=` |
| a **nibble** in the taunt network byte | 4 bits | **16 countries** | taunts |

This produces a distinctive and much-reported symptom: **a country defined past
index 32 works "except that its ownership tags silently behave like country
0."** On x86 `shl` masks the shift count to 5 bits, so index 32 aliases onto
index 0 — countries start *sharing* ownership bits rather than crashing. The
per-country `[CountryName]` section is honoured the whole time, which makes the
failure look like a parser bug when it is an arithmetic one.

**Do not confuse this with the player/house limit.** `IndexBitfield<HouseClass*>`
(`HouseClass::Allies`, `AltAllies`, `TechnoClass::DisplayProductionTo`, …) is
indexed by *house* `ArrayIndex` and caps **houses/players** at 32 — see
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md), whose "Do not confuse
the two bitfield axes" note points here. `IndexBitfield<HouseTypeClass*>` is
indexed by *country* `ArrayIndex2` and caps **countries** at 32. The two are
independent: many houses may share one country, and raising either does nothing
for the other.

**Confirmed via.** YRpp `HouseTypeClass.h:68` (`int ArrayIndex2; //dunno why`),
`HouseClass.h:637-643` (`InRequiredHouses`/`InForbiddenHouses` =
`1u << this->Type->ArrayIndex2`), `ObjectClass.h:91` (`GetTypeOwners` —
*"returns the data for `IndexBitfield<HouseTypeClass*>`"*),
`Helpers/Template.h` (`IndexBitfield` = `1u << ArrayIndex` over a `DWORD data`),
`Audio.h:106` (`TauntDataStruct`). **Confirmed** from headers. The 32-aliasing
behaviour follows from the x86 `shl` masking rule; **confirmed** arithmetically,
**not** observed in-game as part of this write-up.

---

### `0x4750D0` — `INIClass::ReadHouseTypesList` (the country-set choke point)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `INIClass_ReadHouseTypesList` | 0x7 | `Misc/Bugfixes.Buffer.cpp` (at `0x4750EC`) |
| Antares | `INIClass_ReadHouseTypesList_Strtok` | 0x5 | `Misc/Bugfixes.Buffer.cpp` (at `0x475107`) |

*No framework hooks `0x4750D0` itself* — Antares' two hooks sit **inside** the
function (a buffer bugfix), not at its entry.

**What it does.** Parses a comma-separated list of country names from an INI
value and returns a **`DWORD` bitfield**, one bit per country, via
`1u << ArrayIndex2`. This is *the* single conversion point from country names to
a country set anywhere in the game.

**Why it matters.** A whole-binary scan for `E8`/`E9` rel32 targeting it finds
**exactly four call sites**:

| Call site | Tag string | Stores result to |
|---|---|---|
| `0x714531` | `RequiredHouses` (`0x843BB4`) | `[type+0xDA0]` |
| `0x71454B` | `SecretHouses` (`0x843BA4`) | `[type+0xDA8]` |
| `0x714565` | `ForbiddenHouses` (`0x843B94`) | `[type+0xDA4]` |
| `0x7149F0` | `Owner` (`0x843994`) | `[type+0x6CC]` |

Four write sites for the entire country-set surface of the game. Anyone widening
the country limit starts here, not at the consumers.

**What it does *not* do — easily mistaken.** It does **not** enforce a country
count and contains no `32` to raise. The limit is created *by the return type*:
a `DWORD`. Nor is this the parser for `Allies=` in maps — that is
`ReadHousesList` at `0x475260`, which is indexed by **house**, not country, and
belongs to the other bitfield axis entirely. The two parsers are 0x190 bytes
apart and easy to mix up.

**Register / calling convention.** `__thiscall`, `ECX` = the `INIClass`; stack
args (section, key, default-bitfield), returns the bitfield in `EAX`.

**Confirmed via.** Address and semantics: YRpp `CCINIClass.h:216`
(`INI_READ(HouseTypesList, 0x4750D0)` with the comment *"Parses a list of
Countries and returns a bitfield, i.e. Owner= or RequiredHouses="*).
**Confirmed** from header. Call sites, tag strings and store offsets: `objdump`
of vanilla `gamemd.exe` (sha1 `189a5a86…`), 2026-08-20 — **confirmed**, and the
three consecutive offsets `+0xDA0/+0xDA4/+0xDA8` cross-check exactly against
YRpp `TechnoTypeClass.h:508-510`, which declares `RequiredHouses`,
`ForbiddenHouses`, `SecretHouses` as consecutive `DWORD`s. ⚠ `Owner` at
`[type+0x6CC]` has **no** YRpp cross-check and is **inferred** from the
disassembly pattern alone.

---

### `0x48DA3B` — taunt playback, local path

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `sub_48D1E0_PlayTaunt` | 0x5 | `Ext/HouseType/Hooks.cpp` |

**What it does.** One of three call sites of `PlayTaunt` (`0x752B70`). Antares
replaces it, reading the country as a **full `int`** from the global
`0xA8D671` instead of letting the 4-bit nibble decode happen.

The enclosing function `0x48D1E0` has exactly one caller, `0x48D0B9`.

**Confirmed via.** Antares `Ext/HouseType/Hooks.cpp` @ `9f25bdb`. **Confirmed**
from source. Caller census: `objdump` scan. **Confirmed.** ⚠ What `0xA8D671`
*is* — specifically, whether it is where Antares' widened outgoing field
(`0x536438`, below) lands on receive — is **unverified**. The address is
unaligned, which is consistent with a byte offset into a received-message
struct, but that is **inference**.

---

### `0x53639A` — the taunt gate (multiplayer-only enforcement)

**Framework names** — *no framework hooks this address.* Not in the registry.

**What it does.** Gates `TauntCommandClass::Execute` on game mode and two INI
options:

```asm
53639a:  mov 0xa8d110,%cl   ; LANTaunts
5363a0:  test %cl,%cl
5363a2:  mov 0xa8b238,%ecx  ; SessionClass::GameMode (first DWORD of SessionClass)
5363a8:  je 0x5363af
5363aa:  cmp $0x3,%ecx      ; GameMode::LAN       -> allowed
5363ad:  je 0x5363c6
5363af:  mov 0xa8d111,%dl   ; WOLTaunts
5363b5:  test %dl,%dl
5363b7:  je 0x536575        ; bail
5363bd:  cmp $0x4,%ecx      ; GameMode::Internet  -> allowed
5363c0:  jne 0x536575       ; bail
```

i.e. `allowed = (LANTaunts && GameMode==LAN) || (WOLTaunts && GameMode==Internet)`.

The same gate shape is duplicated on the receive side at `0x64A739`–`0x64A759`.

**Why it matters.** `GameMode::Skirmish` is **`5`** (YRpp
`GeneralDefinitions.h:872-878`: `Campaign=0, LAN=3, Internet=4, Skirmish=5`), so
it satisfies neither arm. **This is the entire reason taunts do not work
offline** — there is no separate "taunts disabled in skirmish" logic, just two
equality tests that skirmish cannot pass. Enabling offline taunts means making
these compares (and the two at `0x64A747`/`0x64A756`) accept `5`. Four compares,
no framework contention.

**What it does *not* do — easily mistaken.** Passing this gate does **not**
mean a taunt will be *heard*: `PlayTaunt` (`0x752B70`) applies its own
independent clamps afterwards. And enabling it offline exercises only the
**local send/playback** path (`0x536438`); it does **not** exercise the
network-receive path (`0x64A75E`), so it cannot be used to test receive-side
country-index behaviour.

**Confirmed via.** `objdump` of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-20 — instruction bytes quoted. **Confirmed.** `GameMode` enum values:
YRpp `GeneralDefinitions.h`. **Confirmed** from header. The identification of
`0xA8D110`/`0xA8D111` as `LANTaunts`/`WOLTaunts`: see the structural note below —
**confirmed** arithmetically.

---

### `0x536438` — `TauntCommandClass::Execute` (the packing site)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TauntCommandClass_Execute` | 0x5 | `Ext/HouseType/Hooks.cpp` |

**What it does.** The local player triggers a taunt. Vanilla packs the country
and taunt index into **one byte** and places it in the outgoing packet:

```asm
536427:  mov 0x4b(%eax),%al   ; player->Country
53642a:  shl $0x4,%al         ; country -> HIGH NIBBLE
53642d:  xor %al,%cl
53642f:  and $0xf,%cl         ; (the standard xor/and/xor merge idiom:
536432:  xor %al,%cl          ;  result = (al & 0xF0) | (cl & 0x0F))
536434:  mov %cl,0x44(%esp)   ; one byte into the packet
536438:  call 0x752b70        ; ...and play it locally
```

**This `shl $0x4` is the 16-country taunt ceiling.** There is no `cmp $0x10`
anywhere; grepping for 16 will never find it.

Antares' hook keeps the vanilla byte intact (for compatibility) and
*additionally* writes the **unclamped full `int`** country index at packet offset
`+0x4D` — its own comment: *"put the unclamped country index into the outgoing
packet"* — sourcing the country from `SessionClass::Instance.StartSpots[0]->Country`
rather than from `player->Country`.

**What it does *not* do — easily mistaken.** Antares fixing *this* site does
**not** fix taunts for countries ≥16 in general. This is the **send** side. See
`0x64A75E`.

**Confirmed via.** Disassembly of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-20 — bytes quoted. **Confirmed.** Antares behaviour: `Ext/HouseType/Hooks.cpp`
@ `9f25bdb` (`R->Stack(0x4D, idxCountry)`). **Confirmed** from source. ⚠ That
`+0x4D` is a field of the *network packet* (rather than local stack scratch) is
**inferred** from the surrounding stores at `0x53640A` (`+0x45`) and `0x536421`
(`+0x49`) and the length `0x1D` written at `0x5363D1`; **not** confirmed against
a packet-struct definition.

---

### `0x64A75E` — the third `PlayTaunt` caller (**hooked by nobody**)

**Framework names** — *no framework hooks this address.* Not in the registry.

**What it does.** Sits in a message dispatcher (`cmp $0x78,%eax` at `0x64A734`,
among a run of message-type compares `0x64`, `0x6D`, `0x6E`, `0x74`) behind a
duplicate of the `0x53639A` gate, and feeds `PlayTaunt` the **raw packed byte
straight out of a message struct**:

```asm
64a75b:  mov 0x19(%esi),%cl   ; packed byte at msg+0x19
64a75e:  call 0x752b70
```

**Why it matters — the headline finding of this page.** `PlayTaunt` has exactly
**three** callers in the whole binary:

```
0x48DA3B  ← Antares hooks      0x536438  ← Antares hooks      0x64A75E  ← nobody
```

Antares widens the two sites that *construct* the country index themselves, but
this one *decodes* it from the wire — so it still passes a byte that Antares'
`PlayTaunt` replacement reads through the 4-bit `TauntDataStruct::countryIdx`.

⚠ **This is a strong hypothesis, not a confirmed fact:** that `0x64A75E` is the
path that plays a *remote* player's taunt, and therefore that countries ≥16 wrap
mod 16 here even under Antares. It is consistent with the code — a message
dispatcher, a raw wire byte, the same gate — but has **not** been reproduced
in-game, because doing so requires two networked clients. Anyone with a two-
client setup should confirm or refute it and update this entry.

**What it does *not* do — easily mistaken.** It is **not** reachable offline. A
skirmish game never produces the message that drives it, so enabling offline
taunts (see `0x53639A`) will not exercise this path and will not reproduce the
16-country limit.

**Confirmed via.** Caller census by whole-binary `E8`/`E9` rel32 scan of vanilla
`gamemd.exe` (sha1 `189a5a86…`), 2026-08-20 — **confirmed**, three callers, and
absolute-address references: none. Instruction bytes: **confirmed**. The "not
hooked by any framework" claim: checked against `registry/hooks.csv` —
**confirmed** for the frameworks currently in the registry. The *meaning* of the
dispatcher (remote-taunt receive) is **inferred from context and unverified**.

---

### `0x752B70` — `PlayTaunt`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `PlayTaunt` | 0x5 | `Ext/HouseType/Hooks.cpp` |
| Ares | `HTExt_GetTaunt` | 0x6 | `Ext/HouseType/Hooks.cpp` (at `0x752BA1`) |

**What it does (vanilla).** Takes a single **packed byte** in `ECX` and plays a
taunt WAV:

```asm
752b8d:  mov %cl,%al ; and $0xf,%al     ; low nibble  = taunt number
752b91:  cmp $0x1 / cmp $0x8            ; clamped to 1..8
752ba1:  sar $0x4,%ecx ; and $0xf,%ecx  ; high nibble = COUNTRY index
752ba7:  cmp $0x9,%ecx ; ja fail        ; clamped to 10
752bb0:  jmp *0x752c6c(,%ecx,4)         ; 10-entry jump table
```

The jump table's ten entries each push a **hardcoded filename format string**:

| Country idx | String | Value |
|---|---|---|
| 0 | `0x846770` | `taunts\tauam%02i.wav` |
| 1 | `0x846758` | `taunts\tauko%02i.wav` |
| 2 | `0x846740` | `taunts\taufr%02i.wav` |
| 3 | `0x846728` | `taunts\tauge%02i.wav` |
| 4 | `0x846710` | `taunts\taubr%02i.wav` |
| 5 | `0x8466F8` | `taunts\tauli%02i.wav` |
| 6 | `0x8466E0` | `taunts\tauir%02i.wav` |
| 7 | `0x8466C8` | `taunts\taucu%02i.wav` |
| 8 | `0x8466B0` | `taunts\tauru%02i.wav` |
| 9 | `0x846698` | `taunts\tauyu%02i.wav` |

The low nibble is then formatted into `%02i`, so the *vanilla* file naming is
`tau<country><taunt>.wav` with taunt 1–8.

**What the Ares-lineage hook does.** Antares replaces the whole body: the jump
table gives way to the per-`HouseType` `File.Taunt` tag (default table in
`Ext/HouseType/Body.cpp`, same ten prefixes), and the guards become
`idxTaunt > 9 || idxCountry < 0`. So the *10-country* limit is genuinely gone.

**What it does *not* do — easily mistaken.** Antares' replacement does **not**
remove the 16-country limit, because it still reads
`TauntDataStruct::countryIdx`, a **4-bit** bitfield — the widening lives in its
*callers*, not here. Reading the Antares source alone strongly suggests the
limit is fixed; it is fixed on two of three paths.

⚠ **Latent out-of-bounds read in the Ares-lineage hook.** `PlayCountryTaunt`
guards `idxCountry < 0` but has **no upper-bound check** before
`HouseTypeClass::Array.Items[idxCountry]`. Since the whole point of the
`0x536438` hook is that the index now arrives unclamped, a malformed or
INI-mismatched packet indexes off the end of the array and dereferences whatever
it finds. **Found by source reading; not reproduced.** Worth reporting upstream.

**Register / calling convention.** `__fastcall`-ish: `ECX` = the packed byte
(`TauntDataStruct`). Returns `bool` in `EAX`. Vanilla failure path is
`xor %eax,%eax` at `0x752C63`; the function's tail is `0x752C68`.

**Confirmed via.** Disassembly of vanilla `gamemd.exe` (sha1 `189a5a86…`),
2026-08-20 — bytes and jump table quoted, format strings read directly from the
binary at the addresses listed. **Confirmed.** `TauntDataStruct` bitfield widths:
YRpp `Audio.h:106`. **Confirmed** from header. Antares behaviour and the missing
bound check: `Ext/HouseType/Hooks.cpp` @ `9f25bdb`. **Confirmed** from source.

---

## Structural findings (no single hook address)

### `TauntDataStruct` — the 4-bit wire format
```cpp
struct TauntDataStruct {
    DWORD tauntIdx   : 4;
    DWORD countryIdx : 4;
};
```
(YRpp `Audio.h:106`.) The taunt travels as **one byte**: country in the high
nibble, taunt number in the low. This is a *network wire format*, so widening it
is desync-relevant — both peers must agree. The Ares-lineage precedent is
additive: keep writing the vanilla byte unchanged, carry the wide index in a
separate field. **Confirmed** from header.

### `SessionClass+0x1ED8/+0x1ED9` — `LANTaunts` / `WOLTaunts`
Read from the **`[MultiPlayer]`** section of the game's options INI:

| Global | `SessionClass` offset | INI key (string) |
|---|---|---|
| `0xA8D110` | `+0x1ED8` | `LANTaunts` (`0x83F130`) |
| `0xA8D111` | `+0x1ED9` | `WOLTaunts` (`0x83F13C`) |

Read sites: `0x69838E` / `0x69836D` (and again at `0x699486` / `0x699470`);
section string `MultiPlayer` at `0x82642C`. The arithmetic closes exactly —
`0xA8B238 + 0x1ED8 = 0xA8D110` — which independently re-confirms
[PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md)'s identification of
`0xA8B238` as the `SessionClass` instance. **Confirmed** — strings read from the
binary, offsets from disassembly, arithmetic checked.

### The country-set consumer census (first cut, ⚠ HEURISTIC)
Scanning for `mod=10` disp32 operands equal to the country-bitfield field
offsets gives a starting census of read sites:

| Field | Offset | Candidates | Clusters |
|---|---|---|---|
| `RequiredHouses` | `+0xDA0` | 15 | `0x4F79E4`–`0x4F7A59`, `0x505230`/`0x505598`/`0x505CC7`, `0x674BAA`, `0x6D1D2A`/`0x6D26D4`, `0x6DADA4`, `0x711633` |
| `ForbiddenHouses` | `+0xDA4` | 12 | `0x4F7A77`, `0x505253`/`0x5055B8`, `0x617C58`, `0x6D1D35`/`0x6D1E48`/`0x6D268B`/`0x6D26A8`/`0x6D26CE`, `0x711639` |
| `SecretHouses` | `+0xDA8` | 7 | `0x6D1D24`/`0x6D1E3D`/`0x6D269D`/`0x6D26DA`, `0x71163F` |

The `0x4F79E4`–`0x4F7A77` cluster falls inside **`HouseClass::CanBuild`**
(`0x4F7870`, see [Buildability-Prerequisites.md](Buildability-Prerequisites.md))
— the expected primary consumer, which is the main reason to trust the scan as a
starting point. **This is a byte-pattern scan, not a disassembly:** every address
must be disassembled and classified (read / write / false positive) before use.
The equivalent scan for `Owner` (`+0x6CC`) returned 74 candidates and is **too
noisy to be useful** — `0x6CC` is a common displacement; that field needs a
different approach, starting from `ObjectClass::GetTypeOwners`.

### `ObjectClass::GetTypeOwners` is an `R0` stub in YRpp
`ObjectClass.h:91` declares it `virtual DWORD GetTypeOwners() const R0`. Like
every `R0`/`RX`-declared virtual, **it has no address behind it** — calling it
qualified from a DLL silently returns 0 rather than reaching the engine. Reach
it by vtable slot or by its real address. The same footgun is documented for
`ObjectClass::Select` in [Selection-Mouse.md](Selection-Mouse.md).
**Confirmed** from header.

---

## Practical summary: what a >32-country / >16-taunt build must change

1. **Do not widen the engine fields in place.** `[type+0xDA0]` and friends sit in
   a fixed `TechnoTypeClass` layout that Phobos, Antares and every other DLL read
   directly. Use a side table keyed by type, and keep the engine `DWORD` as a
   truncated shadow so unhooked code degrades to vanilla behaviour instead of
   corrupting.
2. **Parse at `0x4750D0`'s four call sites** (`0x714531`, `0x71454B`,
   `0x714565`, `0x7149F0`) — the whole country-set write surface.
3. **Convert read sites in dependency order**, `HouseClass::CanBuild`
   (`0x4F7870`) first; census above, unverified.
4. **For taunts, `0x64A75E` is the unclaimed address** — the only `PlayTaunt`
   caller no framework has taken, and the leading suspect for the residual
   16-country limit under Antares.
5. **Treat the taunt byte as a wire format.** Additive fields only; a mismatch
   must degrade to silence, never to divergent game state.
6. **Offline taunts are four compares** (`0x5363AA`, `0x5363BD`, `0x64A747`,
   `0x64A756`) accepting `GameMode::Skirmish = 5` — but they exercise the send
   path only, and cannot be used to test item 4.

**Overall status: partially confirmed.** All addresses, instruction bytes,
strings and field offsets on this page are confirmed by disassembly of vanilla
`gamemd.exe` (sha1 `189a5a868b3cef8d3d1a58ac3cf0a5241675e4ea`) on 2026-08-20,
cross-checked against YRpp headers and Antares `9f25bdb` where noted. The
**unverified** claims, all flagged ⚠ above, are: the meaning of the `0x64A75E`
dispatcher; the `+0x4D` → `0xA8D671` packet correspondence; `Owner` at
`+0x6CC`; the consumer census; and the Antares OOB read. Nothing on this page
has been tested in-game.
