# Art Redirection (`Image=`) and Cameo Resolution

Not a hook page — this documents engine *data* semantics that repeatedly produce
"the unit is invisible and I don't know why". Recorded here because nothing else
covered it.

## `Image=` names an ART SECTION, never a unit ID

`Image=` in `rulesmd.ini` selects which **artmd.ini section** a type draws from.
It is *not* "copy that unit's appearance". The distinction bites because many
vanilla units redirect their own art, so their **ID is not a valid art section**:

| Unit (rules ID) | Its own `Image=` | Art section actually used |
|---|---|---|
| `MTNK` Grizzly | `Image=GTNK` | `[GTNK]` |
| `APOC` Apocalypse | `Image=MTNK` | `[MTNK]` |
| `MGTK` Mirage Tank | `Image=RTNK` | `[RTNK]` |
| `SREF` Prism Tank | *(none)* | `[SREF]` |

So the art named `[MTNK]` is the **Apocalypse**, and the Grizzly's art is
`[GTNK]`. Setting `Image=MGTK` or `Image=APOC` points at a section that does not
exist: the object renders as **nothing**, and its cameo comes out blank, with no
error anywhere. Verified in game (YR 1.001 + Antares + Phobos) — `Image=MGTK`
and `Image=APOC` both produced invisible vehicles, while `Image=SREF`,
`Image=HTNK`, `Image=TNKD` and `Image=FV` all rendered correctly.

**Practical rule:** resolve the intended unit's own `Image=` first and use the
result. A tool doing this programmatically should follow the chain (bounded — a
cycle is possible) rather than trusting the ID.

## A cycle renders nothing

`[A] Image=B` together with `[B] Image=A` cannot be resolved: the affected object
is invisible and shows an unrelated cameo. Easy to create when two types are
redirected independently.

## Cameo follows `ImageFile`

The cameo is read from the art section that `ImageFile` names, not from the
type's own section — see Antares `src/Ext/TechnoType/Body.cpp`:
`CameoPCX.Read(&CCINIClass::INI_Art, pThis->ImageFile, "CameoPCX")`. Consequences:

* Any `Image=` redirect **also replaces the cameo**, whether or not that was
  intended.
* Since the art *file* is determined by the section name, there is no data-only
  way to keep one unit's art and another's cameo. Restoring the original cameo
  requires reassigning `TechnoTypeClass::CameoFile` + `Cameo` after types load
  (`FileSystem::LoadSHPFile`); `0x679CAF` (`LoadAfterTypeData` epilogue, 5-byte
  boundary) is a workable point.

## Art is not interchangeable across unit classes

A section existing is necessary but not sufficient — the art has to match what
the unit's rendering expects:

* **Gunner units (the IFV, `FV`)** pick turret art per passenger and their art
  section defines `Weapon1FLH … Weapon10FLH`. Given art that only defines
  `PrimaryFireFLH` (e.g. `[MTNK]`, the Apocalypse), the IFV rendered as nothing;
  given `[SREF]`, which defines `Weapon1FLH`, it rendered correctly.
* Plain turreted tanks (`PrimaryFireFLH`) interchange freely in testing
  (`HTNK` / `TNKD` / `GTNK` / `LTNK`).

**Unverified:** whether the `WeaponNFLH` set is the actual gating factor or
merely correlates with it; only the two IFV cases above were observed. Treat
"art swaps are safe within a unit class, suspect across classes" as the working
rule until someone tests more pairs.

## Gotcha for tooling

`artmd.ini` section headers carry trailing comments (`[MTNK]   ; Apocalypse
tank`) and CRLF line endings, so `grep '^\[MTNK\]$'` reports the section missing.
Match the header prefix, not the whole line.
