#!/usr/bin/env python3
"""
build_engine_string_surface.py — Phase E: the full engine-read tag surface.

Phase D looked up a known list of rules tags in the binary. Phase E goes the other
way: it enumerates EVERY identifier-string the engine pushes as a call argument
(`push offset "Str"` = 68 <VA> on x86), giving the complete set of strings the
engine reads — from rulesmd, artmd, aimd, sound, and anything else — each with the
exact code address(es) that read it. Then it classifies each string by which INI
file it appears in as a key.

This is a superset of Phase D. Its extra value:
  - covers art / AI / sound / etc. tags, not just rules (answers "other sources?");
  - surfaces UNCLASSIFIED identifier strings the engine reads that aren't in any
    INI we have — candidate *undocumented* tags worth investigating.

*** UNVERIFIED / HEURISTIC. *** A push-ref is where a string is referenced, i.e.
where the tag is parsed — a candidate hook site, not proof of behaviour. Some
pushed strings are filenames or object IDs, not tags; those are flagged.

Outputs: registry/engine-string-surface.csv, .json, .md
"""

import csv
import json
import os
import re
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")

EXE = "/home/rex/gamemd.exe"
# Vanilla INIs are cached under sources/ini-cache/ (gitignored, NOT published — game
# data). Refresh with scripts/update_ini_cache.sh, which extracts the vanilla YR and
# RA2 zips. Reading from the cache makes the build reproducible instead of depending on
# a volatile loose folder. Only the DERIVED classification (string -> domain -> address)
# is committed, never the INI contents.
_YR = os.path.join(ROOT, "sources", "ini-cache", "yr")
_RA2 = os.path.join(ROOT, "sources", "ini-cache", "ra2")
_TS = os.path.join(ROOT, "sources", "ini-cache", "ts")
# domain -> list of INI files that define that domain's keys. Cross-referenced to
# label which strings the engine pushes are real tags (and of what kind). All vanilla.
INI_UNIVERSES = {
    "rules":   [f"{_YR}/rulesmd.ini"],
    "art":     [f"{_YR}/artmd.ini"],
    "ai":      [f"{_YR}/aimd.ini"],
    "sound":   [f"{_YR}/soundmd.ini"],
    "eva":     [f"{_YR}/evamd.ini"],
    "theme":   [f"{_YR}/thememd.ini"],
    "ui":      [f"{_YR}/uimd.ini"],
    "rmg":     [f"{_YR}/rmgmd.ini"],
    "battle":  [f"{_YR}/battlemd.ini"],
    "mission": [f"{_YR}/missionmd.ini"],
    "mapsel":  [f"{_YR}/mapselmd.ini"],
    "coop":    [f"{_YR}/coopcampmd.ini"],
    "theater": [f"{_YR}/{n}md.ini" for n in
                ("desert", "lunar", "snow", "temperat", "urban", "urbann")],
    "mp":      [f"{_YR}/{n}md.ini" for n in
                ("mpmodes", "mpbattle", "mpcoop", "mpduel", "mpfreeforall",
                 "mpmeat", "mpmw", "mpnaval", "mpsiege", "mpteam", "mpunholy")],
    # Original Red Alert 2 (pre-Yuri) INIs. YR runs on the RA2 engine (which runs on
    # Tiberian Sun's), so the binary still reads tags RA2/TS used even where YR's own
    # INI templates dropped them (TS Veinhole `VeinAttack`, the `AIIonCannon*` weights,
    # old AI build tags). A string classed ONLY as `ra2` here is a candidate leftover/
    # legacy tag — vestigial in YR but still read by the engine.
    "ra2":     [f"{_RA2}/{n}.ini" for n in
                ("rules", "art", "ai", "sound", "keyboard", "ui", "theme", "tutorial",
                 "mission", "mapsel", "battle", "coopcamp", "rmg", "mpmodes", "mpbattle",
                 "mpcoop", "mpduel", "mpfreeforall", "mpmeat", "mpmw", "mpnaval",
                 "mpsiege", "mpunholy", "snow", "temperat", "urban", "eva")]
               + [f"{_RA2}/missions.pkt"],
    # Tiberian Sun (+ Firestorm) INIs — the base engine YR ultimately descends from.
    # A string classed as `ts` but not `ra2`/YR is the DEEPEST legacy: a TS tag the YR
    # engine still reads (e.g. TS Ion-storm / Veinhole / Firestorm-era logic). Cloned
    # from Vinifera-Developers/Tiberian-Sun-INIs into the gitignored cache.
    "ts":      [f"{_TS}/{n}.INI" for n in
                ("RULES", "FIRESTRM", "ART", "ARTFS", "AI", "AIFS", "SOUND", "ION",
                 "KEYBOARD", "MAPSEL", "MISSION", "THEME", "TUTORIAL", "BATTLE",
                 "NEWMENU", "SNOW", "TEMPERAT", "DAY", "DUSK", "MORNING", "NIGHT")],
    # Map/scenario files are INI text too ([Basic]/[Map]/[SpecialFlags]/lighting/
    # trigger sections) and carry scenario keys the engine reads that appear in no
    # other INI (HomeCell, CarryOverMoney, NextScenario, IceGrowthEnabled, ...).
    # A few representative vanilla maps give the common key set; .mmx are packed but
    # their plaintext headers still contribute. Add more maps here to widen coverage.
    "map": [
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/RA2/ra2 oringanal/all08u.map",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/RA2/ra2 oringanal/all09t.map",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/RA2/ra2 oringanal/ISLEOFWAR.mpr",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/RA2/ra2 oringanal/malibucliffs.mpr",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/000-RA2YR Vanilla/Battleroyale.yrm",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/000-RA2YR Vanilla/HailMary.mmx",
        "/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/000-RA2YR Vanilla/BayOPigs.mmx",
    ],
}

