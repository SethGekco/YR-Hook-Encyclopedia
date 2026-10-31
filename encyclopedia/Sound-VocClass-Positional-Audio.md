# Sound: VocClass positional audio (PlayAt, distance volume, pan)

How gamemd decides **whether and how loud** a positional sound is heard, and
where to hook it. Written while building CosmeticExt
(`~/Claude/CosmeticExt`, distance-dependent soundmd.ini tags). All addresses
are gamemd 1.001 / gamemd-spawn.

**Symptoms that bring you here:**

- "`VocClass::Find` returns garbage or crashes."
- "My sound is inaudible off screen even with a big `Range`."
- "`Type=global` sounds still get quieter."
- "I want a filter or reverb on a sound."

**Nobody else hooks this path** (registry, 2026-10-25). The nearest framework
hooks are:

- Phobos `0x7504C9`, `VocClass_ReadINI_LogMissingSamples`: the per-sound
  INI read, which is not the place to read your own tags, see below.
- Antares/Ares `0x4011C0` `Audio_Load` and `0x4064A0` `AddSample`: the
  bag/sample side.

---

## Structural: `VocClass::Array` holds handles, not data

`VocClass::Array` (`0xB1D378`) is a DynamicVector of **4-byte handles**. Each
item's only field points at the sound data, which is what YRpp's `VocClass`
struct actually describes. Two places in the code show it:

- the handle constructor at `0x750380`
- `LoadAll`, which does `mov ecx,[Items+i*4]; mov ecx,[ecx]` at `0x75130F`

**Easily mistaken:** YRpp's `VocClass::Find` reads `Name` straight through
the handle, so it compares against a pointer's bytes. **Never use it.** Use
`VocClass::FindIndex(name)` and dereference `*Array.Items[i]` yourself.

Data fields used here: `Control` `+0x10` (loop bit), `Type` `+0x14`
(`0x10` = Global), `Range` `+0x50` (cells), `MinVolume` `+0x54` (read via
`0x405140`, which returns 0.0 (the float at `0x7E1748`) while the audio flag
`0x87E2A0` is 0), `Name` `+0x6C`.

The audio code draws only from `Randomizer::Global` (`0x886B88`), which is
**unsynced**. Adding, delaying or substituting `PlayAt` calls therefore
cannot desync a multiplayer game. Keep any randomness you add on an unsynced
generator too.

---

### `0x7509E0` — VocClass::PlayAt (entry)

**Framework names:** none in the registry. CosmeticExt uses
`VocClass_PlayAt_CosmeticExt` (size 5).

**What it does.** This is `PlayAt(int index, CoordStruct const& coords,
AudioController* ctrl)`, the funnel for positional one-shots: anim `Report`
sounds (`0x42211A`), weapon reports, deaths. At entry you can:

- **Substitute the sound** by rewriting ECX, then `return 0`. The stolen
  `mov al,[0x8464AC]` (VoicesEnabled) has no relative branch, and ECX is not
  read before it.
- **Skip the play** with `R->EAX(0); return 0x7509EF;`, PlayAt's own `ret 4`.
  Nothing has been pushed yet at that point. No caller reads EAX, but 0 is
  "nothing played".

**What it does *not* do — easily mistaken.**

- It is **not** the only sound path. UI and EVA sounds and `PlayGlobal` go
  elsewhere.
- Sounds held by an `AudioController` (a unit talking while it moves, a
  burning building) are re-levelled every frame by `0x750D40`, which never
  passes through PlayAt again. Picking a different sound here changes the
  whole playback, but changing the *volume* here only affects the first
  frame.
- Replaying a sound later through `PlayAt(i, coords, nullptr)` makes it a
  free one-shot. That is fine for an anim's Report: the anim gets a fresh
  controller and is often gone by then. Wrong for:
  - loops: played free, they never stop;
  - sounds whose controller is busy (`ctrl->GetEvent()` non-null): vanilla
    is keeping or replacing what plays there.

**Register / calling convention.** `__fastcall`: ECX = index, EDX =
`&coords`, `[esp+4]` = controller (may be null).

**Confirmed via.** objdump of gamemd-spawn.exe (entry bytes, `ret 4` at
0x7509EF, no jump into 0x7509E0..0x7509E4). Seat checked by
`check_hook_bounds --exe`. **⚠ Unverified in game** at the time of writing
(the CosmeticExt DLL had not yet been deployed).

---

### `0x750AC0` — positional volume and pan function

Called from PlayAt (return address `0x750A48`) and from the per-frame
controller update `0x750D40` (return address `0x750D7B`). It computes the
**distance metric**, the linear volume, the global floor and the pan.

**The distance metric** is what Range means:

1. The source coords become a client point (via
   `TacticalClass::CoordsToClient`, `0x6D2140`). The tactical view
   rectangle is `DSurface::ViewBounds` `0x886FA0` (Width `+8`, Height `+0xC`).
