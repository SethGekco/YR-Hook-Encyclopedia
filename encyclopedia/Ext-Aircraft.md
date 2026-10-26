# Subsystem: Aircraft

Hooks in `AircraftClass` and aircraft rendering. Entries sorted by address.

---

### `0x4147F9` — AircraftClass::Draw (shadow branch)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Phobos | `AircraftClass_Draw_Shadow` | 0x6 | `Hooks.MatrixOp.cpp` |
| Kratos | `AircraftClass_Draw_Shadow_SkipPhobos` | 0x6 | `Hooks/AircraftExtHook.cpp` |

**What it does.** This address sits at the point in `AircraftClass::Draw` where
the game is about to draw the aircraft's ground shadow. Phobos hooks it to run
its own **matrix-based** shadow rendering: it pulls the locomotor's shadow matrix
(`loco->Shadow_Matrix`) and applies height-based scaling driven by RulesExt
globals (`AirShadowBaseScale_log`, `HeightShadowScaling`, per-type
`ShadowSizeCharacteristicHeight`). So Phobos *replaces* the vanilla shadow draw
with a scaled, locomotor-aware one, and returns `0x4148A5` (past the whole shadow
block) when the aircraft should have no shadow.

**What it does *not* do — easily mistaken.**
- It is **not** a general "draw the aircraft" hook — it is specifically the
  *shadow* branch. The body sprite/voxel is drawn elsewhere.
