# INI Reading & Inheritance

The engine's INI object (`INIClass` / `CCINIClass`) and the hooks that extend how
sections and keys are read. The headline knowledge on this page: **Phobos's INI
"inheritance" is resolved lazily at read time, not at load time** — and the one
hook whose name suggests otherwise actually does something else entirely.

---

### `0x474230` — CCINIClass::ReadCCFile (post-parse tail)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `CCINIClass_Load_Inheritance` | 0x5 | src/Misc/Hooks.INIInheritance.cpp |

**What it does.** Fires inside `CCINIClass::ReadCCFile` immediately after the file
contents have been parsed into the INI object (`0x47422B call 0x525A60` = the
parse; hook lands on the `mov ebp,eax` that follows). Phobos uses it to implement
**`[$Include]`**: it scans the just-loaded INI for a `[$Include]` section and
recursively merges each listed file into the same `CCINIClass` via
`ReadCCFile(file, false, false)` (each file merged only once per INI object;
missing file = fatal error).

**What it does *not* do — easily mistaken.** Despite the hook's name, **it does
not implement `$Inherits`**. No parent map is built here and no inheritance state
is prepared at load time. `$Inherits` is resolved *lazily, per read miss*, at
`0x528BAC` (below) — an extension that wants to modify what inheritance sees does
**not** need to run before this hook; it only needs to write into the in-memory
INI before the first *read* of the affected section.

**Used by / interactions.** Phobos only (release). Because includes are merged
here, any tool that wants "the complete INI" must act *after* the outermost
`ReadCCFile` returns, or it will miss `[$Include]`d content.

**Confirmed via.** Phobos source `src/Misc/Hooks.INIInheritance.cpp` (clone
`009112c`, 2026-08-02) + objdump of vanilla `gamemd.exe` (imagebase 0x400000):
bytes at `0x474230` = `8B E8` following the parse call, function entry `0x474200`
matches the Antares PDB name `CCINIClass_ReadCCFile1`.

---

### `0x528BAC` — INIClass::GetString, entry-not-found branch

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `INIClass_GetString_Inheritance_NoEntry` | 0xA | src/Misc/Hooks.INIInheritance.cpp |

**What it does.** This is the **actual `$Inherits` implementation site.** The
address is the not-found branch of `INIClass::GetString` (binary: `je 0x528BAC`
when the entry lookup fails; the hook rejoins at `0x528BB6`). On a key miss,
Phobos reads the section's `$Inherits` value (cached per section CRC in a static
map, reset whenever a different `CCINIClass` is read), then walks the
comma-separated parent list **depth-first, first-found-wins**: for each parent in
list order it looks up the key (recursing through that parent's own `$Inherits`),
and stops at the first parent that has it. Companion typed hooks
(`0x5276D0` ReadInt, `0x5295F0` ReadBool, `0x5283D0` ReadDouble, `0x529880`/
`0x529CA0` Point2D/3D, `0x527920` GUID/locomotor, plus byte-patch `0x5278C6`)
reroute the typed readers through the same fallback.

**What it does *not* do — easily mistaken.**
- **Parent precedence is FIRST-found, not last-wins.** In `$Inherits=A,B`, a key
  missing from the child is taken from A if A has it; B is only consulted if A
  misses. (The child's own key always wins outright — the fallback only runs on a
  miss.)
- **No cycle detection.** `A $Inherits B` + `B $Inherits A` with a key missing
  from both recurses until stack overflow. Cycles are the modder's responsibility.
- **Not load-time.** Nothing is flattened; every value stays in its original
  section. Late writes into a section (before its first read) are fully visible
  to inheritance; writes *after* a section's `$Inherits` string has been cached
  will see the old parent list until the INI object changes.

**Used by / interactions.** Phobos only (release). Anything else that hooks the
typed INI readers (`0x5276D0` family) collides with Phobos's overwrite hooks —
those are flow-replacing (they return past the vanilla body), not chainable.

**Register / calling convention.** At `0x528BAC`: `EBP = CCINIClass*`; stack
(offset 0x1C): +0x4 sectionCRC, +0x8 entryCRC, +0xC defaultValue, +0x10 buffer,
+0x14 length. Phobos writes `EDI=buffer, EAX=0, ECX=result` and jumps `0x528BB6`.

**Confirmed via.** Phobos source `src/Misc/Hooks.INIInheritance.cpp` (clone
`009112c`, 2026-08-02) + objdump of vanilla `gamemd.exe` around `0x528BA0–0x528BC0`
(branch structure matches). Cycle-overflow behaviour is by code reading, not
tested in game.
