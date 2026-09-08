# Subsystem: Kill registration & bounty payouts

What happens inside `TechnoClass::RegisterDestruction` — the single funnel
every framework uses for "X killed Y" logic (bounty, veterancy, kill triggers,
killer bookkeeping) — and how the mainline frameworks share it. Addresses for
standard YR `gamemd.exe`, imagebase `0x400000`.

**Provenance:** hook rows cross-checked against `registry/hooks.csv` and the
Antares PDB name list (`gamemd_names_from_antares_pdb.txt`); register facts
read from Antares release source (`src/Ext/Techno/Hooks.Bounty.cpp`), not
independently disassembled. Items marked RE-VERIFY have not been confirmed
against a live disassembly.

## The hook cluster, in address order

| Address | Size | Owner(s) | Purpose |
|---|---|---|---|
| `0x702D6D` | 0x6 | Phobos PR#1172 | SaveKillerInfo (early site) |
| `0x702DD6` | 0x6 | Antares | Kill trigger events (TEvent) |
| `0x702E4E` | 0x6 | Phobos release | SaveKillerInfo |
| `0x702E64` | 0x6 | Antares | **Bounty payout** |
| `0x702E6A` | 0x7 | Phobos **PR#2118** (open) | "New bounty logic" |
| `0x702E9D` | 0x6 | Antares + Ares + Kratos | Veterancy / general kill hook |

House-level sibling: `HouseClass::RegisterDestruction` is hooked at
`0x70337D` (Phobos SaveKillerInfo). Unit-level trigger variant:
`0x744745` UnitClass_RegisterDestruction_Trigger (PDB name, unhooked in
registry).

## Register conventions at 0x702E64 (from Antares source)

- `EDI` = killer `TechnoClass*` (may be checked non-null)
- `ESI` = victim `TechnoClass*`

Antares' handler: if killer's TechnoTypeExt `Bounty` flag is set, calls
`TechnoExt(victim)->CalculateBounty(killer)` and **returns 0** — so a same-
address co-hook placed after it in the Syringe chain still runs (see
`Syringe-Stub-Semantics.md`: a non-zero return would stop the chain).

Antares payout gating (order): killer==victim house → no pay; allied victim →
no pay; victim HouseTypeExt `GivesBounty=no` → no pay; rules `BountyEnablers=`
building list non-empty and killer owns none → no pay; then pays victim's
`Bounty.Value` (Promotable, rank-resolved).

## Adjacency & co-existence notes

- `0x702E64` (size 0x6) ends at `0x702E6A` — exactly where Phobos PR#2118
  begins (size 0x7). **Adjacent, not overlapping**; both may be safely loaded
  by the overlap rules, but then *two* bounty systems run on every kill.
  PR#2118 auto-disables Ares' bounty, not Antares'.
- `0x702E9D` is triple-owned (Antares, Ares, Kratos) — same address, same
  size, all chain.
- Any new kill-tracking DLL should co-hook one of the existing addresses at
  the **same size** rather than picking a fresh nearby address (overlap risk
  with the six sites above is high in this 0x150-byte window).

## RE-VERIFY

- [ ] Function entry address of `TechnoClass::RegisterDestruction` (PDB list
      names only interior sites; entry not recorded here)
- [ ] Whether `EDI`/`ESI` still hold killer/victim at `0x702E9D` (Kratos and
      Ares both hook it; their sources imply yes, unconfirmed)
- [ ] Victim death coordinates availability at these sites (needed for
      range-based "kill leech" logic; victim object is still live here?)
