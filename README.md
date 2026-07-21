# YR Hook Encyclopedia

A complete, local, framework-neutral reference for the executable hooks used to
extend **Red Alert 2: Yuri's Revenge** (`gamemd.exe`). It answers, for every
known hook:

- **What it does** — the behaviour it actually changes.
- **What it does *not* do** — the things people reasonably but wrongly assume it
  covers. This is the part every other hook list omits, and it's where the
  hours get lost.
- **Who uses it** — which public frameworks (Antares, Phobos, Kratos, Ares, …)
  patch this address, and how their versions relate.

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
  hooks.csv               One row per (address, framework, channel) consumer.
  hooks.json              Address-keyed. Each address lists every consumer.
  conflicts.md            Auto: addresses hooked by 2+ CO-LOADABLE frameworks (release).
  pr-hooks.md             Auto: loose hooks from unmerged PRs, grouped by framework/PR.
  tags.csv                Auto: framework INI tags -> where parsed + candidate-hook count.
  tag-hooks.md / .json    Auto: framework tag -> candidate hooks (HEURISTIC, see below).
  vanilla-tags.md/.json/.csv  Auto: vanilla (rules) tag -> candidate read site in gamemd.exe.
  engine-string-surface.*  Auto: EVERY string the engine reads (rules/art/ai/…) + read sites.
  PROVENANCE.md           Auto: exact upstream commit each framework was read from.
  STATS.md                Auto: counts.
encyclopedia/             TIER 2 — curated prose entries, one page per subsystem.
  README.md               Index + the entry workflow.
  _TEMPLATE.md            The entry format (does / does-not / used-by).
  Ext-Aircraft.md         ... one page per subsystem, filled in over time.
scripts/
  update_repos.sh         Clone/update the upstream framework repos (release source).
  fetch_pr_hooks.py       Sweep open PRs for loose hooks -> sources/pr_hooks.json.
  build_registry.py       Regenerate the hook registry under registry/ from the sources.
  build_tag_index.py      Regenerate the framework tag->hook cross-reference (needs hooks.json).
  build_vanilla_tag_candidates.py  Regenerate vanilla (rules) tag->read-site index (needs gamemd.exe).
  build_engine_string_surface.py   Regenerate the full engine string surface (all INIs; needs gamemd.exe).
  fetch_modenc.py         Pull ModEnc wiki flag facts for tags -> sources/modenc-cache.json (needs network).
sources/
  repos/                  Cloned upstream repos (gitignored; reproducible).
  pr_hooks.json           Extracted loose-PR hooks (input to the builder).
  modenc-cache.json       ModEnc-derived tag facts (committed; small wiki metadata + source URLs).
  raw/                    Legacy pre-extracted dumps (e.g. the old Antares+Phobos CSV).
```

### Channels

Each hook consumer is tagged with a **channel**:
- **`release`** — the hook is in the framework's mainline source (a real shipped hook).
- **`PR#NNNN`** — the hook exists *only* in an unmerged pull request: a "loose"
  or proposed hook that may change address, be rewritten, or never merge.

### Conflicts vs. inherited overlap

A shared address is only a **real conflict** when the frameworks involved can be
**loaded at the same time**. Ares and Antares are mutually exclusive (Antares
*continues* Ares; you run one or the other), so an address they both hook is
inherited code, not a conflict — the builder separates those out and keeps
`conflicts.md` to genuine, co-loadable collisions.

## Two tiers, on purpose

**Tier 1 — the Registry** is complete *now*. Every known hook from every covered
framework is in it, keyed by address, with function name, stolen-byte count,
subsystem, and source file. It is generated mechanically, so it is cheap to keep
current and never goes stale silently. Regenerate it any time with:

```
scripts/update_repos.sh          # refresh upstream framework clones (release hooks)
python3 scripts/fetch_pr_hooks.py   # (optional, slow) refresh loose PR hooks
python3 scripts/build_registry.py   # rebuild the hook registry from both
python3 scripts/build_tag_index.py  # rebuild the tag->hook cross-reference
scripts/update_ini_cache.sh         # refresh the vanilla YR/RA2/TS INI cache
python3 scripts/fetch_modenc.py     # (optional, slow, network) ModEnc tag facts -> cache
python3 scripts/build_engine_string_surface.py  # rebuild the engine string surface
```

## Finding what a hook does (the tag → hook index)

Two ways to go from "I want behaviour X" to "which hook is it":

