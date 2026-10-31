# Remap colour and palette per object (`GetRemapColour`)

How the engine picks the player-colour remap for a techno, and how to override
it per object without a stolen-byte hook. Written while building CosmeticExt's
`ColorRules=` (2026-10-30). Everything here is from disassembly of
`gamemd-spawn.exe` 1.001 and has **not yet been observed in game** unless marked.

---

### `0x705D70` — TechnoClass::GetRemapColour (virtual slot `0x1E4`)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | (hook inside the function, at `0x705D74`) | 0x8 | — |

**What it does.** Returns the `LightConvertClass*` used to draw the object's
remap pixels. Logic, in order:

1. `pal = GetTechnoType()->Palette` (`TechnoTypeClass+0xDF0`, a
   `DynamicVectorClass<ColorScheme*>*`, set by art `Palette=`). If set, return
   `pal->Items[Owner->ColorSchemeIndex]->LightConvert` (`+0x30C`). **Disguises
   are ignored on this path.**
2. If `IsClearlyVisibleTo(HouseClass::CurrentPlayer)` (vtable `+0x440`) is
   false and `GetDisguiseHouse(true)` (vtable `+0xD0`) returns a house, use
   `ColorScheme::Array[thatHouse->ColorSchemeIndex]`.
3. Otherwise `ColorScheme::Array[Owner->ColorSchemeIndex]->LightConvert`.

`Owner` is `TechnoClass+0x21C`; `ColorSchemeIndex` is `HouseClass+0x16054`.

**What it does *not* do — easily mistaken.**

- **It is not a per-house cache you can swap.** The owner's index is read on
  every call, so changing the house's colour recolours every object it owns.
  A per-object override has to answer this call per object.
- **The slot is virtual, so a vtable wrap beats a hook here.** The four
  concrete vtables hold `0x705D70` at `AbsVTable + 0x1E4`: Unit `0x7F5E54`,
  Infantry `0x7EB23C`, Building `0x7E40A0`, Aircraft `0x7E2488` (the abstract
  slots `0x7E8E78` and `0x7F4B44` hold it too but never serve a live object).
  Writing your wrapper there (VirtualProtect, from DllMain) costs no stolen
  bytes, truncates no chain, and leaves Phobos' `0x705D74` hook running when
  the wrapper calls the original first. No deployed DLL in Rex's game dir
  references these slot addresses (2026-10-30 sweep).
- **`ColorScheme::Array` (`0xB054D0`) holds every `[Colors]` entry twice:**
  `ShadeCount` 1 and 53. `ColorSchemeIndex` points at the 53-shade one. The
  engine's name lookup (`0x474A90`) takes the first match whose `ShadeCount`
  is not 1. YRpp's `ColorScheme::FindIndex(name, 1)` default gives the wrong
  twin.
- **A custom palette is a parallel scheme vector, indexed the same way.**
  `ColorScheme::GeneratePalette(char*)` (`0x6263D0`, what art `Palette=`
  uses) returns one scheme per colour for a `.pal`. Its loader (`0x627590`)
  builds `<name>` + theater extension + `.PAL`, upper-cased: `abrams` loads
  `ABRAMSTEM.PAL` in temperate, not `abrams.pal`. It returns no vector when
  the file is missing. The result is cached by name, and the theater's
  palette rebuild frees it (CosmeticExt drops its cached pointers at
  `0x534DBE`). Bounds-check the index into it.

**Used by / interactions.** Phobos' `0x705D74` hook is inside the function
(size 8) and keeps working under a vtable wrap that calls the original.
CosmeticExt wraps all four slots (2026-10-30).

**Register / calling convention.** `__thiscall`, no stack arguments (plain
`ret`). A wrapper can be `LightConvertClass* __fastcall(const TechnoClass*,
void* edx)`.

**Confirmed via.** objdump of `0x705D70`–`0x705DF9` and of `0x627590`; the
slot values read from the exe's `.rdata`; `.syhks00` sweep of the deployed
DLLs. ⚠ **Unverified in game:** that the wrap installs as described. Proof
would be CosmeticExt's `GetRemapColour wrapped in 4 of 4` line in debug.log.

---

### Where to decide a per-object look, deterministically

A look picked from a cycle has to be picked in the same order on every
client. These are simulation events, so they qualify (all seats disassembled;
see CosmeticExt DESIGN.md for the stolen bytes):

| Event | Seat | Registers |
|---|---|---|
| First entry into the map | `0x6F6CBE`, in `TechnoClass::Unlimbo` after `ObjectClass::Unlimbo` succeeded | ESI = this |
| Factory product or clone leaving a building | `0x443C60`, `BuildingClass::KickOutUnit` entry | ECX = building, `[esp+4]` = object; product iff `building->Factory->Object == object` |
| Superweapon launch, start and end | `0x4FAE85` / `0x4FAEED` in `HouseClass::Fire_SW` | EBX = house, EDI = SuperClass |
| Free units | `0x446AA9` to `0x446FB6` in `Grand_Opening` | EBP = building throughout |
| Deploy / undeploy | `0x7396D2` (EBP = unit, EBX = new building), `0x449E4F` (EBP = building, EBX = new unit or 0) | |

**Easily mistaken.** Object `UniqueID`s are **not** the same on every client
(`ScenarioClass::UniqueID` starts from a salt), so never hash them for a
shared choice. Key per-object state by them (they survive save/load and are
not reused in a game), but hash something ordered instead, such as a house's
`ArrayIndex` or the order in which sources first appear. Antares
(`Ext/SWType/Hooks.cpp`, `SuperClass_ClickFire` at `0x6CB920`) clears
`SuperClass::IsReady` only after it really called `Launch`, so "ready
before, not ready after" tells a real launch apart from an aborted one,
except for `PreClick`/`PostClick` weapons, which stay ready. (Source
reading; classic Ares not checked.)
