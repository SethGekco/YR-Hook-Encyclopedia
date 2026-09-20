# Render Layers & Y-Sorting

How YR decides which object draws in front of which: `ObjectsInLayers`,
`LayerClass::AddObject`, `LayerClass::Sort`, and `GetYSort`.

The single most important fact is at the top, because it silently invalidates
the obvious approach to z-ordering anything.

---

## Structural note — only **one** of the five layers is ever sorted

`MapClass::ObjectsInLayers` (`0x8A0360`) is an array of five `LayerClass`, each
`0x18` bytes (a `DynamicVectorClass<ObjectClass*>` plus overrides):

| Index | `Layer` | Address | Sorted? |
|---|---|---|---|
| 0 | `Underground` | `0x8A0360` | no |
| 1 | `Surface` | `0x8A0378` | no |
| 2 | `Ground` | `0x8A0390` | **yes** |
| 3 | `Air` | `0x8A03A8` | no |
| 4 | `Top` | `0x8A03C0` | no |

Two independent mechanisms both single out layer 2, and nothing else.

**1. Insertion.** `DisplayClass::Submit` asks for a sorted insert only when the
object's layer is exactly 2 (`0x4A9740`):

```
4a973d  call [eax+0x78]          ; ObjectClass::InWhichLayer() -> edi
4a9742  cmp  edi, 0xffffffff
4a9745  je   skip
4a9747  cmp  edi, 2              ; <-- Ground?
4a974a  lea  edx, [edi+edi*2]    ; edx = layer * 3
4a974d  sete cl                  ; cl = (layer == 2)
4a9750  push ecx                 ;  the `sorted` argument
4a9751  push esi                 ;  the object
4a9752  lea  ecx, [edx*8+0x8a0360]   ; &ObjectsInLayers[layer], stride 24
4a9759  call 0x5519b0            ; LayerClass::AddObject(obj, sorted)
```

**2. Maintenance.** `LayerClass::Sort` (`0x551A30`) has exactly **one** caller in
the whole binary, `0x55DBC8`, and it hardcodes `ecx = 0x8A0390` — `Ground`.

So an object in `Surface`, `Air` or `Top` is appended in submit order and never
reordered. **Its `GetYSort` is never called, and any sort bias on it is dead.**

---

## `LayerClass::AddObject` (`0x5519B0`) — two completely different behaviours

```cpp
bool LayerClass::AddObject(ObjectClass* pObject, bool sorted);
```

* `sorted == true` → tail-calls `0x551A90`, an **ordered insert**: scan for the
  first entry `i` where `item[i]->GetYSort() > newObj->GetYSort()`
  (via `ObjectClass::SortsAfter`, `0x5F6220`), shift the tail right, insert at
  `i`. Correct placement immediately, O(n).
* `sorted == false` → plain append: `Items[Count++] = pObject`.

---

## `LayerClass::Sort` (`0x551A30`) is a **single bubble pass**, not a sort

```
551a41  ...
551a44  mov  esi, [eax+ebx*4+4]      ; item[i+1]
551a48  mov  edi, [eax+ebx*4]        ; item[i]
551a4f  call [edx+0xb8]              ; esi->GetYSort()
551a5d  call [eax+0xb8]              ; edi->GetYSort()
551a63  cmp  [esp+0x10], eax         ; ysort(i+1) vs ysort(i)
551a67  jge  no_swap                 ; swap only if ysort(i+1) < ysort(i)
```

One forward pass, ascending by `GetYSort`, called once per frame. This is a
*maintenance* pass over an already-near-sorted array, not a full sort — it
relies on `AddObject(sorted=true)` having placed things correctly.

⚠ **Asymmetric convergence.** A forward bubble pass carries an element any
distance toward the **back** in one call, but only **one slot toward the front
per call**. Anything that needs a *lower* `GetYSort` than its neighbours creeps
forward at one index per frame. If you ever insert into `Ground` unsorted, a
"draw behind" object is mis-ordered for up to `Count` frames.

---

## `GetYSort` (vtable `+0x0B8`)

`ObjectClass::GetYSort` (`0x5F6BD0`) calls vtable `+0xAC` twice and sums two
components of the result:

```
5f6be0  call [eax+0xac]        ; -> edi
5f6bf1  call [edx+0xac]        ; -> eax   (same function, second buffer)
5f6bf7  mov  ecx,[edi+0x4]     ; .Y
5f6bfa  mov  edx,[eax]         ; .X
5f6bfc  add  ecx,edx
```

