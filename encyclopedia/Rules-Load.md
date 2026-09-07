# Rules Loading (RulesClass::Init / Read_File)

How gamemd reads rules INI data, and the two most-hooked seams in that flow. The
headline knowledge: **`RulesClass::Read_File` (`0x668BF0`) is the single entry
every rules-reading pass goes through** — the initial rulesmd.ini (three internal
calls from `RulesClass::Init`), the game-mode INI, and the map INI — and
**`0x668F6A` is the tail of that same function**, which resolves the registry's
name ambiguity at that address.

Engine identities (YRpp): `0x6686C0` = `RulesClass::Init(CCINIClass*)` ("first
INI file only"); `0x668BF0` = `RulesClass::Read_File(CCINIClass*)` ("later files
— gamemode, map"). Binary: `Init` calls `Read_File` at `0x668A27`, `0x668B05`,
`0x668BAA` and returns (`ret 4` @ `0x668BE5`) immediately before `Read_File`'s
entry; `Read_File`'s body is the long `push esi; mov ecx,edi; call Read_<X>`
chain (`0x668E75`–`0x668EF0`+), ending at the `0x668F6A` tail.

---

### `0x668BF0` — RulesClass::Read_File (entry)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `RulesClass_Addition` | 0x5 | src/Ext/Rules/Hooks.cpp |
| Phobos | `RulesClass_Addition` | 0x5 | src/Ext/Rules/Body.cpp |

**What it does.** Entry of the function that reads every generic/list rules
section (`[General]`, `[VehicleTypes]`, `[AudioVisual]`, …) from the given INI.
Phobos's hook calls `RulesExt::LoadFromINIFile(pRules, pINI)` (its own
rules-level ext tags) and returns 0 — the vanilla body then runs unmodified.

**What it does *not* do — easily mistaken.**
- The "Addition" name suggests it only runs for the *additional* (gamemode/map)
  INIs. **Wrong: it fires for the initial rulesmd.ini too** — three times from
  inside `RulesClass::Init`. A hook here sees **every** rules-reading pass; use
  the `pINI` argument to tell passes apart.
- It reads the *list* sections but does **not** load the listed types' own
  sections (`[MTNK]`…) — that is `LoadTypesFromINI`, which vanilla runs inside
  this function's flow and **Phobos defers to the `0x668F6A` tail** (see below,
  and the `DEFINE_JUMP(0x668EED→0x668EF5)` "load types later" skip).
- Anything written into the INI object *after* this entry hook returns is still
  seen by the vanilla reads that follow — this entry is a valid seam for
  modifying INI content just-in-time (cf. lazy `$Inherits` resolution, page
  INI-Read-Inheritance.md).

**Used by / interactions.** Antares + Phobos, both cooperative `return 0` entry
hooks — chainable with each other and with further well-behaved hooks.

**Register / calling convention.** `ECX = RulesClass*` (thiscall), stack `+0x4 =
CCINIClass* pINI`. Returns `ret 4`.

**Confirmed via.** YRpp header (RulesClass.h JMP_THIS addresses + semantics
comments), Phobos source (clone `009112c`), objdump of vanilla gamemd.exe
(imagebase 0x400000): Init's three `call 0x668BF0` sites and the `ret 4` at
`0x668BE5`.

**Measured at runtime (2026-08-24, YR 1.001 + Antares + Phobos DevBuild #48,
skirmish start).** A cooperative logging hook at this entry fired **exactly three
times per game start, each with a DIFFERENT `CCINIClass*`**:

| Pass | `pINI` | Notes |
|---|---|---|
| 1 | `0x1362F730` | equals `CCINIClass::INI_Rules` |
| 2 | `0x168F9720` | heap; a different INI object |
| 3 | `0x00C9CFAC` | **stack-range address** — a local/temporary INI |

Two corrections to the naive reading of the disassembly:
- The three `call 0x668BF0` sites inside `RulesClass::Init` do **not** each
  produce a pass over the same rules INI. Only **one** pass carries `INI_Rules`;
  the sites are mutually exclusive branches, not a sequence.
- Pass 3's `pINI` lies in the stack range, so a hook here **must not** cache the
  `CCINIClass*` across passes or assume it outlives the call — that pointer is
  reused/invalid afterwards. Identify the rules pass by comparing against
  `CCINIClass::INI_Rules`, not by pass ordinal.

Practical consequence for anyone mutating INI content here: the hook fires more
than once, so any non-idempotent edit (accumulating `+=`/`*=` style folds) must
carry its own applied-guard, e.g. a sentinel key written into the INI object.

