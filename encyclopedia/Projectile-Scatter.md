# Projectile scatter (`Inaccurate` / `BallisticScatter` / `FlakScatter`)

How `TechnoClass::Fire` perturbs a projectile's impact coordinate. Covers the two
magnitude-draw sites the Ares-lineage frameworks hook, the angle synthesis, and
the convergence point where the scattered coordinate is finally assembled.

Entries sorted by address.

---

### `0x4CAC40` / `0x4CACB0` / `0x4CAD00` — sqrt / cos / sin (CRT math helpers)

**Framework names**

Not hooked by any framework in the registry.

**What it does.** Standard double-precision `sqrt`, `cos`, `sin`. `sqrt` is
called at `0x6FE6F1` to finish the firer→target distance (`a²+b²+c²` assembled
across `0x6FE6D8`–`0x6FE6E6`); `cos`/`sin` at `0x6FE899`/`0x6FE8B8` turn the
scatter angle into coordinate components. Listed here so the scatter
disassembly reads cleanly.

**Confirmed via.** objdump of vanilla `gamemd.exe`, identified by call position
and operand shape — `sqrt` from the sum-of-three-squares feeding it, `cos`/`sin`
from the angle constants folded just above (see `0x6FE838`). Not confirmed
against a PDB symbol — the Antares PDB name dump has no entry for any of the
three. Treat the *names* as inferred, the *call sites* as verified.

---

### `0x65C7E0` — `RandomRanged` (synced game RNG)

**Framework names**

Not hooked; called by frameworks rather than patched.

**What it does.** `ScenarioClass::Instance->Random.RandomRanged(min, max)`.
`ECX` = `&Scenario->Random` (i.e. `ScenarioClass` instance at `0xA8B230`, field
offset `+0x218`), args pushed `max` then `min`. Returns in `EAX`.

**Why it matters here.** This is the **network-synced** RNG. Every scatter draw
in vanilla goes through it. Any hook that substitutes its own scatter value must
also draw from this RNG — substituting a `std::` or render-side RNG desyncs
multiplayer, and scatter is a particularly nasty place to do it because the
divergence is invisible until impact coordinates drift apart.

**Confirmed via.** objdump of vanilla `gamemd.exe`; cross-referenced with
Antares `src/Ext/BulletType/Hooks.cpp`, which calls
`ScenarioClass::Instance->Random.RandomRanged` at exactly these sites.

---

### `0x6FE709` — `TechnoClass_Fire_BallisticScatter1`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_Fire_BallisticScatter1` | 0x6 | `Ext/BulletType/Hooks.cpp` |
| Ares | `TechnoClass_Fire_BallisticScatter1` | 0x6 | `Ext/BulletType/Hooks.cpp` |

**What it does.** The magnitude draw for the **`FlakScatter=yes && Inviso=no`**
path. Vanilla: `RandomRanged(0, Rules->BallisticScatter)`. Antares replaces it
with `RandomRanged(BallisticScatter.Min ?? 0, BallisticScatter.Max ?? Rules)`,
returning the scalar in `EAX` and jumping to `0x6FE71C`.

**What it does *not* do — easily mistaken.** It does **not** produce the final
scatter distance. The value returned here is a *ceiling*, not a result. Just
before the hook, vanilla computes the true 3D distance to target
(`fild` dX/dY/dZ at `0x6FE6AD`+, sum of squares, `call 0x4CAC40` = `sqrt`,
stored to `[esp+0x18]`). Just after, it combines the two:

```
6FE71C  flds  [esp+0x18]        ; distance
6FE720  mov   ebx, eax          ; drawn scatter
6FE722  call  0x7C5F00          ; ftol -> eax = distance (int)
6FE727  imul  ebx, eax          ; drawn * distance
6FE72A  mov   eax, [ebp+0xC]    ; weapon index
6FE732  call  [edx+0x168]       ; ObjectClass::GetWeaponRange(idxWeapon)
6FE73D  idiv  ecx               ; / weapon range
```

giving **`final = drawn × distance ÷ GetWeaponRange(idxWeapon)`** — a linear
ramp normalised by weapon range: 0 at point blank, exactly `drawn` at maximum
range, and never more than `drawn`.

Two traps follow. First, this path **already scales scatter with range**, so
"vanilla scatter is range-independent" is wrong *here* (it is true at
`0x6FE7FE`). Second, because the ramp is normalised, raising
`BallisticScatter.Max` cannot make a weapon scatter *more than* the drawn value
at any range — the normalisation is the cap. A hook wanting unbounded
range-driven growth must replace the whole expression, not just the draw.

It also does not cover the non-FlakScatter path — that is `0x6FE7FE`.

