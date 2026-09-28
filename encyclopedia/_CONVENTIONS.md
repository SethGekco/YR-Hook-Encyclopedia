# Conventions — how to read, and write, these pages

This reference is written for **LLM agents** working on YR DLL projects. An agent
reads a page out of context, at speed, and acts on it. So the two things that
matter most are **how much a claim is trusted** and **what it does not cover**.

---

## 1. Status markers — put one on every non-obvious claim

A claim with no marker reads as fact. Most claims here are not facts; they are
source readings, disassembly, or one in-game observation. Say which.

| Marker | Means | An agent should |
|---|---|---|
| **VERIFIED** / ✅ | Observed happening, in game or in a debugger. Say *how*. | act on it |
| *(no marker)* | Read from source or disassembly and believed sound. | act, but expect surprises |
| **⚠ Unverified** | Reasoned, never executed. | act only with a cheap check first |
| **⚠ DISPUTED** | Evidence on both sides, unresolved. | do **not** rely on either side |
| **⛔ SUPERSEDED** | Known wrong. Kept, with what replaced it. | read only to avoid re-deriving |

Every page ends with **Confirmed via** — the actual evidence. Distinguish
"Antares source says" from "objdump says" from "seen in a game": they fail
differently. If part of an entry is verified and part is not, mark the parts.

**Do not silently correct a claim.** Write that it *was* claimed, that it is
wrong, and what the evidence is. A future agent who half-remembers the old claim
needs to find the correction, not an absence.

---

## 2. When something turns out to be wrong

The lifecycle, by Rex's direction:

1. **Add a disclaimer in place.** Mark it ⚠ DISPUTED or ⛔ SUPERSEDED, state the
   contradicting evidence, and leave the original text. A wrong claim that
   *someone acted on* is itself useful information.
2. **Leave it there while it is still instructive.** Most corrections belong next
   to what they correct.
3. **Only once repeatedly confirmed wrong, archive it** — move it to
   `encyclopedia/archive/` with a line saying which page supersedes it. That
   directory is **not** for regular consumption; it exists so a claim that keeps
   resurfacing can be shown to be dead.

**Never delete.** The cost of re-deriving a dead end is higher than the cost of
storing it, and an agent that finds nothing will simply try it again.

---

## 3. Write down what a hook does *not* do

This is the part other hook lists omit and the reason this one exists. The most
valuable sentence on most pages is the one beginning "easily mistaken". Prefer:

- the neighbouring address someone will hook by mistake, and why it is wrong;
- what the framework already does, so nobody reimplements it;
- the symptom a wrong choice produces, so it is recognisable from a log.

**Lead with the symptom where you can.** An agent usually arrives holding a
symptom ("parsed, then nothing"), not an address.

---

## 4. Committing — ⚠ this repo has several concurrent writers

**Never `git add -A` here.** Multiple agent sessions write to this repo at once.
`git add -A` stages *their* uncommitted work too, and it lands under your commit
message, where `git log <file>` will never find it.

This has already happened: `f2134a4`, titled *"Ext-Turrets: a voxel body can never
occlude its turret"*, also carries 206 lines of `Techno-Type-Lifecycle.md` and 98
lines of `Buildability-Prerequisites.md` from a different session. Nothing
automated did that — this repo has **no hooks and no CI** — it was `git add -A`.

**Stage explicit paths:**

```bash
git add encyclopedia/The-Page-I-Edited.md encyclopedia/README.md
```

Also: writing a file with a truncating open (`open(p,"w")`) and a failing encode
leaves it **empty**, and `git add -A` will then commit the deletion. Write to a
temp file and `os.replace()` it.

---

## 5. Where things go

- **One page per subsystem**, entries sorted by address within it.
- **`_`-prefixed pages are meta** (this one, `_TRAPS-READ-FIRST.md`,
  `_TEMPLATE.md`) and sort to the top of a directory listing on purpose.
- **A cross-cutting trap goes in `_TRAPS-READ-FIRST.md`**, with the detail staying
  on its subsystem page. If a trap has bitten twice in different subsystems, it
  belongs there — that is the threshold.
- **Index every new page in `encyclopedia/README.md`.** An unindexed page is
  invisible; the index row is what search actually finds.

---

## 6. This tier is deliberately incomplete

~2,900 addresses exist; a few dozen are written up. That is the design. Coverage
follows **conflict-proneness and misuse-proneness**, not completeness — see the
priority order in `encyclopedia/README.md`. Do not apologise for gaps; do record
them as gaps where an agent might assume coverage.
