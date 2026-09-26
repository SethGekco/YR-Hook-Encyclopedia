# TechnoTypeClass per-TYPE lifecycle (ctor / dtor / LoadFromINI / save-load)

Per-*type* hooks on `TechnoTypeClass` — they fire once per **rules entry**, not
once per live object. Contrast
[Techno-Instance-Lifecycle.md](Techno-Instance-Lifecycle.md), which is the
per-object backbone; this page is the per-type one, and confusing the two is the
most common mistake in this area.

Two things make this cluster worth a page:

1. **It is one of the highest-consensus clusters in the registry.** Antares,
   Ares, Phobos and Kratos all attach their own TechnoType extension here, at
   the same seven addresses, all returning 0. That makes it safe to co-hook —
   and it makes any *divergence* between them a signal worth reading.
2. **`0x716123` vs `0x716132` is exactly such a divergence**, and the registry
   cannot show it, because both addresses appear for the Ares lineage and
   nothing marks the second one as contested. See below.

**Scope, stated once:** `BuildingTypeClass`, `InfantryTypeClass`,
`UnitTypeClass` and `AircraftTypeClass` are the only four classes deriving from
`TechnoTypeClass`, and every one of them runs through these seven addresses. One
set of hooks here replaces four sets of per-class hooks (e.g. the
`BuildingTypeClass` cluster at `0x45E50C` ctor / `0x45E707` dtor /
`0x465010`+`0x465300` save-load prefix / `0x4652ED`+`0x46536A` suffixes /
`0x464A49` LoadFromINI). Reaching for the per-class sites when you want all four
is four times the work and four times the surface.

---

## The cluster

| Address | Function | Stolen | Register / stack |
|---|---|---|---|
| `0x711835` | `TechnoTypeClass_CTOR` | 0x5 | `ESI = TechnoTypeClass*` |
| `0x711AE0` | `TechnoTypeClass_DTOR` | 0x5 | **`ECX`** `= TechnoTypeClass*` |
| `0x7162F0` | `TechnoTypeClass_SaveLoad_Prefix` | **0x6** | `[ESP+4] = pItem`, `[ESP+8] = IStream*` |
| `0x716DC0` | `TechnoTypeClass_SaveLoad_Prefix` (again) | **0x5** | same |
| `0x716DAC` | `TechnoTypeClass_Load_Suffix` | **0xA** | — |
| `0x717094` | `TechnoTypeClass_Save_Suffix` | 0x5 | — |
| `0x716123` | `TechnoTypeClass_LoadFromINI` | 0x5 | `EBP = pItem`, `[ESP+0x380] = CCINIClass*` |

**Framework names** (identical across all four for every row above)

| Framework | Source file |
|---|---|
| Antares | `src/Ext/TechnoType/Body.cpp` (1173-1220) |
| Ares | `src/Ext/TechnoType/Body.cpp` |
| Phobos | `src/Ext/TechnoType/Body.cpp` (1977-2031) |
| Kratos | `src/Hooks/TechnoTypeExtHook.cpp` |

Three stolen-byte details that are easy to get wrong because the neighbouring
row differs:

- The **ctor takes `ESI`, the dtor takes `ECX`.** They are not symmetrical.
- The save-load prefix is hooked at **two** addresses with **different stolen
  sizes** — `0x7162F0` steals 6, its `DEFINE_HOOK_AGAIN` twin `0x716DC0` steals
  5. Copying one row's size onto the other is a silent mis-declaration.
- The **load suffix `0x716DAC` steals 0xA**, so Syringe resumes at `+0xA`, not
  at `+5`. It sits `0x14` bytes before `0x716DC0`, which is enough clearance,
  but only just — a size bump here would collide with the prefix twin.

---

### `0x716123` — TechnoTypeClass::LoadFromINI

**What it does.** Fires while a `TechnoTypeClass` reads its own INI section, and
is the seat every framework uses to parse its per-type extension tags.

**What it does *not* do — easily mistaken.**

- **It is not building-specific, and it is not skipped for buildings.** A
  `BuildingTypeClass` section demonstrably reaches this base seat: Phobos parses
  `SellSound` and `EVA_Sold` into `TechnoTypeExt` only from this hook, then
  reads them back off `BuildingClass::Type` in
  `src/Ext/Building/Hooks.Selling.cpp:85,113`. If the base did not run for
  buildings, those tags could never work — and they do.
- **It fires once per type per INI pass, not once per type.** Rules are read in
  several passes (rulesmd, game-mode INI, map INI — see
  [Rules-Load.md](Rules-Load.md)), and `LoadTypesFromINI` walks **every** type on
  **every** pass, including passes whose file contains no section for that type.
  This is the source of the destructive-reparse trap below.

**⚠ The destructive-reparse trap.** A handler here that does

```cpp
this->MyList.clear();                 // <-- unconditional
for (auto const& s : ReadList(pINI, section, "MyList="))
    this->MyList.push_back(parse(s));
```

is correct on the rules pass and **wipes itself on the map pass**, where the INI
has no such section, `ReadList` returns empty, and the `clear()` has already
happened. The symptom is a feature that works from `rulesmd.ini` and silently
does nothing in an actual match, with no log line to explain it.