**Used by / interactions.** Antares and Ares only, and those two are mutually
exclusive, so this is *not* a live co-loadable conflict (it falls in the 943
inherited Antares↔Ares overlaps excluded from `conflicts.md`). It **does**
conflict with any third-party DLL that hooks the same address: Syringe runs hooks
in load order and the first to return a non-zero address jumps there, so a second
hook returning `0x6FE71C` never executes. Load order silently decides the winner.

**Register / calling convention.** `[esp+0x68]` = `BulletTypeClass*` (Antares
reads it via `GET_STACK`). Return the scalar in `EAX`, jump to `0x6FE71C`.
Enclosing function is `TechnoClass::Fire`, which begins at `0x6FDD50`
(`push ebp; mov ebp,esp; sub esp,0xA4`) — see `0x6FE8D8` for the frame map.

**Confirmed via.** objdump of vanilla `gamemd.exe` (`VA − 0x400000` = file
offset); Antares source `src/Ext/BulletType/Hooks.cpp`.

`[edx+0x168]` is identified as **`ObjectClass::GetWeaponRange(int idxWeapon)`**
by counting vtable slots against YRpp's own offset-encoded placeholder names:
`ObjectClass.h:180` declares `vt_entry_1B0` (= offset `0x1B0`), and walking back
18 new-slot declarations (`IsCellOccupied` `0x1AC` … `Destroy` `0x170`,
`ReceiveDamage` `0x16C`) lands on `GetWeaponRange` at `0x168`. Corroborated
independently by its signature: it takes a single `int idxWeapon`, which is
exactly what `[ebp+0xC]` supplies. Not cross-checked against a live vtable dump,
but two independent lines of evidence agree.

⚠ An earlier revision of this entry claimed the `idiv` divided by *firer→target
distance*. That was wrong — distance is the **multiplicand** (`imul` at
`0x6FE727`); the divisor is weapon range.

---

### `0x6FE7FE` — `TechnoClass_Fire_BallisticScatter2`

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `TechnoClass_Fire_BallisticScatter2` | 0x5 | `Ext/BulletType/Hooks.cpp` |
| Ares | `TechnoClass_Fire_BallisticScatter2` | 0x5 | `Ext/BulletType/Hooks.cpp` |

**What it does.** Magnitude draw for the **`FlakScatter=no || Inviso=yes`** path.
Vanilla: `RandomRanged(BallisticScatter/2, BallisticScatter)` — note the *half*
floor, which is where Antares' asymmetric defaults come from
(`Min` defaults to `BallisticScatter/2` here vs `0` at `0x6FE709`). Returns in
`EAX`, jumps to `0x6FE821`.

**What it does *not* do — easily mistaken.** Unlike `0x6FE709`, this path is
**not** followed by a range division. Instead it proceeds directly to angle
synthesis at `0x6FE827`. The two scatter paths are genuinely different
mechanics, not two entry points to one routine — do not assume a fix at one site
applies to the other.

**Register / calling convention.** `[esp+0x68]` = `BulletTypeClass*`. Return
scalar in `EAX`, jump to `0x6FE821`. The returned value is stashed at
`[esp+0x20]` by the vanilla code at `0x6FE82E`.

**Confirmed via.** objdump of vanilla `gamemd.exe`; Antares source.

---

### `0x6FE838` — scatter angle synthesis (unhooked)

**Framework names**

Not hooked by any framework in the registry.

**What it does.** Draws the scatter *direction* as a uniform angle over the full
circle:

```
6FE838  call 0x65C7E0           ; RandomRanged(0, 0x7FFFFFFE)
6FE845  fmul 4.656612877e-10    ; / 2^31   -> [0,1)
6FE84B  fmul 6.283185307        ; * 2pi    -> [0,2pi)
6FE851  fsub 1.570796327        ; - pi/2
6FE857  fmul -10430.06          ; radians -> 16-bit binary angle (-65536/2pi)
6FE862  movswl ax / sub 0x3FFF  ; wrap into signed 16-bit
6FE872  fmul -9.5876725e-05     ; * 2pi/65536 -> back to radians
6FE878  fstp [esp+0x70]         ; theta (double)
```

The round-trip through a 16-bit binary angle is not redundant — it **quantises
theta to 1/65536 of a circle**, which is what keeps the result bit-identical
across clients. Anyone reimplementing the angle must preserve that quantisation
or accept desync risk.

**Confirmed via.** objdump of vanilla `gamemd.exe`; FP constants decoded directly
out of `.rdata` (`0x7E3570`, `0x7E3CC0`, `0x7E2820`, `0x7E2818`, `0x7E2810`).

---

### `0x6FE8D8` — scattered impact coordinate assembly (unhooked)

**Framework names**

**Not hooked by any framework** — verified 0 hits in `registry/hooks.csv` for
`0x6FE8D8`, `0x6FE87C`, `0x4CACB0`, `0x4CAD00`.

