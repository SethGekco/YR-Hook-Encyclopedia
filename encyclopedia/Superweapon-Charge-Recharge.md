# Superweapon Charge & Recharge

How a `SuperClass` instance's recharge timer is armed, read and displayed, and
where a DLL can change a superweapon's recharge time per house. Companion to
[Superweapon-Launch-Targeting.md](Superweapon-Launch-Targeting.md), which covers
the launch path (`Fire_SW` → `ClickFire` → `Launch`).

## Structure: the fields that matter

From YRpp `SuperClass.h` / `Timer.h` (submodule `3ba9495`). `AbstractClass` ends at `+0x24`.

| Offset | Field | Notes |
|---|---|---|
| `+0x24` | `int CustomChargeTime` | Per-instance override of `Type->RechargeTime`. YRpp: `SetRechargeTime` "makes this SW recharge in this many frames, as opposed to [Type]RechargeTime"; `ResetRechargeTime` "nullifies the previous call". `-1` = unset (**inferred** from the YRpp comments and from framework code that never touches it; the vanilla body of `0x6CC260` has not been disassembled) |
| `+0x28` | `SuperWeaponTypeClass* Type` | `Type->RechargeTime` is in frames |
| `+0x2C` | `HouseClass* Owner` | |
| `+0x30` | `CDTimerClass RechargeTimer` | `StartTime` `+0x30`, `CurrentTime` (clock ptr) `+0x34`, **`TimeLeft` `+0x38`** |
| `+0x6D` | `bool IsPresent` | |
| `+0x6F` | `bool IsReady` | |
| `+0x70` | `bool IsSuspended` | on hold |

The timer's `TimeLeft` holds the **total** duration while it runs. Remaining time
is computed as `TimeLeft − (now − StartTime)`. `Pause()` folds the elapsed time
into `TimeLeft` and sets `StartTime = −1`; `Resume()` sets `StartTime = now`. So
while the timer runs, the `(StartTime, TimeLeft)` pair changes only on
`Start`/`Pause`/`Resume` or a direct write. That makes it a usable
"was the timer re-armed?" signature for a per-frame observer.

Non-virtual engine functions (YRpp `JMP_THIS` addresses):

| Address | Function |
|---|---|
| `0x6CB4D0` | `SetOnHold(bool)` |
| `0x6CB560` | `Grant(oneTime, announce, onHold)` |
| `0x6CB7B0` | `Lose()` |
| `0x6CB830` | `StopPreclickAnim(bool isPlayer)`. Antares' ClickFire calls it after a normal (non-Pre/PostClick) launch |
| `0x6CB920` | `ClickFire(bool isPlayer, CellStruct const&)` |
| `0x6CBCA0` | `HasChargeProgressed(bool isPlayer)` |
| `0x6CBEE0` | `AnimStage()`: the cameo overlay frame |
| `0x6CC1E0` | `SetCharge(int percentage)` |
| `0x6CC260` | `GetRechargeTime()` |
| `0x6CC280` | `SetRechargeTime(int)` |
| `0x6CC290` | `ResetRechargeTime()` |
| `0x6CE0B0` | `Reset()` |

---

### `0x4F8440` — HouseClass::Update (entry)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `HouseClass_Update_TogglePower` | 0x5 | src/Ext/House/Hooks.cpp |
| Ares | `HouseClass_Update_TogglePower` | 0x5 | src/Ext/House/Hooks.cpp |

**What it does.** This is the entry of the per-house logic tick. It runs once per
house per logic frame, with `ECX = HouseClass*`. Antares/Ares run
`HouseExt::UpdateTogglePower()` there and `return 0`.

**What it does *not* do — easily mistaken.**
- It is **not** a superweapon update. SW timers keep running on their own
  clock (`RechargeTimer` is frame-based), so code here sees a timer at most one
  frame after it was armed. Rescaling `TimeLeft` in place while keeping
  `StartTime` is exact, because the frame already elapsed still counts.
- It does not run before map-start objects are placed. A SW granted by a
  pre-placed building can already be charging by the time this first fires.

