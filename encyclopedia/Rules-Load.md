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