**What it does.** Where the magnitude and the angle become an actual coordinate,
and — importantly — **where both scatter paths converge**. `0x6FE7F9` is an
unconditional `jmp 0x6FE8D8` from the end of the FlakScatter path.

`0x6FE625` does `lea eax,[esp+0x94]`, taking the address of the impact
`CoordStruct` — so `[esp+0x94]`/`+0x98`/`+0x9C` are its `X`/`Y`/`Z`.

```
6FE899  call 0x4CACB0           ; cos(theta)
6FE89E  fmul [esp+0x20]         ; * scatter
6FE8A2  fsubr [esp+0xA8]        ; targetY - scatter*cos(theta)
6FE8B4  mov  [esp+0x20], eax    ;   stashed
6FE8C1  add  esp, 0x10          ; <-- offsets shift here
6FE8B8  call 0x4CAD00           ; sin(theta)
6FE8BD  fmul [esp+0x28]         ; * scatter
6FE8C4  fiadd [esp+0x30]        ; targetX + scatter*sin(theta)
6FE8CD  mov  [esp+0x94], eax    ; -> X
6FE8D4  mov  eax, [esp+0x10]    ;   the stashed cos result
6FE8D8  ...                     ; <-- FlakScatter path jumps in here
6FE8E0  mov  [esp+0x98], eax    ; -> Y
6FE8E7  mov  [esp+0x9C], edi    ; -> Z, unmodified
```

Two facts worth writing down:

1. **One shared scalar drives both axes** (`X = targetX + s·sin θ`,
   `Y = targetY − s·cos θ`), so the impact distribution is a **circle**, never an
   ellipse. Per-axis scatter shaping is impossible at `0x6FE709`/`0x6FE7FE` —
   those sites only ever see one number. It has to be done here.
2. **Z is never scattered.** `EDI` receives the Z coordinate at `0x6FE649`
   (`mov edi,[eax+0x8]`, adjusted by `sub edi,eax` at `0x6FE65B`) and is not
   written again anywhere before the store at `0x6FE8E7`. There is no vertical
   scatter term in vanilla at all, so adding one means *introducing* a term, not
   scaling an existing one.

**What it does *not* do — easily mistaken.** This is not a scatter-specific
function you can cleanly replace; it is the tail of `TechnoClass::Fire`'s
coordinate setup, and the surrounding frame is shared with non-scatter fire
paths. Note also the `add $0x10, %esp` at `0x6FE8C1` — stack offsets before and
after that instruction differ, which is an easy way to read the wrong slot.

**These coordinates are deltas, not absolute positions.** The triple at
`[esp+0x30]`/`+0x34`/`+0x38` is the firer→target **aim vector**, written at
`0x6FE643`/`0x6FE65D`/`0x6FE669` and read-only thereafter. Two proofs: the
distance at `0x6FE6AD`+ is `sqrt(a²+b²+c²)` over exactly those slots (summing
squares of absolute map coordinates would be meaningless), and the assembled
output is consumed at `0x6FE902` by `fild [esp+0x94]` / `neg eax` /
`call 0x4CAE30` (**atan2**) → `fsub π/2` → `fmul -10430.06`, i.e. turned into a
binary facing angle. You cannot `atan2` absolute coordinates into a direction.

So scatter perturbs the **aim vector**, which is then converted to a facing.
Anyone overriding scatter here has the *unscattered* vector available in-frame
and does not need to re-derive it from the target pointer.

Note the **two paths arrive here having done different arithmetic**: the
`FlakScatter` path already applied `× distance ÷ weaponRange` (see `0x6FE709`),
the other did not. A hook that recomputes from `[esp+0x30..0x38]` can ignore
this entirely; one that tries to *scale* the assembled result cannot, and would
need the discriminator at `[esp+0x68]→[+0x29E]`.

**Used by / interactions.** Nothing hooks it today, which makes it attractive as
a conflict-free insertion point for a third-party DLL that wants to reshape
scatter without fighting Antares over `0x6FE709`/`0x6FE7FE`.

**Register / calling convention.** The enclosing `TechnoClass::Fire` starts at
`0x6FDD50`:

```
6FDD50  push ebp / mov ebp,esp
6FDD53  and  esp, 0xFFFFFFF8    ; runtime stack alignment
6FDD56  sub  esp, 0xA4
6FDD5C  push ebx / esi / edi
```

⚠ **The `and esp,0xFFFFFFF8` means `ebp − esp` is not a compile-time constant** —
it depends on the caller's alignment. Locals in this function therefore cannot
be addressed as `ebp − k`; only the arguments (above `ebp`) are `ebp`-safe.
This is an easy way to write a hook that works in one call path and corrupts
the frame in another.

Arguments, valid function-wide:

