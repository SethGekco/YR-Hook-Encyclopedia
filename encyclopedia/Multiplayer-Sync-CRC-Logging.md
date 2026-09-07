# Multiplayer Sync CRC & Desync Logging

The engine's out-of-sync machinery: every MP sim frame `Queue_AI` finalizes a
frame CRC (`CurrentFrameCRC`, 0xAC51FC) and stores it into the 256-entry ring
`EventClass::LatestFramesCRC` (0xB04474). When a received `FrameInfo` event's
CRC disagrees, the engine writes a `SYNC<N>.TXT` log via one of two writers:
`0x64DEA0` (normal) or `0x6516F0` (per-slot, only when
`Unsorted::EnableMPSyncDebug`, 0xB04880, is set).

## ⚠ File-level collision invisible to address-based conflict detection

**Antares and Phobos both write `SYNC<N>.TXT` on desync, from different
addresses.** Antares fully replaces the vanilla writers (`0x64DEA0`,
`0x6516F0`) with its per-object CRC state dump. Phobos hooks `0x64736D` /
`0x64CD11` — *downstream of the vanilla writer calls* — and `fopen("wt")`s the
same filename for its event-history dump (RNG calls with caller addresses,
facing/target/destination/mission changes). Execution order on the Queue_AI
path is: vanilla `call 0x64DEA0` at `0x647368` (Antares dump written) → next
instruction `0x64736D` (Phobos truncates and rewrites the file). **With both
frameworks loaded, the Antares object dump is always destroyed**; you only
ever see the Phobos-format file. `registry/conflicts.md` cannot catch this —
no address is shared. SyncTraceExt (incidental consumer) works around it by
wrapping the call sites and copying `SYNC<N>.TXT` to `SYNCSTATE<N>.TXT`
between the two writes.

### `0x647327` — Queue_AI (MP) frame-CRC ring store

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| SyncTraceExt | SyncTrace_QueueAI_FrameCRC | 0x6 | src/SyncTrace.cpp |

**What it does.** The window between `CurrentFrameCRC` being finalized (the
`call 0x64DAB0` at `0x64731C` computes it) and its store into
`LatestFramesCRC[frame & 0xFF]` at `0x647334`. Executes exactly once per sim
frame, on the multiplayer path only. The ideal spot for per-frame sync
instrumentation: the frame's CRC is complete, and the sim state for the frame
is final.

**What it does *not* do — easily mistaken.** Does not run in single-player
sessions (this is the MP send path). There is a second, similar ring store at
`0x64768F`/`0x6476A5` on another protocol path — instrumenting only 0x647327
may miss frames under that path (unverified which protocols use which).

**Register / calling convention.** `ECX` = current frame number (loaded from
0xA8ED84 at `0x647321`); `EDX` about to receive `CurrentFrameCRC`. Stolen
bytes `mov edx,[0xAC51FC]` — single whole instruction, absolute address, no
branch: safe to `return 0` and re-execute from the trampoline.

**Confirmed via.** objdump of vanilla gamemd (file-offset == RVA); registry
shows the address unclaimed by all indexed frameworks.

### `0x647368` / `0x64CCBA` — vanilla call sites of the SYNC writer 0x64DEA0

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| SyncTraceExt | SyncTrace_QueueAI_PreserveSyncDump / SyncTrace_ExecuteDoList_PreserveSyncDump | 0x5 | src/SyncTrace.cpp |

**What it does.** Each is exactly the 5-byte `call 0x64DEA0` instruction —
`0x647368` in Queue_AI's OOS branch, `0x64CCBA` in ExecuteDoList's. Hooking
here interposes *between* the desync detection and the (Antares-replaced)
SYNC writer, without touching either framework's claimed addresses.

**What it does *not* do — easily mistaken.** Not reached when
`EnableMPSyncDebug` is set — the debug branch calls `0x6516F0` instead
(`0x64735F`, and the `0x64CC98` loop). A hook here must NOT `return 0`: the
stolen bytes are an unrelocated rel32 call and re-executing them from the
trampoline is a wild jump (see Syringe-Stub-Semantics.md). Re-issue the call
yourself (one-arg `__fastcall` puts the `EventClass*` in ECX; it is null on
the Queue_AI path — `xor ecx,ecx` at `0x647366` — and a do-list entry pointer
at `0x64CCB3` on the other) and return the explicit next address (`0x64736D`
/ `0x64CCBF`). Calling `0x64DEA0` by address goes through the Syringe
trampoline, so Antares' replacement still runs.

**Used by / interactions.** `0x647368`'s next instruction `0x64736D` is
Phobos's `Queue_AI_WriteDesyncLog` (stolen 0x5, bytes `0x64736D–0x647371`) —
adjacent, not overlapping. `0x64CCBA` sits before Phobos/CnCNet-Spawner's
`0x64CD11`. Verified against the registry's overlap checker.

**Confirmed via.** objdump of vanilla gamemd; Antares `src/Misc/Checksum.cpp`
(hooks + full-replacement returns `0x64DF3D`/`0x651781`); Phobos
`src/Misc/SyncLogging.cpp` (hooks `0x64736D`/`0x64CD11`, filename format
identical to Antares'). The collision consequence (Phobos wins, Antares dump
lost) is inferred from instruction order + `fopen("wt")` semantics — not yet
observed in a live desync.