---

### `0x668F6A` — RulesClass::Read_File (tail)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `RulesData_InitializeAfterAllLoaded` | 0x5 | src/Ext/Rules/Body.cpp |
| Phobos | `RulesClass_Read_File_LoadTypes` | 0x5 | src/Ext/Rules/Body.cpp |

**What it does.** Tail of `Read_File`, after all section readers have run. Bytes:
`A1 38 B2 A8 00` = `mov eax,[0xA8B238]`, followed by the function epilogue
(`ret 4` @ `0x668F8D`). **Phobos stacks TWO hooks at this one address in the same
DLL** — Syringe chains same-address hooks even within one module: one re-invokes
the deferred `pRules->LoadTypesFromINI(pINI)` (paired with its `0x668EED→0x668EF5`
skip earlier in the function), the other runs `InitializeAfterAllLoaded`. Both
`return 0`.

**What it does *not* do — easily mistaken.**
- The registry shows two different names at this address; that is **not** a data
  error — both are real Phobos hooks, in the same source file.
- "InitializeAfter**AllLoaded**" does not mean "once, at the very end of game
  init" — it fires at the tail of **every** `Read_File` pass (rulesmd ×3 via
  Init, gamemode, map).
- Fires **per pass**, not per type; type-level work here must iterate arrays
  itself.

**Used by / interactions.** Phobos ×2 (above). Further cooperative size-5
`return 0` hooks chain safely here — verified: two additional third-party DLLs
co-exist at this address with independent read-only side effects. Hook order
between DLLs follows Syringe load order; do not rely on cross-DLL ordering at
this address.

**Register / calling convention.** `EDI = RulesClass*`, `ESI = CCINIClass* pINI`
(the current pass's INI). Stolen bytes `A1 38 B2 A8 00` (5).

**Confirmed via.** Phobos source (clone `009112c`) Body.cpp lines 1207/1252 +
objdump of vanilla gamemd.exe at `0x668F55–0x668F95`.

---

## Type identity: `GetArrayIndex()` is per-subclass  ⚠ silent cross-category collisions

Not a hook — a data fact that bites any DLL storing parsed INI type lists.

**`TechnoTypeClass::GetArrayIndex()` does not return a unique id.** It returns the
index within the type's OWN subclass array, and those are four separate arrays:

| array | address |
|---|---|
| `UnitTypeClass::Array` | `0xA83CE0` |
| `BuildingTypeClass::Array` | `0xA83C68` |
| `InfantryTypeClass::Array` | `0xA8E348` |
| `TechnoTypeClass::Array` (unified) | `0xA8EB00` |

So an index is unique only *within* a category. Measured against a stock
`rulesmd.ini`:

| index | vehicle | building | infantry |
|---|---|---|---|
| 2 | `APOC` | `GACNST` | `SHK` |
| 3 | `HTNK` | `GAPILE` | `ENGINEER` |
| 9 | `MTNK` | `NAPOWR` | `DOG` |

**The failure mode.** Parse an INI list of vehicles into `GetArrayIndex()`
values, then at runtime compare each techno's `GetArrayIndex()` against that
list: buildings and infantry match silently. In SuperWeaponExt a rule meant to
count nearby *tanks* was counting the player's Construction Yard and barracks, so
the effect scaled with base size and read in game as a mysterious *time-based*
increase — on a feature whose time-based growth was explicitly set to zero.
Nothing logs, nothing crashes, and the tag simply appears to behave wrongly.

**Confirming tell.** Phobos keeps four separate counter arrays —
`LimboAircraft` / `LimboBuildings` / `LimboInfantry` / `LimboVehicles` in
`Ext/House/Body.cpp::AddToLimboTracking` — all indexed by `GetArrayIndex()`. One
array would suffice if the index were unique across techno types.

**Fix.** Key on the unified array instead:

```cpp
const int id = TechnoTypeClass::Array.FindItemIndex(pType);   // unique
```

Cache it per type: `FindItemIndex` is a linear scan and runtime callers typically
run per object per frame. **Convert parse-time and runtime together** — changing
one side only is worse than the original bug, because the lists then never match
at all. Comparing `TechnoTypeClass*` pointers directly is equally correct and
needs no cache; prefer that when the value never crosses an engine-free boundary.

**Confirmed via.** YRpp array declarations; index census over a stock
`rulesmd.ini`; Phobos source at the cited function; observed in game as a wrong
radius, then fixed and re-deployed.