| Slot | Holds | Evidence |
|---|---|---|
| `ESI` | firer (`this`) | `mov esi,ecx` at `0x6FDD5E`; written **once** in the entire function — every later occurrence is a read (`mov %esi,%ecx` setting up thiscalls) |
| `[ebp+0x8]` | `AbstractClass* pTarget` | *written* at `0x6FE1D5`/`0x6FE245` (retargeting), consumed near `Fire_CreateBullet` at `0x6FE554` |
| `[ebp+0xC]` | `int idxWeapon` | pushed to `GetWeaponRange(int)` at `0x6FE72A` |

So firer, target and weapon index are **all live at `0x6FE8D8`** — enough to
recompute range-dependent behaviour from scratch at this site.

At the address itself: `EAX` = the Y value about to be stored, `EDI` = Z, and
the coordinate triple lands at `[esp+0x94]`/`+0x98`/`+0x9C`.

**Both paths converge here with identical `esp`.** Tracing each: path 1 does
`push`/`push` → `call 0x4CACB0` → `push`/`push` → `call 0x4CAD00` →
`add esp,0x10` (`0x6FE7E2`); path 2 is the same shape with its `add esp,0x10` at
`0x6FE8C1`. Both net to the same `esp` *and* use the same slots — `E+0x10` for
the stashed cos result, `E+0x30..0x38` for the aim vector, `E+0x94` for X. They
differ only in which scratch slot holds θ versus the magnitude, and both are
consumed before convergence. So `esp`-relative reads at `0x6FE8D8` **are**
path-agnostic:

| Slot | Contents |
|---|---|
| `[esp+0x30]` / `+0x34` / `+0x38` | unscattered aim vector (deltas) |
| `[esp+0x94]` | X, already scattered |
| `[esp+0x68]` | `BulletTypeClass*` |

Still beware the `add esp,0x10` itself: offsets quoted *before* `0x6FE8C1` in the
listing above refer to different slots than the same literals after it.

⚠ An earlier revision of this entry claimed `esp`-relative reads here were **not**
path-agnostic because the paths had different stack histories. That was wrong —
they converge with identical `esp`. The claim was asserted from partial tracing
rather than a full stack walk of both paths.

**Confirmed via.** objdump of vanilla `gamemd.exe`, `0x6FDD50–0x6FE950`
(prologue; full `ESI` and `EDI` write traces; `[ebp+8]`/`[ebp+0xC]` use trace;
complete stack walk of both scatter paths; write-trace of the `0x30/0x34/0x38`
triple). Registry cross-check for existing hooks. **Not** confirmed by live
debugger or in-game test — the register/offset table should be validated before
anyone relies on it, and the `esp`-relative offsets especially.

---

### `0x6FE8EE` — aim vector consumed (unhooked)

**Framework names**

Not hooked by any framework in the registry (0 hits for `0x6FE8EE`, `0x6FE902`,
`0x4CAE30`).

**What it does.** The instruction after the scattered aim vector is fully
assembled. Reads `[ecx+0x2DC]` and `[ecx+0x29C]` off the `BulletTypeClass*`
(loaded into `ECX` from `[esp+0x68]` at `0x6FE8DC`) to choose between two
facing-derivation routes; the fallthrough at `0x6FE902` converts the vector to a
binary facing angle via `atan2` (`0x4CAE30`), `fsub π/2`, `fmul -10430.06`,
`ftol`, then narrows to 16 bits with `mov %ax,[esp+0x10]`.

**Why it's interesting.** This is the last point at which the aim vector is
still data rather than an angle, and the triple at
`[esp+0x94]`/`+0x98`/`+0x9C` is complete and untouched. For anything wanting to
override scatter wholesale it is a better insertion point than `0x6FE8D8`, which
sits mid-assembly and whose 6 stolen bytes would straddle the `EBX`/`ECX` loads
that this code depends on.

**What it does *not* do — easily mistaken.** It does not apply the scatter — by
here that is long done (`0x6FE899`+ / `0x6FE7B7`+). And the `neg eax` at
`0x6FE902` operates on a register set much earlier, not on the vector.

**Register / calling convention.** `ECX` = `BulletTypeClass*`, `EBX` =
`[esp+0x40]` (both loaded at `0x6FE8D8`/`0x6FE8DC`). Vector at
`[esp+0x94]`/`+0x98`/`+0x9C`. Stolen bytes at `0x6FE8EE` would be `0x6`
(`mov 0x2dc(%ecx),%edx`).

**Confirmed via.** objdump of vanilla `gamemd.exe`, `0x6FE8E7–0x6FE950`.
`0x4CAE30` is identified as `atan2` from its two pushed doubles and the
radians→binary-angle constant folding that immediately follows — **inferred**,
not confirmed against a PDB symbol. No in-game testing.
