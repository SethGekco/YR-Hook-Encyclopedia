# Subsystem: Map hover tooltip (DisplayClass::GetToolTip)

The delayed tooltip shown when the mouse rests on the tactical map. It names the
object under the cursor, or shows a cell string. The function holds a **verified
crash hazard**: an internal branch target sits two instructions before a Phobos
hook, so no seat between them is safe.

All addresses are for the standard YR `gamemd.exe`, imagebase `0x400000`, from
objdump disassembly and an in-game crash investigated on 2026-11-07.

## Function shape

`0x4AE4F0`, `__thiscall`: `ECX` = DisplayClass, `[esp+4]` = help id, `ret 4`.
Returns the tooltip text in `EAX`, or 0 for no tooltip. Only ids `0x1F4..0x384`
(the tactical map) get past the entry checks.

```
0x4AE4F0  mov eax,[esp+4]; sub esp,0x2C; ... push ebx; push esi     ; frame: 0x2C locals + ebx, esi
0x4AE571  call 0x692300            ; ProcessClickCoords: object under the cursor -> [esp+0xC]
0x4AE57E  je 0x4AE5C1              ; [0xA8F7D8] clear (when set: sprintf the cursor's cell X/Y and return it)
0x4AE5C1  call 0x565730            ; cell under the cursor; [cell+0x12C] bit 8 clear -> CSF "TXT_SHADOW" via 0x734E60
0x4AE600  mov ecx,[esp+0xC]        ; <- branch target (0x4AE5D7 jne, 0x4AE5E0 je)
0x4AE604  test ecx,ecx; je 0x4AE69B
0x4AE60C  test [ecx+0x14],1        ; AbstractFlags & Techno
0x4AE610  je 0x4AE697              ;   not a techno (a tree, ...) -> esi=0; jmp 0x4AE66C
0x4AE616  mov al,[ecx+0x41A]       ; TechnoClass::IsOwnedByCurrentPlayer
0x4AE620  jne 0x4AE66C             ;   your own techno -> straight to the name
0x4AE622  cmp [ecx+0x220],2        ; cloaked -> visibility check via 0x4870D0 (0x4AE62B..)
0x4AE654  call [vtbl+0x84]         ; GetTechnoType; [type+0xC9A] set -> 0x4AE69B (no name)
0x4AE668  mov ecx,[esp+0xC]        ; enemy / neutral techno path
0x4AE66C  test ecx,ecx             ; <- branch target (0x4AE620 jne, 0x4AE699 jmp)
0x4AE66E  je 0x4AE69B
0x4AE670  mov edx,[ecx]; call [edx+0x90]   ; GetUIName
0x4AE678  test esi,esi; jne 0x4AE69D       ; techno: return the name
0x4AE67C  ... call 0x5657A0 / 0x484FF0     ; non-techno: other text
0x4AE69B  xor eax,eax              ; <- target (many)
0x4AE69D  pop esi; pop ebx; add esp,0x2C; ret 4
```

So `0x4AE66C` is reached three ways: falling through from `0x4AE668` (an enemy or
neutral techno), from `0x4AE620` (**your own** techno) and from `0x4AE699` (**any
non-techno** object, such as a tree).

## Registry hooks in this function

| Address | Framework | Function name | Stolen |
|---|---|---|---|
| `0x4AE51E` | Phobos | `DisplayClass_GetToolTip_HelpText` | 0x6 |
| `0x4AE62B` | CnCNet-Spawner | `DisplayClass_HelpText_Cloak` | 0x5 |
| `0x4AE670` | Phobos | `DisplayClass_GetToolTip_EnemyUIName` | 0x8 |

None of these three covers a branch target.

---

### `0x4AE668`–`0x4AE66F` — ⚠ do not hook: the patch covers the `0x4AE66C` branch target

**What goes wrong.** A Syringe patch at `0x4AE668` is `E9 rel32` plus NOP padding.
Its last rel32 byte, the **top byte** of `stub − 0x4AE66D`, lands on `0x4AE66C`.
When the engine branches to `0x4AE66C`, the CPU decodes that single byte as an
instruction. Your own techno or any non-techno under the cursor takes that
branch, once the tooltip delay has passed.

