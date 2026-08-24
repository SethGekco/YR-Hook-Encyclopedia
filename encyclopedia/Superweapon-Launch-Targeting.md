# Superweapon launch & targeting

How a superweapon gets from "player owns it" to "it went off at a cell", and
where a third party can observe or veto that without fighting an incumbent
framework.

**Structural fact that shapes this whole page: inhibitors, designators and
launch-site range have NO address in `gamemd.exe`.** They are not engine
features. They are Ares-0.A-era C++ implemented independently inside
**Antares** (`src/Misc/SWTypes.cpp:231-260`) and, redundantly, inside **Phobos**
(`src/Ext/SWType/SWHelpers.cpp:47-132`). Searching the binary for them finds
nothing. Anyone extending that behaviour is extending a *framework*, not the
engine — which is why the veto seams below matter.

---

### `0x4FAE50` — `HouseClass::Fire_SW`  ⚠ the universal launch funnel, entry unhooked

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `HouseClass_SWFire_PreDependent` | 0x6 | Ext/SWType/Hooks.cpp |
| Ares | `HouseClass_SWFire_PreDependent` | 0x6 | Ext/SWType/Hooks.cpp |

⚠ Both of those are at **`0x4FAE72`** — `+0x22` *inside* the function. **The
entry `0x4FAE50` itself is hooked by no framework in the registry.**

**What it does.** Every superweapon launch in the game passes through here.
**17 call sites**, from an objdump census:

| Sites | Path |
|---|---|
| `0x4C78F3` | `RespondToEvent(SpecialPlace)` — the network-synced player-click path |
| `0x509ACD`, `0x509BBB`, `0x509BF8`, `0x509CAB`, `0x509DEB`, `0x509EA8`, `0x509F55`, `0x50A13E`, `0x50A334`, `0x50A480` | `HouseClass` AI superweapon firing, one per vanilla SW |
| `0x6EFDB4`, `0x6F0011`, `0x6F0068`, `0x6F02B6`, `0x6F030D` | AI script / team-mission SW actions |
| `0x4FAE3F` | internal tail-call |

Framework launch paths converge here too, which is what makes a single hook
sufficient: Antares' `SWTypeExt::TryFire` ends in `pOwner->Fire_SW(...)`
(`Hooks.Targeting.cpp:619`), and YRpp's `Fire_SW` is `JMP_THIS(0x4FAE50)` — a
direct call to the game address, not into Antares. Phobos' SW-sidebar button and
its trigger actions `505`/`506` queue `EventType::SpecialPlace`, arriving via
`0x4C78F3`.

**What it does *not* do — easily mistaken.** It is **not** the cursor or the
click. A veto here stops the launch but leaves the cursor reading "allowed" and
silently eats the click; the UI layers are separate addresses (below). It is
also not where a superweapon's *effect* is chosen — that is
`SuperClass::Launch` (`0x6CC390`).

**Register / calling convention.** `__thiscall bool Fire_SW(int idx, CellStruct const& coords)`.
At entry (nothing pushed): `ECX` = `HouseClass*`, `[esp+4]` = SW index,
`[esp+8]` = `CellStruct*`. Stolen bytes **7**, landing on an instruction
boundary:

```
4fae50:  53              push %ebx
4fae51:  8b d9           mov  %ebx,%ecx
4fae53:  8b 4c 24 08     mov  0x8(%esp),%ecx
```

**⚠ Clean-abort recipe, and the trap.** To refuse a launch, set `AL = 0` and
jump **`0x4FAEF3`** — a bare `ret $8`, the correct cleanup for two dword args
from a pristine entry stack.

Do **not** jump to the real epilogue at `0x4FAEED`:

```
4faeed:  5f 5e 5d        pop edi; pop esi; pop ebp
4faef0:  b0 01           mov $0x1,%al
4faef2:  5b              pop ebx
4faef3:  c2 08 00        ret $8
```

Returning a jump address means the stolen bytes never execute, so at hook time
none of those four registers have been pushed. Landing on `0x4FAEED` pops four
values that were never pushed and corrupts the caller's stack.