**Used by / interactions.** Both hooks are cooperative 5-byte `return 0`
handlers, so the stolen bytes are a proven instruction boundary. It is a good,
low-risk per-house per-frame seam: iterate `pHouse->Supers` for per-house SW work.
Country_Extension (private, sole consumer of this use) co-hooks it (size 5,
`return 0`) to apply `SuperWeapon.Ratio=`. It **builds** (DevBuild CI run #24,
2026-09-24); in-game behaviour is **not yet verified**.

**Register / calling convention.** `__thiscall`, `ECX = HouseClass* pThis`.

**Confirmed via.** Antares source (`src/Ext/House/Hooks.cpp:524`), registry
rows. The co-hook is build-verified only.

### `0x6CB4D0` — SuperClass::SetOnHold (full replacement)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SuperClass_SetOnHold` | 0x6 | src/Ext/SWType/Hooks.cpp |
| Ares | `SuperClass_SetOnHold` | 0x6 | src/Ext/SWType/Hooks.cpp |

**What it does.** Antares rewrites the whole function (it returns `0x6CB555`).
It `Pause()`s or `Resume()`s `RechargeTimer`. For ChargeDrain SWs it re-arms
the timer with **`GetRechargeTime()`**, and converts leftover drain time back
into charge time using `SW.ChargeToDrainRatio`.

**What it does *not* do — easily mistaken.** With Antares loaded, the vanilla
body never runs. A hook inside `0x6CB4D6..0x6CB555` is dead code.

**Confirmed via.** Antares source (`src/Ext/SWType/Hooks.cpp`, `SuperClass_SetOnHold`).

### `0x6CB70C` — SuperClass::Grant (timer arming)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SuperClass_Grant_InitialReady` | 0xA | src/Ext/SWType/Hooks.cpp |

**What it does.** This is where a newly granted SW's first charge is armed.
Antares writes `RechargeTimer.StartTime = now` and
`TimeLeft = GetRechargeTime()`, or `0` for `SW.InitialReady`. It moves
`StartTime` back for `SW.VirtualCharge`, then jumps to `0x6CB750`.

**What it does *not* do — easily mistaken.** The duration comes from
**`GetRechargeTime()`**, not `Type->RechargeTime`. So a `CustomChargeTime`
set **before** the grant is honoured, and one set after it only affects the
*next* arming. That is exactly why a "set `CustomChargeTime` lazily in a
per-frame hook" approach misses the first charge.

**Confirmed via.** Antares source (`SuperClass_Grant_InitialReady`).

### `0x6CB920` — SuperClass::ClickFire (full replacement)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SuperClass_ClickFire` | 0x5 | src/Ext/SWType/Hooks.cpp |
| Ares | `SuperClass_ClickFire` | 0x5 | src/Ext/SWType/Hooks.cpp |

**What it does.** Antares replaces the whole function (it returns `0x6CBC9C`).
After `Launch()` it clears `IsReady`, then does one of three things:
- **One-shot, or out of `SW.Shots`:** calls `Lose()`.
- **ManualControl:** `RechargeTimer.Start(GetRechargeTime())`, then `Pause()`.
- **Normal SW:** calls **`StopPreclickAnim(isPlayer)` (`0x6CB830`)**. The
  post-fire re-arm for an ordinary SW therefore happens inside vanilla
  `StopPreclickAnim`, not inside ClickFire.

**What it does *not* do — easily mistaken.**
- A hook inside vanilla ClickFire's body is dead code under Antares.
- Whether vanilla `StopPreclickAnim` arms with `GetRechargeTime()` or reads
  `Type->RechargeTime` directly is **unverified**. Earlier Country_Extension
  attempts hooked `0x6CB8DC` and `0x6CB8F4` inside it ("write to `[ESI+0x38]`",
  i.e. `RechargeTimer.TimeLeft`), and neither produced a working ratio in-game.
  The address/register claims behind them were never objdump-confirmed.

**Confirmed via.** Antares source. The `StopPreclickAnim` internals are unverified.

### `0x6CBCA0` — SuperClass::HasChargeProgressed (entry, unhooked)

**Framework names**
None at the entry. Antares/Ares hook inside it at `0x6CBCDE`, `0x6CBD6B` and
`0x6CBD86`; Phobos at `0x6CBD2C`.

**What it does.** Per-frame charge update for one SW. It returns true when the
cameo overlay stage changed, and triggers the "ready" EVA. The Antares
`Update_DrainMoney` hook inside it drains money for AI owners too, so it runs
for every house, not only the local player.