- **Framework tags → hooks** (`registry/tags.csv`, `tag-hooks.md/.json`, built by
  `build_tag_index.py`). For every INI tag a framework *adds*, this lists where
  the tag is parsed and a **shortlist of candidate hooks** likely to implement it.
  It's built from source structure, so it's a **triage shortlist, not proof** —
  every link is labelled `member-referenced` (the parsed field's name appears in
  the hook's file — fairly strong), `same-subsystem` (a wider net), or `broad`
  (a big net, treat with care). The narrowing is the value: a shortlist of 6 — or
  even 60 — beats reading 1,700 hooks blind. ⚠ **Treat all of it as unverified**
  until you confirm against the source or in-game.
- **Vanilla tags → read sites** (`registry/vanilla-tags.csv`, `.md`, `.json`,
  built by `build_vanilla_tag_candidates.py`). Original game tags aren't in any
  source — but the engine reads a tag by pushing its string address as a call
  argument (`push offset "Tag"` = `68 <VA>` on x86). The builder finds each tag's
  string in `gamemd.exe` and scans `.text` for that push, giving the **exact code
  address(es) where the tag is read** — a candidate hook site. ~91% of vanilla
  tags resolve this way (no Ghidra needed). It also flags when a read site sits
  within `0x400` of an already-registered framework hook, linking vanilla tags
  back to documented hooks. ⚠ Still **unverified**: a read site is where the tag
  is *parsed*, which anchors you near the behaviour but isn't proof of it.
- **The whole engine surface** (`registry/engine-string-surface.*`, built by
  `build_engine_string_surface.py`). The reverse of the above: instead of looking
  up known tags, it enumerates **every identifier string the engine pushes** and
  classifies each into one of five kinds:
  - `tag` — a key (or fixed list-section like `[TaskForces]`/`[Waypoints]`) in an
    INI we checked; carries a domain. **1,919**.
  - `tag-unlisted` — a CamelCase engine-key shape the binary reads but that appears
    in **no** INI we have: real engine tags vanilla content never sets (rare or
    defaulted rules/art keys — `ActiveAnimTwoX`, `ShowOccupantPips`, `CustomRotor`,
    `AIUseTurbineUpgradeProbability`). The richest lead-list of *undocumented* tags.
    **514**. Each is then **domain-sourced from multiple independent methods, every
    claim tagged with how it was obtained** — and we **don't pick a favourite**:
    competing documented claims are shown side by side until someone verifies a tag
    experimentally, so readers can weigh them and reconcile conflicting findings.
    The methods:
    - `modenc` — parsed from the [ModEnc](https://modenc.renegadeprojects.com) wiki's
      `{{flag}}` template via `scripts/fetch_modenc.py` (cached with the source URL).
      **177** get a documented INI; another **117** have a ModEnc page with type info
      but no file; **203** have no page.
    - `readsite-consensus` — inferred from the binary: known tags whose read sites
      cluster within ±128 bytes of the unlisted tag's read site and **unanimously**
      agree on a domain (else it abstains). ~100% leave-one-out precision, but with
      real misses where art/rules loaders interleave. **26** are sourced this way.
    - `framework-source` — the literal appears in a framework's C++ (corroboration
      it's a real tag, and *who* reads it): **25**.

    Net **203/514** carry at least one domain claim. Where two methods **disagree**
    (3 cases, e.g. `CustomRotor`: read-site says `rules`, ModEnc says `art`), both
    claims are shown side by side and the row is marked ⚠ in a `≟` column — a flag
    for someone to test, **not** a ruling for either source. See the "provenance,
    not verdicts" table and the disagreements list in `engine-string-surface.md`.
  - `file` (319, filenames/resources), `code` (146, RTTI/abstract types, UI ids,
    value literals, function/debug strings — not tags), and `unclassified`
    (ambiguous residual — now **0**).

  Strings are classed against the **full vanilla YR INI set** (30 files: rules,
  art, ai, sound, eva, theme, ui, rmg, the theater tile-control files, the MP
  game-mode files, mission/mapsel/battle/coop), **sample map/scenario files**
  (`.map`/`.mpr`/`.yrm`/`.mmx` — the `map` domain: `HomeCell`, `NextScenario`,
  `IceGrowthEnabled`, the lighting `Ion*` keys), the **original Red Alert 2 INIs**
  (`ra2` domain), and the **Tiberian Sun INIs**, split into base TS (`ts`, v1.x)
  and the **Firestorm expansion** (`tsfs`, v2.00 — the FS-suffixed / numbered
  overlay INIs). Fixed list-*section* names (`[TaskForces]`/`[ScriptTypes]` in AI
  INIs, `[CellTags]`/`[Waypoints]` in maps) are indexed too — but only for AI / map
  / mission files, never rules/art (whose sections are object IDs the engine never
  pushes as literals).
  - **Engine-lineage legacy tags.** YR runs on the RA2 engine, which runs on the
    Tiberian Sun engine (base game + Firestorm). When a feature was cut, its
    *tag-reading code often stayed in the binary*. Classifying against RA2, base TS
    and Firestorm INIs surfaces these — a string `gamemd.exe` reads that survives
    only in an older generation is a vestigial tag:
    - `ts`-only (~53): tags in base Tiberian Sun's `RULES.INI` etc. that YR still
      reads — `HunterSeeker`, `FirestormWall`/`LaserFence`/`LaserFencePost`,
      `EMPulseCannon`, `IsPlug`/`IsTemple` (Ion-Cannon component towers),
      `ICBMLauncher`, `Dig`/`AtmosphereEntry` (subterranean).
    - `tsfs`-only (~17): keys that live *only* in the Firestorm overlay INIs
      (`ARTFS`/`AIFS`/`FIRESTRM`/`BATTLEFS`) — Firestorm's art/animation-system
      additions: `VoxelBarrelFile`/`VoxelBarrelOffsetTo…`, `DeathFrames`/
      `StartWalkFrame`/`StartStandFrame`, `EngineerCaptureLevel`.
      (Note: `ts` vs `tsfs` reflects *which INI file the key sits in*, not which
      game introduced the feature — this community mirror ships base `RULES.INI`
      as the complete merged rules, so Firestorm-era **unit** tags resolve to `ts`.)
    - `ra2`+`ts`: TS features that also passed through RA2 — `VeinAttack`
      (Veinhole, `0x6692ff`), `AIIonCannon*Value` (`0x670a55`+),
      `BuildAA`/`BuildDefense`/`BuildHelipad`/`BuildPDefense`, `Armory`/`Hospital`.
    - `ra2`-only: RA2 additions YR dropped — `CampaignPlayer`/`CampaignEnemy`
      (YR switched to numbered `…1` forms).
  - Vanilla INIs are read from a gitignored cache (`sources/ini-cache/`, refreshed
    by `scripts/update_ini_cache.sh` — the YR/RA2 zips plus the TS INI repo) so the
    build is reproducible; only the derived string→domain→address data is committed.

**Tier 2 — the Encyclopedia** is the slow, valuable part: hand-written prose for
hooks that are widely used, widely *misunderstood*, or conflict-prone. It grows
one subsystem at a time and is never expected to be "finished." An address
having no Tier 2 entry yet just means nobody has written it up — the Tier 1 row
still tells you it exists and who hooks it.

## Coverage

| Framework | Release | PRs | Source |
|---|---|---|---|
| Ares (classic) | ✅ | n/a (0 open) | cloned `Ares-Developers/Ares` (frozen at last-open, 2016) |
| Antares | ✅ | n/a (0 open) | cloned `Phobos-developers/Antares` |
| Phobos  | ✅ | ✅ open PRs | cloned `Phobos-developers/Phobos` |
| Kratos  | ✅ | ✅ open PRs | cloned `ra2diy/KratosPP` |
| AggressiveStance | ✅ | n/a (0 open) | cloned `Aephiex/YRAggressiveStance` — small standalone Syringe DLL |
| CnCRAZER/Ares fork | ⏳ | ✅ open PRs | fork of Ares; PR-only for now |
| Vanilla-RE'd, Syringe core, CnCNet spawner, other | ⏳ | ⏳ | future tiers |

> **Antares ≠ Ares.** Antares is a Phobos-developers open-source *reimplementation*
> of newer, closed Ares — and is deliberately incompatible with Ares itself.
> The registry's `Antares` rows are Antares, not classic Ares. Classic Ares is a
> separate framework still to be added. Don't conflate them.

## Scope & neutrality

This is a **general, public** reference. It is framed around the vanilla engine
functions and the public frameworks only. It does **not** catalogue anyone's
private or personal mods. A specific mod or private DLL is named **only** when it
is the sole known consumer of an otherwise-undocumented hook — and never as the
organising frame for a page. If you find a private project referenced as a
page's subject rather than as an incidental consumer, that's a bug to fix. 
This is not affiliated with any listed project under Coverage and is not intended
to steal anyone's work; it's goal is simply to provide a middleman for vibecoders
to not unintentionally conflict with an existing project as well help save tokens
looking for the correct, known, hooks for everything. This project has both 
confirmed and speculated hooks listed, as information evolves this library will
hopefully evolve with it. 

## How to add knowledge

- **New/updated framework data** → update the relevant source in `sources/raw/`
  or the extractor in `scripts/build_registry.py`, then re-run the builder.
- **New prose** → copy `encyclopedia/_TEMPLATE.md` into the right subsystem page
  and fill it in. Verify claims against real source or reverse-engineering, and
  say how you confirmed each fact. "Unverified" is a legitimate, honest status —
  a guess presented as fact is not.