2. The function takes how far the point is **beyond the view's edges**:
   `[esp+0x38]` horizontally, `[esp+0x20]` vertically **doubled**
   (isometric). Each is clamped at 0.
3. `rangePx = Range × 60` at `[esp+0x14]`.
4. If both offsets are inside `rangePx`, volume =
   `(rangePx − max(dx, 2dy)) / rangePx`, stored at `[esp+0x18]`. Otherwise
   volume is 0.

So **Range is in cells beyond the screen edge**, with the edge distance
measured as a Chebyshev distance. On screen is distance 0, at full volume.

**Two `Type` bits change this** (YRpp `SoundType` names). Both were read
from the disassembly; **⚠ not yet observed in game**.

- **`0x800` (`Shroud`), at `0x750B2D`** (`test bh,0x8`). The source's cell
  (`MapClass::GetCellAt` `0x5657A0`) must have flags `+0x12C & 0x18`, i.e.
  be revealed. Otherwise the function returns 0.0 at `0x750B9D`, before the
  distance is computed. The sound is silent, and a hook at `0x750C9B` never
  sees it.
- **`0x40` (`Local`), at `0x750BFA`** (`test bl,0x40`). Before it,
  `[esp+0x38]` = |client x − half width| and `[esp+0x28]` = |client y − half
  height| (the halves are `ViewBounds` × 0.5 at `0x7E5168`). A non-Local
  sound then subtracts the half sizes and clamps at 0, giving beyond-the-edge
  distance. A **Local sound skips that**, so its `Range` is measured from the
  **screen centre**, and `[esp+0x38]`/`[esp+0x20]` at the volume seat hold
  centre distances.
- **`Screen` (`0x20`) is not tested** in this function or in PlayAt.

**Easily mistaken:** a hook that recomputes "cells beyond the edge" for
itself, for example to pick a variant at PlayAt, disagrees with the
engine for `Type=LOCAL` sounds. Vanilla YR has 31 of them, all ambients and
loops. Branch on `Type & 0x40` the way the engine does.

**What it does *not* do — easily mistaken.**

- `Range` is **not** measured from the screen centre or from any unit. A
  `Range=10` sound 11 cells beyond the edge is silent however large the map
  is.
- **`Type=global` does not mean "no distance falloff."** Global sounds are
  faded exactly like the others. Global only adds a **floor**: at `0x750C9B`,
  `test bl,0x10 / je 0x750CBD`, and for global sounds
  `volume = max(volume, MinVolume)` (`0x750CA0..0x750CB9`).
- Below **0.05** (`0x7E8AE8`, compared at `0x750CBD`) the function returns 0
  and the sound is **not played at all**. A sound turned down by a hook can
  therefore vanish rather than play quietly.

### `0x750C9B` — volume seat (CosmeticExt `VocClass_ComputeVolume_CosmeticExt`, size 5)

This is the place to replace or scale the distance volume: after vanilla's
linear value, before the global floor and the 0.05 cut.

- **⚠ It steals `test bl,0x10; je 0x750CBD`, a relative branch.** Never
  `return 0`. Return `0x750CA0` for global sounds and `0x750CBD` otherwise,
  replicating the branch. See `Syringe-Stub-Semantics.md`.
- Locals at the seat:
  - `[esp+0x18]` volume (float)
  - `[esp+0x38]` dx px
  - `[esp+0x20]` 2·dy px
  - `[esp+0x14]` rangePx
  - EDI = sound data
  - EBX = Type flags
  - The FPU stack is empty.
