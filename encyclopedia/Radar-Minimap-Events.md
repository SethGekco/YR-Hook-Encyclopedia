# Radar / Minimap Events

The minimap's "base under attack" pulse — the rotating rectangle — and the
globals around it. Everything here is vanilla `gamemd.exe`; no shipping
framework hooks these addresses, but **map-expansion DLLs do**, and one of those
hooks is a documented trap (see `0x660540`).

## Globals

| Address | Meaning |
|---|---|
| `0x87F7E8` | `RadarClass::Instance` |
| `[R+0x1488]` | radar zoom factor (float). **< 1 on ordinary maps too** — the whole map is scaled into the radar rect |
| `[R+0x1490]` / `[R+0x1498]` | iso origin offsets consumed by the transform |
| `[R+0x149C]` / `[R+0x14A0]` | pixel origin added after scaling |
| `[R+0x121C]` / `[R+0x1220]` | the two minimap surfaces (null if creation was skipped) |
| `[R+0x14A4]` / `[R+0x14A8]` | radar rect dimensions (104 × 108 in the stock sidebar) |
| `0x880C84` / `0x880C88` / `0x880C8C` / `0x880C90` | radar screen rect: x / y / w / h |
| `0x8809F4` … `0x880A00` | the radar **dirty rect** (x, y, w, h) consumed by the blit |
| `0x880A04` | the drawing singleton the event paths call virtuals on. **No `.text` writer exists, yet it is non-null at runtime** — do not reason from "never written" to "always null" |
| `0xB04DAC` / `0xB04DB8` | radar event array / count |
| `0x7F0998` | per-event-type dedup radius table, stride `0x10` |
| `0x7F09A4` | per-event-type "enabled" byte, stride `0x10` |

## `0x6550C0` — RadarClass::CellToRadarPixel

Cell → radar pixel. `ECX = RadarClass::Instance`, `ret 8`:

```
px = round((X - Y + [R+0x1490]) * [R+0x1488]) + [R+0x149C]
py = round((Y - [R+0x1498] + X) * [R+0x1488]) + [R+0x14A0]
```

Returns a **1 × 1 rect** (`{px, py, 1, 1}`), not a point. Inverse at `0x655150`.

**What it does *not* do — easily mistaken.** The zoom factor is below 1 on
ordinary maps as well as huge ones (a 146×169 map already spans ~315 iso units
into a 104-wide rect). Events and terrain therefore live in the *same* space;
"events are in rect space, terrain is in surface space" is not a real failure
mode, and chasing it will waste your time.

## `0x65FA70` — RadarEventClass::Create (add event)

`ECX = event type`, stack arg = packed `CellStruct`. Walks `0xB04DAC` and, for an
existing event of the same type, compares the squared cell distance against that
type's radius at `[type*0x10 + 0x7F0998]`; within the radius the event is folded
into the existing one instead of appended.

**What it does *not* do — easily mistaken.** That dedup is also what caps the EVA
announcement. If you gate or skip this function (e.g. to suppress pulses on a
huge map), the announcement path is *not* deduped for you — "Your base is under
attack" repeats uncapped. Replicate the radius test if you intercept here.

## `0x65FB80` — RadarEventClass::RadarEventClass

Stores the raw `CellStruct` at `[this+0x20]/[+0x22]` (stride-independent), runs
`0x6550C0`, and stores the pixel position **relative to the radar rect origin**
at `[this+0x04]/[this+0x08]`:

```
65fbe4  mov edi,[0x880C84]   ; rect x
65fbea  mov ebp,[0x880C88]   ; rect y
65fbff  call 0x6550C0
65fc09  sub ecx,edi
65fc0b  sub eax,ebp
65fc0d  mov [esi+4],ecx      ; <- position the pulse draws and erases at
65fc10  mov [esi+8],eax
```

## `0x660540` — RadarEventClass::Erase  ⚠️ **do not skip**

**What it does.** Repaints the previous frame's pulse and marks the region for
blit:

```
66054E  call 0x660730             ; 4 rotated corner points of the pulse
660553  edx=[esi+4] esi=[esi+8]   ; offset them by the stored position
660587  push 0x65FB60             ; per-pixel callback ->
                                  ;   RadarClass::Instance->0x6562D0
                                  ;   = replot that pixel from its cell
6605A6  call [esi+0x78] / [+0x44] ; walk each of the four edges
6605FA+ union the 4 rects into the dirty rect 0x8809F4..0x880A00
```

**What it does *not* do — easily mistaken.** It is **not** a coord-transform
helper, and its result does **not** feed sync-checksum logging. That
mis-identification is in circulation: at least two independent map-stride
expansion DLLs skip this function wholesale at stride > 512 (one of them names
the hook `Map512CoordTransformGuard`) to dodge an access violation on
`0x880A04`. The cost is that the "base under attack" pulse is drawn every frame
and **never repainted** — magenta trails that persist on the minimap at *every*
map size and fade only where unrelated activity happens to dirty those cells.
If you must guard it, guard on `0x880A04 == 0` and nothing else.

**Register / calling convention.** `__thiscall`, `ECX = RadarEventClass*`, no
stack args; its only `ret` is the bare `c3` at `0x660729`. The entry is
`sub esp,0x68` (3) + `lea eax,[esp+0x48]` (4), so a Syringe hook here must
declare **7** stolen bytes, not 5 — 5 lands mid-`lea` and the stub replays a
truncated instruction. To skip cleanly, jump to the bare `ret` at `0x66053A`.

**Used by.** One caller, `0x65FE3B`, inside `RadarEventClass::Update`
(`0x65FE00`), which the radar tick drives per frame from `0x65336D`.

## Neighbouring event routines

| Address | Role |
|---|---|
| `0x660000` | draw every live event (called from `0x657537`, inside `RadarClass::UpdateMinimap`) |
| `0x660050` | draw one event's pulse; picks colour from the type tables, derefs `0x880A04`, unions its rects into the dirty rect |
| `0x660730` | the four rotated corner points of a pulse at its current radius |
| `0x6603B0` | purge expired events (called from `0x65786D`) |
| `0x65FD50` / `0x660B00` | clear all events |
| `0x6607D0` / `0x660840` | savegame serialisation of the event list |

**Confirmed via.** objdump of vanilla `gamemd.exe` (`0x400000` image base,
`file offset == RVA` in `.text`) for every address and offset above;
cross-referenced by scanning `.text` for each global's literal 4-byte address.
The `0x660540` behaviour was additionally confirmed by the bug it causes: with
the skip in place a MapSizeExt build smeared the minimap on maps of every size,
which is what motivated the disassembly. In-game confirmation of the *fix* is
pending at the time of writing.
