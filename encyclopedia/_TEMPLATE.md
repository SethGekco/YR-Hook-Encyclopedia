<!--
Copy this block into the appropriate subsystem page for each hook you write up.
Keep entries sorted by address within a page. Delete this comment in the copy.
Every claim should be confirmable; mark anything you did not verify as such.
-->

### `0xADDRESS` — EngineFunctionName

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Ares   | … | 0x? | Ares.cpp |
| Phobos | … | 0x? | Ext/…/Hooks.cpp |
| Kratos | … | 0x? | Hooks/…Hook.cpp |

**What it does.** The concrete behaviour changed at this address — the vanilla
code being intercepted and what the hook makes happen instead.

**What it does *not* do — easily mistaken.** The specific wrong assumptions this
hook invites. (e.g. "fires per unit" when it fires per *type*; "covers X" when X
goes through a different address; "runs every frame" when it's event-driven.)
Omit only if there's genuinely nothing to warn about.

**Used by / interactions.** Which frameworks patch it and how they relate — is it
the same benign call site everyone hooks, or does one framework override
another? If it's in `registry/conflicts.md`, explain whether the collision is
safe or a real incompatibility, and under what load order.

**Register / calling convention** (optional). `ECX = …`, stack args, return
convention — when known and useful for someone writing their own hook here.

**Confirmed via.** How each claim above was verified: upstream source (name the
file/version), Ghidra/objdump of vanilla `gamemd.exe`, in-game testing, or
cross-reference. Be explicit about what is **unverified**.