**Determinism.** This sits *downstream* of the event queue, so every client
reaches it on the same frame with the same state. A veto decided here is
lockstep-safe by position, not by care. Deciding at the cursor instead would
not be.

**Confirmed via.** objdump of vanilla `gamemd.exe` (call-site census, stolen
bytes, epilogue); Antares source at the cited lines; registry query for
contention; **in-game skirmish** — a DLL hooking this entry alongside
Antares+Phobos+13 other Syringe DLLs loaded clean, vetoed launches correctly,
and produced zero access violations.

---

### `0x4AC21C` — `DisplayClass::LeftMouseButtonUp`, superweapon convergence point

**Framework names.** None. Unhooked by every framework in the registry.
Antares hooks `0x4AC20C`, 16 bytes earlier.

**What it does.** This is where both the framework path and the vanilla path
*converge* after deciding which superweapon a click belongs to:

```
4ac20c:  mov  0x9c(%esp),%ecx      <-- Antares' hook
4ac213:  call 0x6ceeb0             <-- SuperWeaponTypeClass::FindFirstOfAction
4ac218:  test %eax,%eax
4ac21a:  je   0x4ac294
4ac21c:  mov  0x98(%eax),%edx      <-- convergence: EAX = SuperWeaponTypeClass*
4ac222:  mov  0x94(%esp),%ecx      <-- the target cell
...      builds EventClass(house, SpecialPlace, swIdx, cell)
4ac294:  <no-superweapon path>
```

Antares' `0x4AC20C` hook returns either `0x4AC21C` (a superweapon resolved) or
`0x4AC294` (none); vanilla's own `test/je` reaches the same two. So a hook at
`0x4AC21C` runs **on both paths, after either has decided** — the general
"downstream convergence point" technique for coexisting with a framework that
owns an address.

Stolen bytes **6** (`8b 90 98 00 00 00`). `ESP` is unchanged between `0x4AC21C`
and `0x4AC222`, so the cell the game is about to place in the event is readable
at `[esp+0x94]`. Refusing by returning `0x4AC294` means the `SpecialPlace` event
is never queued at all.

**What it does *not* do.** It is client-side and pre-network. Refusing here is
cosmetic plus latency, **not** enforcement — an AI or a remote player never
passes through it. Pair it with `0x4FAE50`.

**Confirmed via.** objdump; Antares `Ext/SWType/Hooks.cpp:167-192`; in-game.

---