FILE_EXT = re.compile(r"\.(INI|MIX|PAL|SHP|VXL|HVA|PCX|WAV|AUD|CSF|BAG|IDX|TXT|BIN|MAP|PKT|TMP|DLL|EXE)$", re.I)
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9._]{2,39}$")


def parse_pe(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    sizeopt = struct.unpack_from("<H", data, e + 20)[0]
    opt = e + 24
    imgbase = struct.unpack_from("<I", data, opt + 28)[0]
    so = opt + sizeopt
    secs = []
    for i in range(nsec):
        b = so + i * 40
        name = data[b:b + 8].rstrip(b"\0").decode("latin1")
        vs, va, rs, pr = struct.unpack_from("<IIII", data, b + 8)
        secs.append((name, vs, va, rs, pr))
    return imgbase, secs


def load_keys(paths):
    keys = set()
    for path in paths:
        if not os.path.exists(path):
            print(f"WARN: missing INI universe {path}", file=sys.stderr)
            continue
        for line in open(path, encoding="latin1"):
            m = re.match(r"\s*([A-Za-z][A-Za-z0-9._]*)\s*=", line)
            if m:
                keys.add(m.group(1))
    return keys


def classify(s, domains):
    if domains:
        return "tag"
    if FILE_EXT.search(s):
        return "file"
    if len(s) <= 4 and s.isupper():
        return "code"
    return "unclassified"


def main():
    data = open(EXE, "rb").read()
    imgbase, secs = parse_pe(data)
    text = [x for x in secs if x[0] == ".text"][0]
    tlo, thi = text[4], text[4] + text[3]

    def off2va(off):
        for n, vs, va, rs, pr in secs:
            if pr <= off < pr + rs:
                return imgbase + va + (off - pr)
        return None

    def va2off(v):
        r = v - imgbase
        for n, vs, va, rs, pr in secs:
            if va <= r < va + max(vs, rs):
                o = pr + (r - va)
                return o if o < len(data) else None
        return None

    # push imm32 index over .text
    push_index = defaultdict(list)
    off = tlo
    while off < thi - 5:
        if data[off] == 0x68:
            push_index[struct.unpack_from("<I", data, off + 1)[0]].append(off2va(off))
        off += 1

    # resolve each push target to an identifier string
    universes = {name: load_keys(p) for name, p in INI_UNIVERSES.items()}
    known_hooks = set()
    hp = os.path.join(REG, "hooks.json")
    if os.path.exists(hp):
        known_hooks = {int(a, 16) for a in json.load(open(hp))}

    def nearest_known(va, window=0x400):
        best = None
        for k in known_hooks:
            d = abs(k - va)
            if d <= window and (best is None or d < abs(best - va)):
                best = k
        return best

    surface = {}
    for tgt, sites in push_index.items():
        o = va2off(tgt)
        if o is None:
            continue
        end = data.find(b"\x00", o, o + 48)
        if end == -1:
            continue
        s = data[o:end].decode("latin1")
        if not IDENT.match(s):
            continue
        domains = sorted([name for name, keys in universes.items() if s in keys])
        sites_va = [hex(v) for v in sites if v]
        hints = {}
        for r in sites_va:
            nk = nearest_known(int(r, 16))
            if nk is not None:
                hints[r] = hex(nk)
        surface[s] = {
            "string": s,
            "kind": classify(s, domains),
            "domains": domains,
            "string_va": hex(tgt),
            "read_sites": sites_va,
            "near_known_hook": hints,
        }

    os.makedirs(REG, exist_ok=True)
    with open(os.path.join(REG, "engine-string-surface.json"), "w", encoding="utf-8") as fh:
        json.dump(surface, fh, indent=2)
        fh.write("\n")

    order = sorted(surface)
    with open(os.path.join(REG, "engine-string-surface.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["String", "Kind", "Domains", "ReadSites", "StringVA"])
        for s in order:
            v = surface[s]
            w.writerow([s, v["kind"], "|".join(v["domains"]), " ".join(v["read_sites"]), v["string_va"]])

    kinds = defaultdict(int)
    dom = defaultdict(int)
    for v in surface.values():
        kinds[v["kind"]] += 1
        for d in v["domains"]:
            dom[d] += 1
    unclassified = sorted(s for s, v in surface.items() if v["kind"] == "unclassified")

    with open(os.path.join(REG, "engine-string-surface.md"), "w", encoding="utf-8") as fh:
        fh.write("# Engine string-key surface (Phase E)\n\n")
        fh.write("_Auto-generated by `scripts/build_engine_string_surface.py` from "
                 f"`gamemd.exe` (imagebase {hex(imgbase)})._\n\n")
        fh.write("> ## ⚠ UNVERIFIED / HEURISTIC\n")
        fh.write("> Every identifier-string the engine **pushes** as a call argument, with the\n")
        fh.write("> code address(es) that read it. A read site is where a tag is *parsed* — a\n")
        fh.write("> candidate hook location, **not** proof of where its behaviour lives. Strings\n")
        fh.write("> are classed as `tag` (a key in an INI we checked), `file`, `code` (short\n")
        fh.write("> object id), or `unclassified` (identifier the engine reads but not in any INI\n")
        fh.write("> we have — a candidate *undocumented* tag, or an internal/section string).\n\n")
        fh.write(f"**{len(surface)}** pushed identifier strings. "
                 f"Kinds: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])) + ".\n\n")
        fh.write("Tag domains (a string may be in more than one): "
                 + ", ".join(f"{d} {n}" for d, n in sorted(dom.items(), key=lambda x: -x[1])) + ".\n\n")
        fh.write("Full data in `engine-string-surface.csv` / `.json`. Rules tags also have a "
                 "cleaner, cross-linked view in `vanilla-tags.md` (Phase D).\n\n")
        fh.write(f"## Unclassified — candidate undocumented tags ({len(unclassified)})\n\n")
        fh.write("_Identifier strings the engine reads that aren't a key in rules/art/ai here. "
                 "Some are internal strings or section names; some may be real, undocumented "
                 "tags worth probing. Read site(s) shown._\n\n")
        fh.write("| String | Read site(s) | Near known hook |\n|---|---|---|\n")
        for s in unclassified:
            v = surface[s]
            shown = " ".join(f"`{r}`" for r in v["read_sites"][:4]) or "—"
            if len(v["read_sites"]) > 4:
                shown += f" (+{len(v['read_sites']) - 4})"
            hint = " ".join(f"`{val}`" for val in list(v["near_known_hook"].values())[:2])
            fh.write(f"| `{s}` | {shown} | {hint} |\n")

    print(f"OK: {len(surface)} pushed identifier strings. Kinds: {dict(kinds)}")
    print(f"  tag domains: {dict(dom)}")
    print(f"  unclassified (candidate undocumented): {len(unclassified)}")


if __name__ == "__main__":
    main()
