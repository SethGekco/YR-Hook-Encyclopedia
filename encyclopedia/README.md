# Encyclopedia (Tier 2)

Curated, hand-written prose entries. One markdown page per subsystem; one entry
per hook address, sorted by address within the page. Use `_TEMPLATE.md` for each
new entry.

This tier is deliberately incomplete and always will be. The goal is not to
write up all ~2,900 addresses — it's to cover the hooks that are **widely used,
widely misunderstood, or conflict-prone**, so the reference earns its keep.

## Priority order for what to write up next

1. **Shared addresses** (`registry/conflicts.md`) — 300 addresses where two or
   more frameworks collide. These are where compatibility bugs actually live and
   where a written explanation saves the most time. The 79 hooked by *all three*
   frameworks are the top of the list.
2. **Famous / high-traffic hooks** — game-loop, firing, targeting, save/load —
   the ones everyone eventually touches.
3. **Easily-mistaken hooks** — anywhere the address's scope (per-type vs
   per-instance, per-frame vs event-driven) trips people up.

## Pages

| Page | Subsystem | Status |
|---|---|---|
| [Ext-Aircraft.md](Ext-Aircraft.md) | Aircraft | seed (1 exemplar entry) |
- [Map Reveal / Sight](Map-Reveal-Sight.md) — RevealArea0/1/2; the big-map trap (YRpp hardcodes stride 512 at compile time).
| [AI-Trigger-Team-Lifecycle.md](AI-Trigger-Team-Lifecycle.md) | AI trigger evaluation, team selection & lifecycle | vanilla-RE (7 behavioural + 4 extension sites; unhooked by frameworks) |
| [Attachment-Cell-Placement.md](Attachment-Cell-Placement.md) | Unit placement marking, cell occupation, custom-locomotor recursion | 4 entries (2 registry-absent DEFINE_JUMPs, 1 do-not-hook, 1 three-framework conflict) |
| [Map-Cell-Indexing.md](Map-Cell-Indexing.md) | Map coordinate→cell indexing & row stride | vanilla-RE (the 512 stride machinery; map-resize crash surface) |
| [PlayerCount-HouseLimits.md](PlayerCount-HouseLimits.md) | Player Count & House-Array Limits | partial (source-confirmed; YR AssignHouses internals pending disasm; RE-vet downstream break-site roadmap added, unverified) |
| [Input-ActiveClickWith.md](Input-ActiveClickWith.md) | Active-click order dispatch + building-planning guard | 2 entries (full-reimpl conflict hazard: PR#352 vs PR#1993 vs release 0x4AE95E) |

_(Add a row per subsystem page as it's created. Subsystem names mirror the
`Subsystem` column in the registry.)_

## Writing standard

- Key each entry by **address**, with the engine function name as the heading.
- Fill the **"does not do — easily mistaken"** field. If you can't think of a
  misconception, say so briefly rather than leaving it blank — a blank reads as
  "not yet written."
- **Cite how you confirmed each claim.** Upstream source (name file + version),
  Ghidra/objdump, or in-game test. Mark guesses as unverified. An honest
  "unconfirmed" is worth more than a confident error.
- Frame everything around the **vanilla engine and public frameworks**. Do not
  make a private mod the subject of an entry (incidental-consumer mention only —
  see the neutrality rule in the top-level README).
