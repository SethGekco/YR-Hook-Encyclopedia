# Veterancy Abilities

How the engine answers "does this unit have ability X", and why that answer has
exactly one door.

---

### `0x70D0D0` — TechnoClass::HasAbility

**Framework names**

| Framework | Function name | Stolen | Source file |
|---|---|---|---|
| — | *(no framework in the registry hooks this address)* | — | — |

YRpp declares it as a real call: `bool HasAbility(Ability) const { JMP_THIS(0x70D0D0); }`
(`TechnoClass.h`).

**What it does.** Returns whether the unit currently has an ability, by checking
its veterancy level and then indexing the type's ability tables:

```
0x70D0D0  push ebx; push esi; mov esi,ecx; push edi   ; 5 bytes
0x70D0D5  lea edi,[esi+0x150]                         ; &this->Veterancy
0x70D0DD  call 0x74FF90                               ; IsVeteran   (unverified name)
0x70D0E8  call 0x750010                               ; IsElite     (unverified name)
0x70D0F5  call [vt+0x84]                              ; GetTechnoType
0x70D104  mov ebx,[esp+0x10]                          ; the Ability argument
0x70D10C  mov al,[esi+ebx+0x29C]                      ; VeteranAbilities[ability]
0x70D135  mov al,[esi+ebx+0x2AE]                      ; EliteAbilities[ability]
0x70D117  pop edi; pop esi; mov al,1; pop ebx; ret 4  ; TRUE
0x70D145  ...                                         ; TRUE (elite path)
0x70D148  pop edi; pop esi; xor al,al; pop ebx; ret 4 ; FALSE
```

Note `0x2AE - 0x29C = 0x12 = 18`, exactly the size of YRpp's `AbilitiesStruct`
(18 `bool`s, `Ability` enum `Faster=0 .. Crusher=17`) — the two tables are
adjacent, which corroborates both offsets.

An **elite** unit gets veteran abilities too: the elite branch at `0x70D11F` is
only reached when the veteran test failed.

**Why it matters.** There are **34 `call 0x70D0D0` sites** in `gamemd.exe`. For a
function that gates a gameplay-visible property, that is unusually centralised:
one hook can grant or revoke abilities for every consumer that asks politely.

**What it does *not* do — easily mistaken.**

* **It is not the only reader of the ability tables.** `VeteranAbilities` /
  `EliteAbilities` at `TechnoTypeClass +0x29C` / `+0x2AE` can also be read
  directly. Any feature that claims "all abilities" on the strength of this hook
  alone is claiming more than it verified. ⚠ **Unverified:** the 34 call sites
  have not been classified, and no sweep for direct readers of `+0x29C`/`+0x2AE`
  has been done. Treat "every ability works" as an open question.
* **Hooking the entry is a trap.** Both shared exits (`0x70D117`, `0x70D148`)
  begin `pop edi; pop esi; ... pop ebx`. At `0x70D0D0` those three registers have
  not been pushed yet, so a hook at the entry that returns one of the exits pops
  the caller's frame. Hook `0x70D0D5` instead (6 bytes, `lea`): by then the
  pushes are done, and the `Ability` argument sits at `[esp+0x10]`
  (3 pushes + return address) rather than `[esp+0x4]`.
* **An add-only hook cannot take an ability away.** Returning early only when you
  want to grant means the vanilla body still answers `true` for anything
  veterancy grants. A hook that needs to *suppress* an ability must compute the
  whole answer, including the vanilla veterancy contribution, and return one of
  the two exits.

**Register / calling convention.** `__thiscall`, `ECX = TechnoClass*`,
one stack argument (`Ability`, 4 bytes), `ret 4`. Result in `AL`.

**Confirmed via** objdump of vanilla `gamemd.exe`; call-site count from a
`call 0x70d0d0` sweep of a full disassembly; YRpp `TechnoClass.h` /
`TechnoTypeClass.h` / `GeneralDefinitions.h` for the signature, table layout and
enum. **Unverified:** the names of `0x74FF90` / `0x750010` (inferred from the
`VeterancyStruct` this-pointer and the branch structure), and whether any code
path reads the ability tables without calling this function.
