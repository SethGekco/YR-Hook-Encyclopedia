# SHP image access — reading a shape frame's pixels

How to pull the raw pixels of an `SHPStruct` frame and draw it yourself (custom
previews, silhouettes, UI). YRpp only forward-declares `SHPStruct`, so these
engine methods are usually called through their addresses.

Source: **Enthalpy v1.0.3** (`CCrispS/Enthalpy`, GPLv3), which draws a
translucent unit silhouette as a formation preview. `src/ShpGhost.cpp` maps the
four methods it needs; all are `__thiscall` on the `SHPStruct*`.

| Address | Signature (`__thiscall`, `self` = `SHPStruct*`) | Role |
|---|---|---|
| `0x69E090` | `void Load(self)` | Fault in / decode the shape's frame data so the other calls are valid. |
| `0x69E740` | `BYTE* GetPixels(self, int frame)` | Pointer to the frame's 8-bit palette-index pixels. |
| `0x69E7E0` | `void* GetFrameBounds(self, void* pBuffer, int frame)` | Fills `pBuffer` with the frame's bounds (offset + extent). |
| `0x69E900` | `bool HasCompression(self, int frame)` | True when the frame is **RLE-compressed**. |

**Composition** (draw one frame): `Load` once → `HasCompression(frame)` to gate →
`GetFrameBounds(&buf, frame)` for placement/extent → `GetPixels(frame)` for the
index bytes → blit against a palette.

⚠ **The compression gate is the trap.** `GetPixels` returns the *stored* bytes.
When `HasCompression(frame)` is true the frame is RLE, so those bytes are **not**
a flat readable bitmap — walking them as `width*height` indices draws garbage.
Enthalpy's `IsReadable` is exactly `!HasCompression`: it only draws frames it can
read pixel-by-pixel and skips the rest rather than decode RLE by hand. If you
need every frame, decompress first; don't assume `GetPixels` is always flat.

⚠ **Only the first few `SHPStruct` header fields are stable to read directly** —
Enthalpy notes the header's first fields (frame count, width, height) are shared
between the stored and cached-reference forms, and reads only those.

**Voxels go a different way.** Enthalpy draws voxel units via the engine's own
`DrawAsVXL` rather than this SHP path — there is no equivalent "give me the
pixels" for a voxel; you ask the engine to render it.

**Confirmed via.** Enthalpy v1.0.3 source (`src/ShpGhost.cpp`, `src/ShpGhost.h`)
and its startup `VerifyGameBuild` byte-check of these sites (it validates the
hook sites, not these call targets, so treat the addresses as Enthalpy's reading
of `gamemd.exe` 1.001). Signatures are the `using` typedefs in `ShpGhost.cpp`.
Not independently disassembled here.

## Related
* [Render-Layers-YSort](Render-Layers-YSort.md) — where in `TacticalClass::Render`
  a custom draw like this can be injected, and the layerless-map trap.
* [Remap-Colour-Palette](Remap-Colour-Palette.md) — turning 8-bit indices into
  colour.