### `SuperWeaponTypeClass::GetAction` — vtable slot `0x7F40FC`  ⚠ 4-byte prologue, do NOT code-hook `0x6CEF80`

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SuperWeaponTypeClass_GetAction` | 0x7 | Ext/SWType/Hooks.cpp |

Antares hooks **`0x6CEF84`**. The vtable slot itself is unclaimed.

**⚠ The trap.** The function entry is `0x6CEF80` and its prologue is **four
bytes**, not five:

```
6cef80:  56           push %esi        (1)
6cef81:  57           push %edi        (1)
6cef82:  8b f9        mov  %ecx,%edi   (2)
6cef84:  83 bf ...    cmpl $0xa,...    <-- Antares' hook starts here
```

A 5-byte Syringe `jmp` at `0x6CEF80` overwrites the first byte of the
instruction at `0x6CEF84`, where Antares writes its own `jmp`. Whichever DLL
injects second corrupts the other — a **load-order-dependent crash, not a build
error**. Counting instructions instead of bytes is what makes this one easy to
get wrong.

**What to do instead.** `GetAction` is a virtual with **no `call rel32` anywhere
in `gamemd.exe`**; its only absolute reference is vtable slot **`0x7F40FC`**
(verified to contain `0x6CEF80`). Replace the slot with
`DEFINE_FUNCTION_JUMP(VTABLE, 0x7F40FC, wrapper)` and have the wrapper call
`0x6CEF80` directly. Antares' in-function hook still runs inside that call and
still decides first; a wrapper can then further restrict. Antares' code is
untouched, so there is no ordering hazard.

(Call the game address directly rather than through a YRpp qualified call: YRpp
declares this virtual `R0`, so a qualified non-virtual call silently no-ops —
see [Selection-Mouse.md](Selection-Mouse.md) for the same footgun on
`ObjectClass::Select`.)

**Return values — two vocabularies.** Vanilla returns `0x46`
(`Action::NoForceShield`, at `0x6CEFCA`) for "this superweapon may not fire
here"; the enum name reflects which family owns the cursor, but the engine uses
it for every SW. Antares defines its own `SuperWeaponAllowed = 0x7F` /
`SuperWeaponDisallowed = 0x7E` (`src/Misc/Actions.h:9-10`) for the superweapons
it manages. A wrapper that wants to deny should answer in whichever vocabulary
the original used — read it off the return value rather than guessing, because
`0x7E` and `0x46` drive different cursors.

**Confirmed via.** objdump (prologue byte count, vtable slot contents, the two
return sites); Antares source; in-game — a vtable wrapper co-existing with
Antares' `0x6CEF84` hook produced the correct disallowed cursor and no crash.

---

### `0x6CC390` — `SuperClass::Launch`, and the pending-SW global `0x8809A0`

**Framework names.** None — unhooked by every framework in the registry.

**What it does.** Runs the fired superweapon's effect, branching per SW action.
Relevant to third parties because of what it *clears*: `Unsorted::CurrentSWType`
at **`0x8809A0`** (equivalently `DisplayClass::Instance.CurrentSWTypeIndex`;
`0x87F7E8 + 0x11B8 = 0x8809A0`) is the pending/armed superweapon the cursor is
carrying.

Every reference in the binary:

| Address | What |
|---|---|
| `0x6AAE94`, `0x6AAF92` | `SidebarClass::ProcessCameoClick` — **sets** it on cameo click |
| `0x6AB2E7` | sets it to `1` (= `IronCurtain`); context unverified |
| `0x6CC46E` | inside `Launch`, sets it to `4` (= `ChronoWarp`) — the ChronoSphere second click, **not** a deselect |
| `0x6CCD1C`, `0x6CCD9A`, `0x6CCE41`, `0x6CD04F`, `0x6CD2CB`, `0x6CD50F`, `0x6CD6F8`, `0x6CD7D3`, `0x6CDA53`, `0x6CDCC3`, `0x6CDE16` | **11 × `movl $-1`** inside `Launch`, one per SW action branch — **this is the deselect** |
| `0x4FB8A9`, `0x50B190` | cleared when a superweapon becomes unavailable (`HouseClass::UpdateSuperWeaponsOwned` region) |

**What it does *not* do — easily mistaken.** There is no single deselect site to
patch. Anyone wanting "keep the superweapon selected after firing" should hook
`Launch`'s entry/exit and restore the index, **not** patch the 11 stores — and
must leave `0x4FB8A9`/`0x50B190` alone, since those fire when the superweapon is
genuinely lost.

**Confirmed via.** objdump (all reference sites, the `-1`/`4`/`1` constants);
`SuperWeaponType` enum from YRpp (`ChronoWarp = 4`, `IronCurtain = 1`).
The `0x6AB2E7` context and the keep-selected behaviour are **unverified** — no
implementation has exercised them.

---

## Related

- Screen-point → cell resolution (needed to aim a superweapon at the cursor)
  is documented in [Selection-Mouse.md](Selection-Mouse.md) under
  `DisplayClass::ProcessClickCoords` `0x692300`.
- Trigger **events** for superweapon activation are Ares-lineage, not engine:
  Antares `AresTriggerEvent::SuperActivated` = **75**, `SuperDeactivated` = 76,
  `SuperNearWaypoint` = 77 (`src/Utilities/AresEnums.h:31-33`), sprung from
  `SWTypeExt::Activate` (`Ext/SWType/Body.cpp:617-618`). ⚠ They spring only when
  Antares' `GetNewSWType()` is non-null, and the near-waypoint radius is
  **hardcoded to 5.0 cells**. `0x4FAE50` above catches every launch regardless of
  which framework handles the type.