**The symptom depends on where Syringe put the stub, so it changes per launch.**
Measured from live memory dumps, all with the same 31-DLL launch list
(2026-11-06/07). The stub address moves with what earlier DLLs allocate at
start-up, here a map-size DLL that sizes itself per map:

| Run | Stub | Byte at `0x4AE66C` | Decodes as | Effect |
|---|---|---|---|---|
| normal skirmish map | `0x04800000` | `04` | `add al,0x90` | silent (skips the null test, which is safe because `ECX` is already non-null) |
| three 1000x1000 runs | `0x07770000` | `07` | `pop es` | ⚠ Unverified: expected fault at `0x4AE66C` (a non-selector loaded into ES); no hover happened in those runs |
| one 1000x1000 run | `0x073A0000` | `06` | `push es` | **VERIFIED crash**, below |

**VERIFIED signature for `06`** (snapshot-20261107-084232): `C0000005 at
00000000`, `EIP 0`, **`ESI = 0000002B`** (the ES selector under Wine), and `EBX` =
the caller's saved `ESI`. Mechanism: `push es` leaves ESP 4 bytes low. The epilogue
then pops the selector into `ESI` and the saved `ESI` into `EBX`, and `ret 4` takes
a zeroed local as the return address. A crash with `EIP 0` and `ESI` equal to a
segment selector (`0x23`/`0x2B`) points here.

**What it does *not* do — easily mistaken.**
- It is not random memory corruption. One launch can run clean for an hour if
  nobody hovers; the same launch crashes on the first own-unit tooltip.
- It is not caused by the DLL whose allocations moved the stub, even though adding
  or removing that DLL turns the crash on or off.
- Moving the seat a few bytes does not help. Any seat from `0x4AE668` to `0x4AE66B`
  still covers `0x4AE66C`. A seat at `0x4AE66C` itself needs 5 bytes and runs into
  Phobos at `0x4AE670`.

**Safe alternative seat: `0x4AE600`, stolen 6** (`mov ecx,[esp+0xC]` + `test
ecx,ecx`). Branching to the *start* of a hook is fine, and nothing branches into
`0x4AE601..0x4AE605`. The stolen bytes hold no relative operand, so `return 0` is
safe under classic Syringe. The `test` flags survive the stub's `jmp` back to the
`je` at `0x4AE606`. All three paths to the name pass through it. To give no
tooltip, return `0x4AE69B`. The object is at `[esp+0xC]`, the same slot `0x4AE668`
reads. ⚠ It may be a non-techno (a tree), so the handler must not assume
TechnoClass. ⚠ Unverified in game: seat reasoned from disassembly only.

**Used by / interactions.** A private disguise-tooltip DLL (MirageTreesExt) used
`0x4AE668` with stolen size 8; that is the crash above. It moved to `0x4AE600`
(stolen 6) on 2026-11-07. The registry has no framework hook here.

---

## Confirmed via

- objdump of `gamemd.exe` (`0x4AE4F0`–`0x4AE6A5`; branch sources listed above).
- Live-memory dumps (`ReadProcessMemory` of the running game) from five runs,
  bytes `0x4AE668..0x4AE677`: the jmp targets and the byte at `0x4AE66C` in the
  table above.
- `except.txt` of the crash: `EIP 00000000, ESP 0036D168, EBX 000001F4, ESI
  0000002B`. `0x6AC210` keeps the help id `0x1F4` in `ESI` and calls through
  `0x640450` → `0x658770` → `0x4AE4F0`. So `EBX = 0x1F4` is that saved `ESI`,
  shifted one slot.
- `TechnoClass+0x41A` = `IsOwnedByCurrentPlayer` from YRpp's field layout (the three
  bools before `unknown_bool_41D`).
- A sweep of 3,483 hooks from 31 deployed DLLs against every direct branch target
  in the disassembly found this one in the tooltip path. Others are listed in
  [_TRAPS-READ-FIRST.md](_TRAPS-READ-FIRST.md) §9.
