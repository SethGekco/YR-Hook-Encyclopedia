# Cell Numbering, Order Targets, and Pathfinder Internals (gamemd.exe 1.001)

Findings from the MapSizeExt stride-2048 campaign (2026-08). Framework-neutral.
Companion: `Map-Cell-Indexing.md` (grid stride) and MapSizeExt
`docs/STRIDE-1024-SPEC.md` (the full 1024 spec).

## The base-1000 external cell number (N = Y*1000 + X)

Distinct from the grid stride: map INIs, waypoints, and **order targets** identify a
cell by `N = Y*1000 + X` (iso rx/ry). Caps representable maps at W+H ≤ 1000.

**Encoders (×1000):**
- `0x6E6AC0` **TargetClass::From(AbstractClass*)** — THE order-target encoder.
  `call [vt+0x2C]` (WhatAmI) → `cmp eax,0xB` (cell RTTI) → type byte to out+4 →
  reads MapCoords dword `[cell+0x24]` → lea-×125 chain **with a one-byte
  `pop edi` interleaved @0x6E6ADD** → `lea eax,[edx+ecx*8]` @0x6E6AE4 = X+1000·Y →
  store out+0. Non-cell branch: type 0x34 + `call [vt+0x10]` (GetID), ret 0x6E6AFC.
- `0x6E6B20` (from CellStruct*) and `0x6E6B70` (from CoordStruct*, leptons ÷256):
  same ×125-lea shape; vtable-dispatched, save/serialize paths.
- Forest fire: encode `0x71CBF2` (sprintf "%d" of N), decode `0x71CAEF` (atoi + ÷1000)
  — a self-consistent pair.
- Phobos.dll (build 48): waypoint parser decode imul @RVA 0x80109, waypoint INI
  writeback imul @RVA 0x8029A (the DLL's only ×1000s besides RGB math @0x961xx).

**Decoders (÷1000, idiv 0x3E8 + 0x10624DD3 magic pair):**
- `0x6E6ED0` (type==0xB) and `0x6E7C2C` — the event-target pair (target +
  MegaMission destination), both end in `GetCellAt @0x5657A0`.
- `0x4AD232`, `0x4ADC17` — DisplayClass; 0x4ADC17 loops (index,N) pairs into the
  Scenario waypoint setter `0x68BF50` (planning/waypoint feature path).
- `0x68BE0C` — the vanilla [Waypoints] reader (X=N%1000 idiv, Y re-derived via magic;
  patch both). NOTE: **Phobos's waypoint rework replaces this reader entirely**
  (its hook returns to 0x68BDB3); with Phobos loaded the vanilla decode is dead code.
- Dual-format gate: `[0xA8ED7C] >= 4` selects base-1000 vs a legacy ±mod-128 branch.
- ±1000 **steppers** also exist (navigation in N-space): add-0x3E8 @0x4152C2,
  0x417437, 0x41799A, 0x417B01, 0x417E2E, 0x41A7D6, 0x41AB32, 0x42A8CB, 0x4AD8FF,
  0x5DC2D7; sub-0x3E8 @0x5DF26E, 0x5F18BF, 0x5F1B01, 0x69582E.

**Scan methodology lesson (cost five hunts):** ×1000 compiles as three
`lea r,[r+r*4]` + `×8` — and the compiler may schedule a **one-byte push/pop inside
the lea chain**. Any byte-pattern scan for constant math must allow interleaved
single-byte ops. Also check: imul imm, imul reg (0F AF after mov reg,1000),
idiv, magic 0x10624DD3, sprintf-"%d" text form, and constants passed as
**pushed function arguments** (`68 E8 03 00 00`).

## Order/event pipeline anchors

- OutList object @`0x87F778`; Add fn `0x55BAA0` (arg EventClass*, checks +0x98,
  delegates 0x5519B0). **Carries frame-sync events only — player click orders do
  NOT pass through it** (they surface in a static packed ring, below).
- Static event region: list headers @`0xA83E00` (vt 0x7E9F24) and `0xA83E30`
  (vt 0x7E9FA4, heap ptr-array at [0xA83E34], count [0xA83E40]); byte-packed
  111-byte (0x6F) event records from ~`0xA83F5E` (target {N dword, type byte} inside).
- Human orders execute via EventClass::Execute (~0x4C7479 frame) → target decode
  0x6E6ED0/0x6E7C2C. **AI-issued missions bypass the event queue entirely** —
  a coordinate bug that spares the AI is in the human order pipeline.
- The engine's OOB dummy cell `0xABDC50` is a **legitimate flow-control sentinel**
  (compared at 0x47D2B8, 0x51FE41 infantry scatter, eight 0x56Bxxx sites …); its
  scratch MapCoords @0xABDC74 are rewritten by every failed lookup. Never repurpose
  it — substituting NULL breaks scatter/stop logic game-wide. Lookup fail paths that
  write the scratch: op[](Cell&) @0x565712, op[](lepton) @0x565789, GetCellAt
  @0x5657CF.

## A* pathfinder internals

- `FootClass::UpdatePathfinding @0x4D3920` (chkstk 0x1F9C): **arg1 @[esp+4] is the
  packed TARGET CellStruct** (converted ×256+128 to leptons, checked via vt+0x2CC);
  arg2 is a pointer. (An earlier note calling arg1 "start" was wrong.)
  FootClass Destination object ptr = `[this+0x5A4]` (13 writer sites; e.g. 0x4D9510).
- Node allocator `0x42A460`: pool A at [AStar+0x10], 16-byte nodes, **counter stored
  AT base+0x100000** (65,536 cap); pool B at [AStar+0xC], 12-byte, counter at
  base+0x180000 (131,072 cap). **No bounds check** — the node written at slot 65,536
  lands on the counter → next alloc goes wild → delayed heap corruption (intermittent
  wild-EIP fatals; corrupted vtable low bytes). Counter resets per search @0x42A5B9/C3;
  ctor allocs `push 0x100004` @0x42A7E0, `push 0x180004` @0x42A814.
- **The game allocator (0x7C8E17 → 0x7C9442, CRT small-block with threshold at
  [0x87C584]) will not return large contiguous blocks** — enlarging these pools by
  patching sizes crashes at launch. Mitigate by clamping the counters
  (≤0xFFFE / ≤0x1FFFE) at the two count-reads (0x42A466 / 0x42A482) instead.
- Under sustained path failure (unreachable targets re-pathed every frame) a further
  overflow beyond these two pools exists (fatals with EDX=0x7EB05D, stack
  0x55B613 LogicClass_Update) — unresolved as of 2026-08-18.

## Iso diamond geometry (the dense lattice)

Valid cells exist at **both parities** of rx+ry (half-offset rows; (2W−1)·H cells):
`dx = rx−ry+W−1 ∈ [0, 2W−2]`, `dy = rx+ry−W−1 ∈ [0, 2H−1]`, any integer pair.
An even-parity-only membership test silently misclassifies half of all cells.
Convert: `rx=(dx+dy)/2+1`, `ry=(dy−dx)/2+W`. Vanilla clamps off-map orders to the
nearest cell (the click path); replicate that when re-basing decoders.

## Syringe / patching gotchas

- `R->ESP(v)` never takes effect (popad discards it) — to skip a function, return
  the address of a bare `ret`; never hook a window containing `add esp, imm`.
- Patch functions called from another TU must not be `static` (LNK2019).
- Byte-verify before every write; a mismatch should skip, not corrupt.
- Hook-at-entry with `return 0` re-executes the stolen bytes in the trampoline.
