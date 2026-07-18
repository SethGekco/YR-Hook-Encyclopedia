# YR Hook Encyclopedia

A complete, local, framework-neutral reference for the executable hooks used to
extend **Red Alert 2: Yuri's Revenge** (`gamemd.exe`). It answers, for every
known hook:

- **What it does** — the behaviour it actually changes.
- **What it does *not* do** — the things people reasonably but wrongly assume it
  covers. This is the part every other hook list omits, and it's where the
  hours get lost.
- **Who uses it** — which public frameworks (Ares, Phobos, Kratos, …) patch this
  address, and how their versions relate.

## The one idea that organises everything

**A hook's identity is its address in `gamemd.exe`.** Names differ between
frameworks; the address does not. Keying on the address is what makes the single
most useful fact fall out for free: **when two frameworks hook the same address,
that is a compatibility concern.** The registry surfaces every such collision
automatically (see `registry/conflicts.md`).

## Layout

```
README.md                 You are here.
sources.md                Provenance: where each framework's data comes from.
registry/                 TIER 1 — the complete, mechanical index (all known hooks).
  hooks.csv               One row per (address, framework) consumer. Sorted by address.
  hooks.json              Address-keyed. Each address lists every framework hooking it.
  conflicts.md            Auto-generated: addresses hooked by 2+ frameworks.
  STATS.md                Auto-generated counts.
encyclopedia/             TIER 2 — curated prose entries, one page per subsystem.
  README.md               Index + the entry workflow.
  _TEMPLATE.md            The entry format (does / does-not / used-by).
  Ext-Aircraft.md         ... one page per subsystem, filled in over time.
scripts/
  build_registry.py       Regenerates everything under registry/ from the sources.
sources/raw/              Unmodified upstream dumps (e.g. the Ares+Phobos CSV).
```

## Two tiers, on purpose

**Tier 1 — the Registry** is complete *now*. Every known hook from every covered
framework is in it, keyed by address, with function name, stolen-byte count,
subsystem, and source file. It is generated mechanically, so it is cheap to keep
current and never goes stale silently. Regenerate it any time with:

```
python3 scripts/build_registry.py
```

**Tier 2 — the Encyclopedia** is the slow, valuable part: hand-written prose for
hooks that are widely used, widely *misunderstood*, or conflict-prone. It grows
one subsystem at a time and is never expected to be "finished." An address
having no Tier 2 entry yet just means nobody has written it up — the Tier 1 row
still tells you it exists and who hooks it.

## Coverage

| Framework | Status | Source |
|---|---|---|
| Ares    | ✅ in registry | pre-extracted CSV (see `sources.md`) |
| Phobos  | ✅ in registry | pre-extracted CSV (see `sources.md`) |
| Kratos  | ✅ in registry | extracted live from source |
| Vanilla-RE'd, Syringe core, CnCNet spawner, other | ⏳ not yet | future tiers |

## Scope & neutrality

This is a **general, public** reference. It is framed around the vanilla engine
functions and the public frameworks only. It does **not** catalogue anyone's
private or personal mods. A specific mod or private DLL is named **only** when it
is the sole known consumer of an otherwise-undocumented hook — and never as the
organising frame for a page. If you find a private project referenced as a
page's subject rather than as an incidental consumer, that's a bug to fix.

## How to add knowledge

- **New/updated framework data** → update the relevant source in `sources/raw/`
  or the extractor in `scripts/build_registry.py`, then re-run the builder.
- **New prose** → copy `encyclopedia/_TEMPLATE.md` into the right subsystem page
  and fill it in. Verify claims against real source or reverse-engineering, and
  say how you confirmed each fact. "Unverified" is a legitimate, honest status —
  a guess presented as fact is not.
