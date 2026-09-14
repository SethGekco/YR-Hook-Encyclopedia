# Subsystem: Scenario [Smudge] section read

The scenario-load routine that parses a map's `[Smudge]` entries, and a
**verified hook-placement hazard** inside its epilogue. Runs during scenario
start, immediately after the isometric tile set is loaded (`debug.log`:
"Loaded N isometric tiles ...").

All addresses are for the standard YR `gamemd.exe`, imagebase `0x400000`,
verified by objdump disassembly and an in-the-wild crash investigation
(2026-09-14).

## Function shape

- Body begins near `0x6B4C80`; a guard early in the function bails straight
  to the epilogue when there is nothing to read:

```
0x6B4CA7:  jle 0x6B4DBA          ; early-out (observed taken on maps with no [Smudge] section)
...
0x6B4DB9:  5B        pop ebx     ; epilogue, fall-through entry
0x6B4DBA:  5D        pop ebp     ; <-- ALSO a direct branch target (from 0x6B4CA7)
0x6B4DBB:  81 C4 94 00 00 00     add esp, 0x94
0x6B4DC1:  C3        ret
```

## ⚠ Hazard: 0x6B4DBA is a branch target inside the epilogue

Any Syringe hook whose 5-byte JMP patch covers `0x6B4DBA` (i.e. any hook
placed at `0x6B4DB6`–`0x6B4DBA` exclusive of the target itself) breaks the
early-out path: the `jle` lands on byte 3–4 of the JMP rel32, decodes
garbage, and the process dies with scattered symptoms — `C0000096`
(privileged instruction) or `C0000005` at `0x6B4DBA/0x6B4DBB`, or a wild
jump into heap (EIP in unmapped/heap space), or corrupted registers that
crash later in unrelated code (`0x5257D1` thiscall with `this = -1` was
observed downstream).

Because the trigger is the early-out path, the crash is **map-content
dependent**: maps with `[Smudge]` entries load fine, maps without them crash
at scenario start. This presents as "random map crashes" and is easy to
misattribute (it was initially blamed on wine).

**Seen in the wild:** a modified Phobos fork (Global Crisis standalone,
2026) ships `DEFINE_HOOK(0x6B4DB7, ScenarioClass_ReadSmudge_ExtraSmudges, 0xA)`
— the patch straddles `0x6B4DBA`, and every no-`[Smudge]` map (12 of that
mod's 29 Battle maps) crashes at load, on Windows and wine alike. Zeroing
that one `.syhks00` record made the mod boot fully in-game. Mainline Phobos,
Antares, Ares and Kratos do **not** hook this range (`registry/hooks.csv`).

**Safe placement:** `0x6B4DBA` itself is a safe hook address — a branch
*target* is a legal hook start (both the fall-through path, after
`pop ebx`, and the `jle` path enter at the first byte of the JMP). Note the
two entry paths differ by one pop: on the `jle` path EBX has not been
popped. Hooking earlier, fully before `0x6B4CA7`'s target range, is also
fine.

General rule this confirms: before hooking, scan the function for branches
whose targets fall strictly inside `[hookaddr+1, hookaddr+5)`.
