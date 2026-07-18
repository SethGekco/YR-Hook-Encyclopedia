# Sources & provenance

Every fact in this encyclopedia should be traceable to one of these. When you
add a Tier 2 entry, cite which source(s) you confirmed it against.

## Frameworks in the registry

### Ares
- **In registry via:** the pre-extracted dump `sources/raw/All-Hooks-Phobos-Antares.csv`
  (column `Framework = Antares`, normalised to `Ares` in the registry).
- **Upstream source for prose:** Ares is open-source (`Ares-Developers/Ares` on
  GitHub). Use it to confirm what a hook does when writing Tier 2 entries.
- **Note:** Ares is closed to new stolen-address work but remains the reference
  for a huge body of vanilla-behaviour extensions.

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
- **Notes:** Kratos is a Chinese-community Syringe extension. Source comments are
  frequently in Chinese; they are worth reading — they often state a hook's
  intent (and its interaction with Phobos) directly. Kratos deliberately
  co-hooks several Phobos addresses to override or skip Phobos behaviour; those
  show up in `registry/conflicts.md`.

## Data conventions

- **Address** — the primary key. Normalised to `0x`-prefixed uppercase.
- **Stolen bytes** — how many bytes the hook overwrites at the address. Stored as
  hex (`0x5`, `0x0A`). All upstream sources express this in hex; the original
  Ares/Phobos CSV dropped the `0x` prefix but the values are still hex.
- **Subsystem** — a coarse category (`Ext/Techno`, `Misc`, …) mirroring the
  framework's own source layout. Advisory grouping only, not authoritative.
- **Source file** — the framework source file the hook is defined in, for
  cross-reference back to upstream.

## Not yet included (future tiers)

- **Vanilla reverse-engineered hooks** — addresses discovered by RE'ing
  `gamemd.exe` directly (Ghidra/objdump), described by engine function name.
- **Syringe core** — the loader/bootstrap hooks every DLL depends on.
- **CnCNet spawner** and other community frameworks.
