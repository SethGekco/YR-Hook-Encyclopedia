# Sources & provenance

Every fact in this encyclopedia should be traceable to one of these. When you
add a Tier 2 entry, cite which source(s) you confirmed it against.

## Canonical upstream repositories

| Repo | What it is |
|---|---|
| https://github.com/Phobos-developers/Phobos | **Phobos** — active open-source YR extension. |
| https://github.com/Phobos-developers/Antares | **Antares** — open-source *reimplementation* of newer, closed Ares, by the Phobos-developers community. A **distinct framework**, not Ares. |
| https://github.com/ra2diy/KratosPP | **KratosPP (Kratos)** — Chinese-community Syringe extension. Upstream of the local `/home/rex/KratosPP_meep` checkout. |
| https://github.com/Ares-Developers/Ares | **Ares (classic)** — the original Ares. Open only through **v0.A**; everything past that is closed-source (which is *why* Antares exists). |
| https://github.com/Ares-Developers/Ares-release | Ares **packaging** repo (readme, `ares.mix`, license) — **not source, not binaries**. For assembling release packages only. |
| https://github.com/CnCRAZER/Ares | A **fork** of `Ares-Developers/Ares`. Track separately if/when its divergences matter. |

### ⚠ Antares is not Ares — do not conflate
Antares reverses and reimplements Ares functionality that went closed after v0.A.
It is **intentionally incompatible** with Ares (you must remove `Ares.dll` to run
Antares). So a hook present in Antares is not proof classic Ares hooks the same
address, and vice-versa. When classic Ares is eventually added as its own source,
it gets its own `Framework` label — `Antares` and `Ares` stay separate columns.

## Frameworks in the registry

### Antares
- **In registry via:** the pre-extracted dump `sources/raw/All-Hooks-Phobos-Antares.csv`
  (column `Framework = Antares`, kept as-is).
- **Upstream source for prose:** `Phobos-developers/Antares` (see table above).
- **Note:** because Antares reimplements Ares behaviour, its function/hook names
  often mirror classic Ares — useful for cross-referencing, but confirm against
  the Antares repo, not an Ares assumption.

### Phobos
- **In registry via:** the same CSV (`Framework = Phobos`).
- **Upstream source for prose:** `Phobos-developers/Phobos` on GitHub.
- **⚠ Version caveat:** the CSV was extracted from a *newer* Phobos than the
  local checkout at
  `…/000-RA2YR Data - cncnet edition - BASED ON WP/src`. That local tree is an
  older build and is **missing hooks the CSV contains** (e.g. the aircraft
  shadow hook at `0x4147F9`). Treat the CSV as authoritative for *which* hooks
  Phobos has, and confirm behaviour against upstream Phobos at a matching
  version — not blindly against that local checkout.

### Kratos (KratosPP)
- **In registry via:** live extraction from `/home/rex/KratosPP_meep/src` by
  `scripts/build_registry.py`, parsing `DEFINE_HOOK` / `DEFINE_HOOK_AGAIN`.
- **Upstream:** `ra2diy/KratosPP` (the local `KratosPP_meep` is a checkout of it).
- **Notes:** Kratos is a Chinese-community Syringe extension. Source comments are
  frequently in Chinese; they are worth reading — they often state a hook's
  intent (and its interaction with Phobos) directly. Kratos deliberately
  co-hooks several Phobos addresses to override or skip Phobos behaviour; those
  show up in `registry/conflicts.md`.

## Data conventions

- **Address** — the primary key. Normalised to `0x`-prefixed uppercase.
- **Stolen bytes** — how many bytes the hook overwrites at the address. Stored as
  hex (`0x5`, `0x0A`). All upstream sources express this in hex; the original
  Antares/Phobos CSV dropped the `0x` prefix but the values are still hex.
- **Subsystem** — a coarse category (`Ext/Techno`, `Misc`, …) mirroring the
  framework's own source layout. Advisory grouping only, not authoritative.
- **Source file** — the framework source file the hook is defined in, for
  cross-reference back to upstream.

## Not yet included (future tiers)

- **Ares (classic)** — its own framework, separate from Antares. Open source
  only through v0.A (`Ares-Developers/Ares`); later versions are closed. When
  added, it gets its own `Framework = Ares` label. The `CnCRAZER/Ares` fork
  would be tracked as a variant of this, not of Antares.
- **Vanilla reverse-engineered hooks** — addresses discovered by RE'ing
  `gamemd.exe` directly (Ghidra/objdump), described by engine function name.
- **Syringe core** — the loader/bootstrap hooks every DLL depends on.
- **CnCNet spawner** and other community frameworks.
