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

## How data enters the registry

**Release-channel hooks** are extracted *directly from cloned upstream repos* by
`scripts/build_registry.py` (parsing `DEFINE_HOOK` / `DEFINE_HOOK_AGAIN`). Clone
or refresh them with `scripts/update_repos.sh`. The exact commit each framework
was read from is recorded in `registry/PROVENANCE.md` every build. This replaced
the earlier approach of trusting a pre-made CSV, and removes all version-drift
guesswork — the source is the source.

**Loose (PR-channel) hooks** are swept from open pull requests by
`scripts/fetch_pr_hooks.py` into `sources/pr_hooks.json`, then merged by the
builder. See `registry/pr-hooks.md`.

**Mutually-exclusive frameworks:** the builder knows Ares and Antares are never
loaded together (Antares continues Ares; `Ares.dll` must be removed to run
Antares). Addresses only shared *between* Ares and Antares are inherited code,
not conflicts, and are excluded from `conflicts.md` (counted separately in
`STATS.md`).

### Ares (classic)
- **In registry via:** cloned `Ares-Developers/Ares`. It is **frozen at its
  last open-source commit (2016)** — everything past v0.A is closed. So the Ares
  rows represent last-open Ares, not any modern closed build.
- **Dialect:** bare-hex address and size, e.g. `DEFINE_HOOK(47AE36, Name, 8)`.

### Antares
- **In registry via:** cloned `Phobos-developers/Antares`.
- **Note:** Antares continues Ares from its last-open state, so most of its hooks
  are byte-identical to Ares's — expect near-complete Ares↔Antares address
  overlap (inherited, not a conflict). Confirm any *new* Antares behaviour
  against the Antares repo, not an Ares assumption.
- **Dialect:** bare-hex, same as Ares.

### Phobos
- **In registry via:** cloned `Phobos-developers/Phobos` (current `master`). The
  old CSV-vs-local-checkout version caveat no longer applies — the builder reads
  live upstream source, recorded in `PROVENANCE.md`.
- **Dialect:** `0x`-prefixed address and size, e.g. `DEFINE_HOOK(0x..., Name, 0x6)`.
- **PRs:** Phobos has the most open PRs by far — the primary source of loose hooks.

### Kratos (KratosPP)
- **In registry via:** cloned `ra2diy/KratosPP` (the local `/home/rex/KratosPP_meep`
  is a checkout of the same project; the registry uses the fresh clone).
- **Notes:** Chinese-community Syringe extension; source comments are frequently
  in Chinese and often state a hook's intent (and its Phobos interaction)
  directly. Kratos deliberately co-hooks several Phobos addresses to override or
  skip Phobos behaviour; those appear in `registry/conflicts.md`.
- **Dialect:** `0x`-prefixed, same as Phobos.

### CnCRAZER/Ares (fork)
- A fork of classic Ares with open PRs. Currently included at the **PR channel
  only** (its open PRs are swept). Its release divergence from classic Ares is
  not yet extracted separately — a future task if the fork proves to differ
  meaningfully.

## Data conventions

- **Address** — the primary key. Normalised to `0x`-prefixed uppercase.
- **Channel** — `release` (in mainline source) or `PR#NNNN` (only in an open PR).
- **Framework dialects** — Ares/Antares write the address and stolen-byte count
  as bare hex (`DEFINE_HOOK(47AE36, Name, 8)`); Phobos/Kratos prefix `0x`
  (`DEFINE_HOOK(0x..., Name, 0x8)`). The builder parses both as hex.
- **Stolen bytes** — how many bytes the hook overwrites at the address. Stored as
  hex (`0x5`, `0x0A`).
- **Subsystem** — a coarse category (`Ext/Techno`, `Misc`, …) derived from the
  hook's source-file directory. Advisory grouping only, not authoritative.
- **Source file** — the framework source file (repo-relative) the hook is defined
  in, for cross-reference back to upstream.

## Not yet included (future tiers)

- **Vanilla reverse-engineered hooks** — addresses discovered by RE'ing
  `gamemd.exe` directly (Ghidra/objdump), described by engine function name.
- **Syringe core** — the loader/bootstrap hooks every DLL depends on.
- **CnCNet spawner** and other community frameworks.