- To tell the callers apart, read `[esp+0x34]`, the return address. From
  PlayAt (`0x750A48`), its controller (PlayAt's EBP) is saved at
  `[esp+0x8]`. From `0x750D40` (`0x750D7B`), the controller (its EBX) is at
  `[esp+0xC]`.
- **Easily mistaken:** randomness here runs **every frame** for
  controller-held sounds. A fresh draw per call makes them flutter, so key
  the draw on (controller, sound).

### `0x750D29` — pan seat (CosmeticExt `VocClass_ComputePan_CosmeticExt`, size 5)

The pan has just been computed into **EAX** (0..0x4000, centre 0x2000) and
not yet stored to the out-parameter. The stack frame is as above. Stolen:
`fld [esp+0x18]; pop edi`, which has no branch and leaves ESP unchanged at
replay, so `return 0` is safe.

**Confirmed via.** objdump of 0x750AC0..0x750D3F (the full function).
Offsets cross-checked against both call sites. **⚠ Unverified in game** at
the time of writing.

---

### `0x7513DD` — VocClass::LoadAll (single exit)

**What it does.** `LoadAll(CCINIClass*)` is at `0x7510D0`. At the exit, EDI =
the soundmd INI and every sound exists. That makes it the place to read your
own per-sound tags: you can resolve cross-references between sounds by
`FindIndex` here, which you can't do mid-load. Stolen: `pop edi; pop esi;
pop ebp; add esp,0x824` (9 bytes, no branch).

**Easily mistaken:** Phobos' `0x7504C9` is inside the **per-sound** read.
Tags that name other sounds can't be resolved there, because later sounds
don't exist yet.

**How it builds the list** (read from the disassembly, 2026-10-30). The
`[SoundList]` loop starts at `0x7512C6` and runs over `GetKeyCount`, in key
order:

- Each value is read with `GetString` into a **32-byte** buffer
  (`[esp+0x10]`), so a name is at most 31 characters.
- It is compared against every existing sound by `_strcmpi` (`0x7C8D20`) on
  the name getter `0x405170`. A duplicate name adds nothing, which is why
  vanilla's 847 entries make 818 sounds.
- A new name gets a 4-byte handle (`0x7513B2` → `0x4063B0` builds the
  data). The handle is appended only if `VocClass::Array` can grow.
  `Count >= Capacity` with a static buffer, or with `CapacityIncrement <= 0`,
  skips the append silently (`0x75135F..0x7513AE`).
- `FindIndex` (`0x7514D0`) is the same linear `_strcmpi` search and never
  allocates.

**⚠ Open:** with a loose soundmd.ini that added three sounds (850 keys, 821
distinct names), the engine made 820 sounds, all three new ones among them.
Duplicate keys, WW-CRC clashes of key or section names, non-numeric keys and
names over 31 characters were ruled out offline. CosmeticExt now logs each
name that did not become a sound; record the cause here once it is known.

---

## Structural: what the mixer cannot do, and why to bake instead

The engine mixes in a callback on its own audio thread. The decoder is at
`0x40AA70`, and there are 8 critical sections around the channel state.
A channel has a **volume and a pan, nothing else**: no filter stage, no
send. Live low-pass or reverb would mean owning that mixing.

The practical alternative, used by CosmeticExt:

- Render distance variants offline (air absorption, ground comb, scattered
  tail) into an extra bag.
- Pick between them at `0x7509E0` by distance.

Lead for live filtering: a per-channel one-pole low-pass in the decoder's
output at 0x40AA70, with its coefficient from the channel's distance. This
is **⚠ Unverified**: nobody has tried it.

## Structural: the audio bag (`audio.idx`/`audio.bag`)

**Header.** `audio.idx` is "GABA" v2: magic `0x41424147`, version 2, count,
then 36-byte entries. Each entry is `Name[16]`, Offset, Size, SampleRate,
Flags, ChunkSize. Entries are sorted case-insensitively.

**Flags.** `1` stereo, `2` PCM, `4` 16-bit, `8` IMA ADPCM. Vanilla YR's bag
has 2285 samples, all 22050 Hz:

| Flags | Format | Samples |
|---|---|---|
| `12` | mono ADPCM, 512-byte chunks | 2192 |
| `6` | mono PCM16 | 84 |
| `13` | stereo ADPCM, 1024-byte chunks | 5 |
| `7` | stereo PCM16 | 4 |

The bag ships in `langmd.mix` → `audiomd.mix`.

**Mono ADPCM** (**VERIFIED**: decoded offline). A block is an int16 first
sample, a uint8 step index and 1 pad byte, followed by nibbles, **low nibble
first**. That gives 1017 samples per 512-byte block. Only this order makes
the block boundaries seamless.

**Stereo ADPCM** (**VERIFIED**: decoded offline on all 5 vanilla stereo
ADPCM samples). One 4-byte header per channel, then the body's bytes
alternate **L, R, L, R**. This decodes 2–3× smoother than the MS-IMA
4-byte-group layout or a nibble-per-channel split.

- **Easily mistaken:** assuming the MS-IMA WAV layout produces audible
  garbage only on stereo samples, which are rare, so it can go unnoticed.

**Antares/Ares** (`src/Misc/Audio.cpp`, hook `0x4011C0`):

- It loads `audio`, `ares`, then `audio01`..`audio99`. A mod can **add**
  samples without replacing `audio.bag`.
- `AddSample` (`0x4064A0`) strips leading `$`/`#` from sample names, falls
  back to loose `<sample>.wav` files, and caps a sound at **32 samples**.

## Confirmed via

- objdump of gamemd-spawn.exe: PlayAt entry, the whole of 0x750AC0, LoadAll's
  exit and the main-loop seat. Hook seats were checked with
  `check_hook_bounds --exe` and `check_hook_overlap` against this registry,
  plus a `.syhks00` sweep of every DLL in a live install. No other consumer
  was found.
- Antares source for the bag loader and sample cap.
- Offline decode and measurement of vanilla `audio.bag` for the ADPCM
  layouts.
- **Not yet observed in game:** the runtime behaviour of the CosmeticExt
  hooks.