This is the same hazard [Rules-Load.md](Rules-Load.md) documents one level up at
`RulesClass::Read_File`, and it has the same fix: **read into the existing
value** rather than clearing and re-reading. Phobos gets this for free because
it parses through `Valueable<T>::Read`, which leaves the member untouched when
the key is absent. Hand-rolled `ReadString`/`ReadInteger`/`clear()` handlers do
not, and must replicate it.

**Confirmed via.** Antares source (`src/Ext/TechnoType/Body.cpp:1213-1220`),
Phobos source (`develop`, `src/Ext/TechnoType/Body.cpp:2023-2031`), registry
`hooks.csv`. The building-reaches-the-base claim is confirmed from Phobos'
`Hooks.Selling.cpp` read sites, not from disassembly.

---

### `0x716132` — the second LoadFromINI seat that Phobos refuses

**Framework names**
| Framework | Hooks it? | Source file |
|---|---|---|
| Antares | **yes** — `DEFINE_HOOK_AGAIN(0x716132, …, 0x5)` | `src/Ext/TechnoType/Body.cpp:1212` |
| Ares | **yes** | `src/Ext/TechnoType/Body.cpp` |
| Kratos | **yes** | `src/Hooks/TechnoTypeExtHook.cpp` |
| Phobos | **no — commented out** | `src/Ext/TechnoType/Body.cpp:2022` |

Phobos carries the line verbatim as:

```cpp
//DEFINE_HOOK_AGAIN(0x716132, TechnoTypeClass_LoadFromINI, 0x5)// Section dont exist!
```

**What this means for you.** The registry lists `0x716132` under Antares, Ares
and Kratos with no annotation, so a reader checking for conflicts sees a
perfectly ordinary second seat. It is not ordinary: one of the four frameworks
looked at it and deliberately backed out, on the grounds that the INI section is
not valid at that point.

**Decision rule, which does not depend on resolving the disagreement:**

- If your handler is **idempotent** — it reads into existing values and an
  absent key changes nothing — hooking both seats is harmless either way, and
  matching the Ares lineage costs nothing.
- If your handler is **destructive** — any unconditional `clear()`, or any
  `ReadX(section, key, hardcodedDefault)` that overwrites — then the second seat
  can only take data away from you and can never add any, because a section that
  does not exist has nothing to contribute. Hook `0x716123` alone.

The asymmetry is the useful part: there is no scenario in which a destructive
handler *gains* from the second seat, so the conservative choice is also the
complete one.

**⚠ Unverified.** Which of `0x716123` / `0x716132` is reached under what
condition has **not** been established here by disassembly — no vanilla
`gamemd.exe` was available. What is established is the source-level divergence
and Phobos' stated reason. Anyone with the binary should resolve the actual
control flow between `0x716123` and `0x716132` (15 bytes apart, both inside
`TechnoTypeClass::LoadFromINI`) and replace this section with the answer.

**Confirmed via.** Antares source (`src/Ext/TechnoType/Body.cpp:1212-1213`),
Phobos source (`develop`, `src/Ext/TechnoType/Body.cpp:2022-2023`), registry
`hooks.csv` rows for `0x716132`. Register layout is shared with `0x716123` in
every framework that hooks both (`EBP` / `[ESP+0x380]`).

---

### `0x711835` / `0x711AE0` — ctor & dtor

**What they do.** Allocate and free per-type extension data keyed by
`TechnoTypeClass*`.

**What they do *not* do — easily mistaken.** These fire during **rules load**,
once per type, long before any object of that type exists. A per-type ext
allocated here is **not** a place to keep anything about a live unit; that is
what the per-instance cluster is for. The dtor likewise fires at shutdown or
rules reload, not when a unit dies.

**Register / calling convention.** `ESI = TechnoTypeClass*` at the ctor;
`ECX = TechnoTypeClass*` at the dtor (thiscall entry). All four frameworks read
the same registers.

**Confirmed via.** Antares (`src/Ext/TechnoType/Body.cpp:1173-1187`), Phobos
(`develop`, `1977-1995`), registry `hooks.csv`.

---

### `0x7162F0` / `0x716DC0` / `0x716DAC` / `0x717094` — the save-load set

**What they do.** The prefix pair hands the extension container the `IStream*`
for the type currently being serialised; the two suffixes bracket the static
load and save. See [Savegame-Stream.md](Savegame-Stream.md) for the surrounding
stream machinery.

**What they do *not* do — easily mistaken.** Type data is re-parsed from the INI
on load, so most of a *type* extension has nothing session-specific to write
here. The things that do belong are the ones recording **what has happened**
rather than what was configured — per-house tallies, latches, anything whose
loss on reload would be exploitable or would silently change behaviour.

**Confirmed via.** Antares (`src/Ext/TechnoType/Body.cpp:1189-1210`), Phobos
(`develop`, `1997-2020`), registry `hooks.csv`.

---

## Related pages

- [Techno-Instance-Lifecycle.md](Techno-Instance-Lifecycle.md) — the per-object
  counterpart; check which one you actually want before hooking either.
- [Rules-Load.md](Rules-Load.md) — the multi-pass rules read that makes
  `LoadFromINI` fire more than once per type, and the same destructive-read trap
  one level up.
- [Savegame-Stream.md](Savegame-Stream.md) — the stream boundaries the save-load
  set plugs into.