⚠ **vtable `+0xAC` is `ObjectClass::GetRenderCoords` (`0x41BE00`), which returns
a `CoordStruct`** — not a rectangle. So the key is
`renderCoords.X + renderCoords.Y` **in leptons, and one cell is 256.**

(An earlier revision of this page called it a render rectangle and warned
against assuming 256. That was wrong. Measured in game: a corpse anim reported
a base value of `73036`, exactly the magnitude a world position gives, and the
correction came only after two sub-cell bias values — `-16` and `-64`, i.e. a
sixteenth and a quarter of a cell — visibly did nothing.)

`AnimClass::GetYSort` (`0x422BC0`) overrides it:

```
call 0x5F6BD0            ; the geometric base
mov  ecx, [esi+0x104]    ; the INSTANCE's YSortAdjust
add  eax, ecx
```

⚠ **`AnimTypeClass::YSortAdjust` is never read.** The base never touches it and
the constructor does not copy it to the instance. Setting the type's field is a
no-op; you must set `AnimClass +0x104` on each instance after construction.

Lower value = earlier in the array = drawn first = **behind**.

---

## `AnimClass::InWhichLayer` (`0x424CB0`) — anims default to `Air`

```
424cb0  mov  eax, [ecx+0xcc]     ; attached-to object?
424cb8  je   no_owner
424cba  mov  eax, 2              ; attached  -> Ground
424cbf  ret
424cc0  mov  eax, [ecx+0xc8]     ; the AnimTypeClass
424cc8  je   no_type
424cca  mov  eax, [eax+0x364]    ; -> Type->Layer
424cd0  ret
424cd1  mov  eax, 3              ; no type   -> Air
```

And `AnimTypeClass::AnimTypeClass` (`0x4276D4`) initialises `Layer` to `3`:

```
4276d4  mov  DWORD PTR [esi+0x364], 0x3     ; Layer = Air
```

**Consequence for anyone building a decal, corpse, scorch mark or any anim that
must sit *under* units:** a freshly allocated `AnimTypeClass` is in `Air`, which
is unsorted *and* drawn after `Ground`, so the anim is unconditionally on top of
every infantry and vehicle — and no amount of `YSortAdjust` will change it,
because the field is never consulted in that layer. Set `Type->Layer =
Layer::Ground` (2) **first**; only then does the sort bias do anything.

Attaching the anim to an object is the other route to `Ground` (the `+0xCC`
branch above), but that couples the anim's lifetime to the object's.

⚠ `Layer::Surface` (1) is **not** a safe "under everything" choice: an anim
placed there has been observed not to draw at all. It is also unsorted, so it
buys nothing over `Ground` anyway.

---

## Practical checklist for "draw this anim under units"

1. `pType->Layer = Layer::Ground;` — **without this nothing else matters.**
2. `pAnim->YSortAdjust = <small negative>;` on the **instance**, not the type.
3. Size the magnitude in **cells: one cell = 256 leptons**. Sub-cell values are
   invisible in practice — they only break exact ties, and two objects rarely
   share a lepton-exact position. `-256` biases by one cell. A very large value
   sorts the object behind things many cells away, which looks as wrong as
   being on top.
4. If the object is paused or otherwise never advances, also re-set
   `ObjectClass +0x80` (`NeedsRedraw`) each frame — `ObjectClass::DrawIfVisible`
   (`0x5F4B10`) clears it after use, so a frozen anim is drawn exactly once.

### Anti-pattern

Tuning `YSortAdjust` to find a working value **before** confirming the object is
in `Ground`. Every value behaves identically (i.e. does nothing) outside layer 2,
so the experiment cannot distinguish "wrong magnitude", "wrong sign" and "field
not read". Establish the layer first; then a magnitude change must produce a
visible change, and that is itself the check that the layer is right.

---

## Provenance

`objdump -d` of vanilla `gamemd-spawn.exe`: `0x4A9720`, `0x5519B0`, `0x551A90`,
`0x551A30`, `0x55DBC8`, `0x5F6220`, `0x5F6BD0`, `0x422BC0`, `0x424CB0`,
`0x427530`. `AnimClass` vtable at `0x7E3354`; slot `+0x78` (`InWhichLayer`)
resolves to `0x424CB0`. Layer enum values cross-checked against YRpp
`GeneralDefinitions.h`.

Found while building IntelExt's infantry-corpse decals, after four builds spent
tuning a sort bias that was never being read.

## Related

* [Fog-Of-War-Dormant-Layer](Fog-Of-War-Dormant-Layer.md) — `DrawIfVisible` and
  the per-cell draw gate.
* [Logic-Frame-Update](Logic-Frame-Update.md) — where the once-per-frame
  `LayerClass::Sort` call sits.
