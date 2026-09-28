
## Binary hook extraction: the `.syhks00` record stride is 16 bytes, not 12

This registry is built from **source** (`scripts/build_registry.py`), which is why it
is complete. Binary extraction is only needed for a DLL whose source you do not have
— and there is a trap worth recording, because two independent sessions hit it.

A Syringe hook-declaration record in `.syhks00` is **16 bytes**, not 12. Parsing at
stride 12 appears to work — you get plausible-looking names — but it reads roughly
**one record in three** and manufactures garbage entries from the misalignment.
Measured on the live install:

| DLL | stride 12 (valid/total) | stride 16 (valid/total) |
|---|---|---|
| Antares.dll | 461 / 1441 | **1390 / 1464** |
| Phobos.dll | 435 / 1309 | **1298 / 1314** |
| PayloadExt.dll | 8 / 23 | **23 / 23** |

Two ways this bites:
- **False "hook is missing" conclusions.** A hook present in the binary is reported
  absent, which reads as source/binary drift and sends you rebuilding to fix nothing.
- **False "nothing else hooks this" conclusions.** A sweep at stride 12 under-reports
  by ~2/3, so "no other DLL touches this address" is unsafe. One such sweep listed 4
  hooks in a window that actually contains 18.

Sanity check before trusting any sweep: `.syhks00` virtual size should be divisible
by 16, and a correct parse yields almost no records with an implausible address
(outside `0x401000`–`0x8FFFFF`) or a zero patch size.