- Hooking it does **not** by itself suppress the shadow. Vanilla still has its
  own shadow path after this point; to actually cancel a shadow you must return
  to the address *past* the whole shadow block, not just skip one framework's
  hook (see Kratos's two different return targets below).
- Phobos's presence here means a naive third hook at `0x4147F9` will **fight
  Phobos**, not vanilla.

**Used by / interactions — this is a real conflict, by design.** Both Phobos and
Kratos hook this exact address; it appears in `registry/conflicts.md`. This is
not the benign "everyone hooks the same call site" case — Kratos hooks it
*specifically to arbitrate Phobos*:

- Gated behind `AudioVisual::AllowTakeoverPhobosShadowMaker`. When **off**,
  Kratos returns `0` (fall through) and Phobos's shadow logic runs normally.
- When **on**, Kratos decides per-aircraft:
  - if the aircraft should have no shadow (`Type->NoShadow`, cloaked, sinking,
    or the locomotor reports no shadow) it returns **`0x4148A5`** — jumping
    clean past the *entire* shadow block, vanilla **and** Phobos.
  - otherwise it returns **`0x4147FF`**, which skips only Phobos's hook and lets
    the vanilla shadow draw proceed.

  So on a Kratos+Phobos build, load order and that one INI-driven flag decide
  whose shadow code wins. This is the canonical example of why the registry
  keys on address: the collision is invisible in a per-framework hook list and
  obvious the moment you group by address.

**Confirmed via.**
- Kratos behaviour: read directly from `Kratos/src/Hooks/AircraftExtHook.cpp`
  (the `return 0x4148A5;` / `return 0x4147FF;` branches and the
  `AllowTakeoverPhobosShadowMaker` gate). **Confirmed.**
- Phobos behaviour: read directly from cloned upstream
  `Phobos/src/Ext/TechnoType/Hooks.MatrixOp.cpp` (the `DEFINE_HOOK(0x4147F9, …)`
  body — matrix shadow, RulesExt scaling, and the `FinishDrawing = 0x4148A5`
  skip on cloak/sink/`NoShadow`/no-shadow-locomotor). **Confirmed.** Note Phobos
  and Kratos independently use the *same* skip conditions and the *same*
  `0x4148A5` exit, which cross-validates both.
- Return address `0x4148A5`: confirmed as the shadow-block exit by **both**
  Phobos and Kratos source. `0x4147FF` (skip-Phobos-only) is Kratos-specific and
  is the instruction right after the hooked bytes. Not re-derived from
  `gamemd.exe` disassembly here, but corroborated across two frameworks.

---

### `0x4157C0` — AircraftClass spy-plane / paradrop overfly  ⚠ five passes are hardcoded

Not a hook recommendation — a behavioural fact that reads as a bug and costs real
debugging time. Reported in game as **"the spy plane circles its target instead of
doing a flyby."**

**The mechanism.** The overfly mission (function start `0x4157C0`, ends `0x41595C`)
re-tests distance every tick rather than following a fixed trail:

```
415934:  mov ecx, ds:0x8871E0          ; RulesClass::Instance
41593a:  cmp eax, [ecx+0x54C]          ; distance vs [General]ParadropRadius
415940:  jg  0x415956                  ; too far -> keep flying
415942:  ...call [edx+0x1E8]...        ; in range -> do the pass
415950:  dec BYTE PTR [esi+0x6D3]      ; <-- passes remaining
415956:  mov eax,3 ; pop esi ; ret
```

`[esi+0x6D3]` is `AircraftClass::NumParadropsLeft` (`sizeof(FootClass)` is `0x6C0`;
the field sits at +0x13 into `AircraftClass`). **Exactly one site initialises it:**

```
0x413D74:  mov byte ptr [esi+0x6D3], 5     ; inside AircraftClass::AircraftClass (0x413D20)
```

So every aircraft is born with five passes, and a spy plane makes all five unless
something caps it. Five passes over one target is what looks like orbiting. The
flight path itself is fine — it simply repeats.

**The cap is a Phobos tag, on the WEAPON, not the aircraft.**
`CheckSpyPlaneCameraCount` (Phobos `Ext/Aircraft/Hooks.cpp`, hooks at `0x415666`
and `0x4157EB`) returns "no limit" when `Strafing.Shots` is unset, so a stock
configuration inherits the hardcoded 5:

```ini
[SpyCameraWeapon]      ; the aircraft's Primary, NOT the aircraft section
Strafing.Shots=1       ; one pass, then leave
```

✅ **Verified in game:** that single line turned persistent circling into a clean
flyby.

**Ruled out along the way, so nobody repeats it:**
- **Speed.** The plane's `Speed` had been doubled (15 → 30) with `ROT` left at 2 —
  a very plausible "wider turn radius" story. Reverting it changed nothing: speed
  alters how wide each loop is, not how many there are.
- **A third-party DLL.** Settled by uninjecting the suspect DLL entirely and
  observing identical behaviour, with its absence confirmed in the log.

**Confirmed via.** objdump of `gamemd.exe` at the cited addresses; a byte-pattern
search for writes to `+0x6D3` (exactly one — the constructor); Phobos source; and
an in-game before/after.

---

### `0x415960` — AircraftClass::Mission_ParadropOverfly  ⚠ a hidden map gate hangs the plane

The paradrop mission, `0x415960`–`0x415A42`. The address usually hooked inside it
is `0x415997` (the distance-vs-`[General]ParadropRadius` compare). This entry is
about what happens **after** that compare says yes, because that is where a
paradrop silently fails.

**The whole function, annotated.**

```
415960:  sub  esp,0xC
415964:  mov  esi,ecx                    ; esi = AircraftClass* this
415966:  mov  eax,[esi+0x2B4]            ; this->Target
41596C:  movb [esi+0x6D2],1              ; IsLocked = true
415975:  je   0x415A0A                   ; no target      -> leave
41597B:  mov  ecx,[esi+0x118]            ; Passengers.FirstPassenger
415983:  je   0x415A0A                   ; nobody aboard  -> leave
41598C:  call 0x5F6440                   ; distance to target -> eax
415991:  mov  ecx,[0x8871E0]             ; RulesClass::Instance
415997:  cmp  eax,[ecx+0x54C]            ; vs [General]ParadropRadius
41599D:  jle  0x4159C8                   ; close enough   -> DROP branch
; ---- too far -------------------------------------------------------------
41599F:  mov  al,[esi+0x6D3]             ; NumParadropsLeft
4159A5:  movb [esi+0x6D2],0              ; IsLocked = false
4159AE:  jle  0x415A11                   ; out of passes  -> leave
4159B8:  call [edx+0x1E8]                ; QueueMission(0x1A) -> come around again
4159BE:  mov  eax,5 ; ret
; ---- DROP branch ---------------------------------------------------------
4159C8:  lea  ecx,[esi+0x9C]             ; the PLANE's own Location, not the target
4159EB:  mov  ecx,0x87F7E8               ; MapClass::Instance
4159F0:  call 0x5785F0                   ; MapClass::IsWithinUsableArea(CoordStruct)
4159F5:  test al,al
4159F7:  je   0x415A39                   ; <-- FALSE: mov eax,5 ; ret. NOTHING ELSE.
4159FB:  call 0x415C60                   ; AircraftClass::Paradrop (one passenger)
415A00:  mov  eax,5 ; ret
; ---- leave ---------------------------------------------------------------
415A11:  call [eax+0x3C8] / [edx+0x480] / QueueMission(4)
```

**The trap.** The `je 0x415A39` at `0x4159F7` returns a five-frame delay and does
**nothing else** — no drop, no new mission, no change of destination. Every other
exit from this function either drops, re-queues a pass, or sends the plane away.
That one does not. So an aircraft that has reached its destination, is inside the
drop radius, and whose **own coordinates** read as outside the usable area will
re-ask the same question every five frames for the rest of the match.

Reported in game as **"the paradrop plane hovers in the air exactly where it is
supposed to drop, instead of doing a flyby"** — intermittently, on the same map,
with the same country.

**It also explains partial payloads.** `AircraftClass::Paradrop` releases exactly
one passenger per call (see `0x415C60` below), so a five-man stick needs five
mission ticks. An interruption part-way leaves the rest aboard. "Some planes drop
a fraction of their payload" and "some planes hover" are the **same event** at
different moments in the sequence, not two bugs.

**What the gate actually tests.** `MapClass::IsWithinUsableArea(const CoordStruct&)`
at `0x5785F0` truncates the coords to a cell (`>>8`, X and Y only — altitude is
irrelevant) and tails into `IsWithinUsableArea(CellStruct, checkLevel=true)` at
`0x578460`. That one reads `MapClass+0xF4/0xFC/0x100/0x104/0x108` (the map and
visible rects) and, **when `checkLevel` is set, shifts the test by the cell's
`Level`** (`movsbl 0x11B(%eax)` — `CellClass::Level`) before comparing. So the
playable-area boundary this test draws is **height-dependent**: the same cell can
pass or fail depending on terrain elevation. That is the mechanism behind the
"maybe it is cliff-related" hunch — it is not cliffs as such, it is elevation
anywhere near the usable-area boundary.

**Do not try to fix it by widening the radius.** A larger `ParadropRadius` makes
the plane enter the DROP branch *earlier*, i.e. further out and closer to the map
edge it spawned from, which makes the gate *more* likely to refuse. If anything
the override pushes in the wrong direction.

**Ruled out, so nobody repeats it:** a third-party superweapon DLL was suspected
twice and cleared twice by uninjecting it and reproducing the hover anyway. The
gate is vanilla.

**✅ CONFIRMED IN GAME, 2026-10-25.** One skirmish, 18 hover events, every single
one of them `usable=0` — no exceptions, no other correlate. The boundary is
exact: of **217 distinct plane positions** logged, every cell with `X+Y <= 220`
passed and every cell with `X+Y >= 221` failed, on a map whose `MapRect` is
`(0,0 76x75)` and `MapCoordBounds` `(L1 T1 R150 B150)`. All eleven refused cells
sit in one small patch (X 116–122, Y 102–105) at the south-east edge of the
playable diamond. The plane overshoots its target by a cell or two and crosses
the line while still inside the drop radius:

```
f28031  at=(117,103)  usable=1  dist=30   -> released
f28036  at=(118,103)  usable=0  dist=349  -> refused, 5 of 8 still aboard
```

**The payload arithmetic checks out too.** Planes carried **8**, not five, and
released one per tick; 17 of the 18 were refused holding exactly 5, having
already dropped 3. "Partial payload" and "hover" are one event, as predicted.

**It is not always permanent.** One plane recovered unaided — refused at
f100920, came around, found a usable cell at f101034 and finished its stick. The
other 14 left the overfly trace entirely after being refused and never came
back; that log cannot say whether they were shot down, retreated, or stalled in
`Mission_ParadropApproach` (mission 26, a different function, not instrumented).

**The repair, if you need one.** Do not try to force the drop — `Paradrop`
releases at the plane's own position and that position is the thing the gate
just rejected. Instead, answer the *distance* test with "not close enough":
a hook at `0x415997` that returns `0x41599F` instead of `0x4159C8` when
`IsWithinUsableArea(plane coords)` is false sends the engine down a branch it
already runs thousands of times a match — clear `IsLocked`, queue
`ParadropApproach`, come around — rather than into the branch that does nothing.
No new address, no invented behaviour.

⚠ **Bound it.** That branch reads `NumParadropsLeft` and only gives up at zero,
and across the whole match above that field was observed at 4 and 5 and never
lower, so nothing guarantees the engine would ever stop re-approaching.
Unbounded deferral trades a plane that hovers for a plane that circles.
SuperWeaponExt caps it at three go-arounds and then hands the plane back.

**Confirmed via.** objdump of `gamemd-spawn.exe` at every address quoted;
`MapClass.h` in YRpp, which names `0x5785F0` / `0x578460` / `0x578540` as the
three `IsWithinUsableArea` overloads and `0x87F7E8` as `MapClass::Instance`,
matching the `mov ecx,0x87F7E8` in the call site; and the in-game log above,
from a diagnostic that evaluates the same predicate one hook earlier in the same
tick.

---

### `0x415C60` — AircraftClass::Paradrop (function entry)  — unclaimed, one passenger per call

```
415C60:  sub  esp,0x20              ; 5-byte hook: 83 ec 20 53 56
415C63:  push ebx
415C64:  push esi                   ; 0x415C65 is the next boundary (57 push edi)
415C66:  mov  edi,ecx               ; ecx = AircraftClass* this
415C68:  lea  ecx,[edi+0x114]       ; &this->Passengers
415C6E:  call 0x473430              ; PassengersClass::RemoveFirstPassenger
415C73:  mov  esi,eax
415C77:  je   0x415ECD              ; nobody aboard -> bail
415C7D:  mov  ebx,[edi+0x2FC]       ; a counter, decremented per release...
415C89:  dec  ebx
415CA6:  mov  al,[edi+0x2FC]        ; ...whose LOW BIT picks the drop side
415CAC:  test al,1                  ;    (+0x3FFF vs -0x3FFF on the facing)
```

**One passenger per call.** This is the fact that makes partial payloads legible:
the function does not loop over the cargo. Its caller
(`Mission_ParadropOverfly`, above) calls it once per mission tick, every five
frames, until `FirstPassenger` is null.

**Availability.** The entry is **free**. In the registry, the nearest claims
inside this function are Antares/Ares `AircraftClass_Paradrop_Units` at
`0x415CA6` and `AircraftClass_Paradrop_Carryall` at `0x415DF6`, both far past the
five-byte window, and nothing is registered between `0x415A7A` and `0x415CA6`. A
size-5 hook at `0x415C60` lands cleanly on the boundary at `0x415C65`.

**Good for.** Counting or logging actual releases; reading the payload before it
shrinks (`Passengers.NumPassengers` is still pre-decrement here); vetoing a drop
by returning past the function.

**Not good for.** Changing *where* the stick lands — the lateral offset is picked
later from `[edi+0x2FC]`'s parity, and the Antares hook at `0x415CA6` already sits
in that code.

**Field notes.** `AircraftClass` layout used above is confirmed against the
disassembly rather than assumed: `+0x114` `Passengers.NumPassengers`, `+0x118`
`Passengers.FirstPassenger`, `+0x6D2` `IsLocked`, `+0x6D3` `NumParadropsLeft`.
YRpp's declaration order in `AircraftClass.h` agrees with all four. Nothing is
claimed about `+0x2FC` beyond what the two instructions above show.

**Confirmed via.** objdump of `gamemd-spawn.exe`; `registry/hooks.csv`;
SuperWeaponExt's `check_hook_bounds.py --exe`, which boundary-checks the hook
against the shipped binary. Used in anger: SuperWeaponExt
`src/Ext/SWType/Hooks.ParaDrop.cpp`, `AircraftClass_Paradrop_Trace` (observe-only,
returns 0).