**What it does *not* do — easily mistaken.**
- **⚠ The entry's stolen-byte count is unverified.** Country_Extension
  shipped a 6-byte entry hook here (commit `db04754`) without checking the
  prologue's instruction boundaries, and the feature never worked. Prefer
  `0x4F8440` (above) as a per-frame seam, where the size is proven.
- It does not arm the recharge timer. Arming happens in Grant, ClickFire/
  `StopPreclickAnim`, SetOnHold and `Reset`.

**Confirmed via.** YRpp comment, registry, Antares source. The prologue is unverified.

### `0x6CBF5B` — SuperClass::AnimStage (cameo percentage)

**Framework names**
| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| Antares | `SuperClass_GetCameoChargeStage_ChargeDrainRatio` | 0x9 | src/Ext/SWType/Hooks.cpp |
| Ares | `SuperClass_GetCameoChargeStage_ChargeDrainRatio` | 0x9 | src/Ext/SWType/Hooks.cpp |

**What it does.** It computes the darken-overlay stage from stack locals: two
copies of the recharge time (`[esp+0x10]`, `[esp+0x14]`) and `timeLeft`
(`[esp+0xC]`), as `1 − (R·ratio − left)/(R·ratio)`, in 55 steps. Then it jumps
to `0x6CC053`.

**What it does *not* do — easily mistaken.** **Scaling only
`RechargeTimer.TimeLeft` desynchronises the cameo** unless the recharge time
`R` read here is scaled too. That is why per-house recharge scaling should go
through `CustomChargeTime` (so `GetRechargeTime()` agrees with the timer),
not only through the timer. Whether `R` here comes from `GetRechargeTime()` or
`Type->RechargeTime` is **unverified**.

**Confirmed via.** Antares source. Where `R` comes from is unverified.

### `0x6CC260` / `0x6CC280` / `0x6CC290` — Get/Set/ResetRechargeTime (unhooked)

**Framework names**
None. The registry has nothing between `0x6CC1E6` and `0x6CC2B0`.

**What it does.** Per YRpp: `GetRechargeTime()` returns the effective full
recharge time (`CustomChargeTime` if set, else `Type->RechargeTime`).
`SetRechargeTime(t)` stores `t` into `CustomChargeTime` (`+0x24`), and
`ResetRechargeTime()` unsets it. Callers that read the duration through
`GetRechargeTime()` include:
- Antares Grant, ClickFire (ManualControl) and SetOnHold (ChargeDrain);
- the Antares Team ext (`Body.cpp:59`);
- Phobos tooltips (`PhobosToolTip.cpp:177`), SW sidebar UI
  (`Hooks.UI.cpp:626`) and AI script logic (`Script/Body.cpp:1203`).

**What it does *not* do — easily mistaken.**
- **`SetRechargeTime` does not touch the running timer.** It changes the
  *next* arming only. Calling it while the SW is charging leaves the current
  charge at its old length.
- It is not called by anything in vanilla-path code we have confirmed.
  `CustomChargeTime` is effectively free per-instance state. It is saved in
  savegames as part of `SuperClass`.

**Used by / interactions.** Country_Extension writes `CustomChargeTime`
directly from `0x4F8440` to implement per-country recharge ratios. As a
backstop, it rescales any freshly armed timer that still holds exactly
`Type->RechargeTime`, which covers arms that bypass `GetRechargeTime()` or
happened before the first house update. Build-verified; **in-game unverified**.

**Confirmed via.** YRpp `SuperClass.h` comments and signatures; framework
source greps (Antares `9f25bdb`-era clone, Phobos HEAD). The function bodies
were **not** disassembled.

---

## Open questions (resolve with objdump of `gamemd.exe`)

1. Does `0x6CC260` compare `CustomChargeTime` against `-1`, or against `<= 0`?
2. Does `StopPreclickAnim` (`0x6CB830`) arm with `GetRechargeTime()` or with
   `Type->RechargeTime`? Does `Reset()` (`0x6CE0B0`)?
3. Where does `AnimStage`'s `R` (`[esp+0x10]`/`[esp+0x14]`) come from?
4. What are the prologue bytes at `0x6CBCA0` (for anyone who still wants an
   entry hook there)?
