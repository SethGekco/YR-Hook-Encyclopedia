#!/usr/bin/env python3
"""
build_registry.py — Tier 1 registry builder for the YR Hook Encyclopedia.

Merges every known gamemd.exe hook from the supported frameworks into a single
address-keyed registry. The address is the primary key: when two frameworks
hook the same address, that is a real compatibility conflict, and this script
makes it visible.

Outputs (all under ../registry/):
  hooks.csv        Flat, one row per (address, framework) consumer. Sorted by address.
  hooks.json       Address-keyed. Each address lists every framework that hooks it.
  conflicts.md     Human-readable list of addresses hooked by 2+ frameworks.
  STATS.md         Summary counts, regenerated each run.

Sources are defined in SOURCES below. Re-run this whenever a source updates.
Nothing here is project-specific; only public frameworks are included.
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")

# --- Source locations -------------------------------------------------------
# The Ares+Phobos CSV is the pre-extracted dump kept in sources/raw/.
ARES_PHOBOS_CSV = os.path.join(ROOT, "sources", "raw", "All-Hooks-Phobos-Antares.csv")
# Kratos is extracted live from its source tree.
KRATOS_SRC = "/home/rex/KratosPP_meep/src"

# Framework label normalisation. The CSV calls Ares "Antares".
FRAMEWORK_RENAME = {"Antares": "Ares"}


def norm_addr(a):
    """Normalise an address to uppercase 0x-prefixed, no leading-zero padding beyond 0x."""
    a = a.strip()
    if not a.lower().startswith("0x"):
        a = "0x" + a
    return "0x" + a[2:].upper().lstrip("0").rjust(1, "0")


def parse_hex_size(s):
    """Stolen-byte counts are hex in every source ('0A', '10', '0x5'). Return int, or None."""
    s = s.strip()
    if s == "":
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def load_ares_phobos(rows):
    if not os.path.exists(ARES_PHOBOS_CSV):
        print(f"WARN: missing {ARES_PHOBOS_CSV}", file=sys.stderr)
        return
    with open(ARES_PHOBOS_CSV, newline="", encoding="utf-8", errors="replace") as fh:
        rd = csv.DictReader(fh)
        for r in rd:
            fw = FRAMEWORK_RENAME.get(r["Framework"].strip(), r["Framework"].strip())
            rows.append({
                "address": norm_addr(r["Address"]),
                "framework": fw,
                "function": r["FunctionName"].strip(),
                "stolen_bytes": parse_hex_size(r["StolenBytes"]),
                "subsystem": r["Subsystem"].strip(),
                "source_file": r["SourceFile"].strip(),
            })


# DEFINE_HOOK(0xADDR, Name, 0xSIZE)  and DEFINE_HOOK_AGAIN(...)
HOOK_RE = re.compile(
    r"DEFINE_HOOK(?:_AGAIN)?\s*\(\s*(0x[0-9A-Fa-f]+)\s*,\s*([A-Za-z_]\w*)\s*,\s*(0x[0-9A-Fa-f]+)"
)


def kratos_subsystem(rel):
    """Map a Kratos source filename to an Ext/<Type> subsystem, matching the CSV style."""
    stem = os.path.splitext(os.path.basename(rel))[0]
    for suf in ("ExtHooks", "ExtHook", "Hook"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    misc = {"General", "GScreen", "LaserDraw", "PointerExpire", "SaveGame", "Extension", ""}
    if stem in misc:
        return "Misc"
    return "Ext/" + stem


def load_kratos(rows):
    if not os.path.isdir(KRATOS_SRC):
        print(f"WARN: missing Kratos src {KRATOS_SRC}", file=sys.stderr)
        return
    for dirpath, _, files in os.walk(KRATOS_SRC):
        for fn in files:
            if not fn.endswith((".cpp", ".h")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, KRATOS_SRC)
            try:
                text = open(full, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in HOOK_RE.finditer(text):
                rows.append({
                    "address": norm_addr(m.group(1)),
                    "framework": "Kratos",
                    "function": m.group(2),
                    "stolen_bytes": parse_hex_size(m.group(3)),
                    "subsystem": kratos_subsystem(rel),
                    "source_file": rel.replace(os.sep, "/"),
                })


def addr_key(a):
    return int(a, 16)


def main():
    rows = []
    load_ares_phobos(rows)
    load_kratos(rows)

    # Deduplicate identical (address, framework, function) rows; DEFINE_HOOK_AGAIN
    # legitimately repeats a function name across addresses, so key on all three.
    seen = set()
    uniq = []
    for r in rows:
        k = (r["address"], r["framework"], r["function"], r["source_file"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    rows = uniq
    rows.sort(key=lambda r: (addr_key(r["address"]), r["framework"], r["function"]))

    os.makedirs(REG, exist_ok=True)

    # --- hooks.csv ---
    with open(os.path.join(REG, "hooks.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Address", "Framework", "Function", "StolenBytes", "Subsystem", "SourceFile"])
        for r in rows:
            sb = "" if r["stolen_bytes"] is None else "0x%X" % r["stolen_bytes"]
            w.writerow([r["address"], r["framework"], r["function"], sb, r["subsystem"], r["source_file"]])

    # --- hooks.json (address-keyed) ---
    by_addr = defaultdict(list)
    for r in rows:
        by_addr[r["address"]].append(r)
    j = {}
    for addr in sorted(by_addr, key=addr_key):
        consumers = by_addr[addr]
        fws = sorted({c["framework"] for c in consumers})
        j[addr] = {
            "frameworks": fws,
            "shared": len(fws) > 1,
            "consumers": [
                {
                    "framework": c["framework"],
                    "function": c["function"],
                    "stolen_bytes": None if c["stolen_bytes"] is None else "0x%X" % c["stolen_bytes"],
                    "subsystem": c["subsystem"],
                    "source_file": c["source_file"],
                }
                for c in consumers
            ],
        }
    with open(os.path.join(REG, "hooks.json"), "w", encoding="utf-8") as fh:
        json.dump(j, fh, indent=2)
        fh.write("\n")

    # --- conflicts.md ---
    shared = [(a, v) for a, v in j.items() if v["shared"]]
    with open(os.path.join(REG, "conflicts.md"), "w", encoding="utf-8") as fh:
        fh.write("# Shared-address map (potential conflicts)\n\n")
        fh.write("_Auto-generated by `scripts/build_registry.py`. Do not edit by hand._\n\n")
        fh.write(
            "Every address below is hooked by **two or more** frameworks. Two frameworks "
            "patching the same address is the classic source of incompatibility: whichever "
            "loads second may overwrite the first, or their stolen bytes may overlap. A shared "
            "address is not *automatically* a bug — some are the same well-known engine call "
            "site that everyone hooks compatibly — but each one is worth a human look. "
            "See the encyclopedia entry for the address before assuming either.\n\n"
        )
        fh.write(f"**{len(shared)}** shared addresses.\n\n")
        fh.write("| Address | Frameworks | Functions |\n|---|---|---|\n")
        for a, v in sorted(shared, key=lambda kv: addr_key(kv[0])):
            fns = "<br>".join(f"`{c['framework']}`: {c['function']}" for c in v["consumers"])
            fh.write(f"| `{a}` | {', '.join(v['frameworks'])} | {fns} |\n")

    # --- STATS.md ---
    per_fw = defaultdict(int)
    for r in rows:
        per_fw[r["framework"]] += 1
    with open(os.path.join(REG, "STATS.md"), "w", encoding="utf-8") as fh:
        fh.write("# Registry statistics\n\n")
        fh.write("_Auto-generated by `scripts/build_registry.py`._\n\n")
        fh.write(f"- Total consumer rows: **{len(rows)}**\n")
        fh.write(f"- Distinct addresses: **{len(by_addr)}**\n")
        fh.write(f"- Shared addresses (2+ frameworks): **{len(shared)}**\n\n")
        fh.write("## Hooks per framework\n\n| Framework | Hooks |\n|---|---|\n")
        for fw in sorted(per_fw, key=lambda f: -per_fw[f]):
            fh.write(f"| {fw} | {per_fw[fw]} |\n")

    print(f"OK: {len(rows)} rows, {len(by_addr)} addresses, {len(shared)} shared.")
    for fw in sorted(per_fw, key=lambda f: -per_fw[f]):
        print(f"  {fw}: {per_fw[fw]}")


if __name__ == "__main__":
    main()
