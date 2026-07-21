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

import bisect
import csv
import glob
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
    # Tiberian Sun INIs — the base engine YR ultimately descends from. Split into the
    # base game (`ts`, v1.x) and the Firestorm expansion (`tsfs`, v2.00) because they
    # are distinct products: the FS-suffixed / numbered files (FIRESTRM, ARTFS, AIFS,
    # BATTLEFS, *01, MISSION1) are Firestorm ADDITIONS & CHANGES layered over base TS.
    # A string classed as `ts`/`tsfs` but not `ra2`/YR is the DEEPEST legacy: a TS-era
    # tag the YR engine still reads. `tsfs`-not-`ts` isolates Firestorm-introduced
    # tags (HunterSeeker, FirestormWall, EMPulseCannon, LaserFence, ...) from base-TS
    # ones. Cloned from Vinifera-Developers/Tiberian-Sun-INIs into the gitignored cache.
    "ts":      [f"{_TS}/{n}.INI" for n in
                ("RULES", "ART", "AI", "SOUND", "ION", "KEYBOARD", "MAPSEL", "MISSION",
                 "THEME", "TUTORIAL", "BATTLE", "NEWMENU", "SNOW", "TEMPERAT",
                 "DAY", "DUSK", "MORNING", "NIGHT")],
    "tsfs":    [f"{_TS}/{n}.INI" for n in
                ("FIRESTRM", "ARTFS", "AIFS", "BATTLEFS",
                 "MAPSEL01", "MISSION1", "SOUND01", "THEME01")],
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

# Some engine-read identifiers are fixed *section* names the engine iterates as a list
# (`[TaskForces]`/`[ScriptTypes]`/`[TeamTypes]` in AI INIs; `[CellTags]`/`[Waypoints]`/
# `[UnitActionLines]` in map/scenario files), not `key=` tags — so load_keys misses
# them. We index the section HEADERS of AI + map + mission INIs only (NOT rules/art,
# whose sections are the thousands of object IDs the engine never pushes as literals).
SECTION_UNIVERSES = {
    "ai":      [f"{_YR}/aimd.ini"],
    "mission": [f"{_YR}/missionmd.ini"],
    "ra2":     [f"{_RA2}/ai.ini"],
    "ts":      [f"{_TS}/AI.INI"],
    "tsfs":    [f"{_TS}/AIFS.INI"],
    "map":     INI_UNIVERSES["map"],
}

FILE_EXT = re.compile(r"\.(INI|MIX|PAL|SHP|VXL|HVA|PCX|WAV|AUD|CSF|BAG|IDX|TXT|BIN|MAP|PKT|"
                      r"TMP|DLL|EXE|FNT|DAT|VPL|IMG|SED|KEY|NET|BMP|HLP|YRO|PKG|MMX|MPR|YRM)$", re.I)
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9._]{2,39}$")
# Extra shape heuristics used to split the "no INI match" leftovers (see classify()).
FILE_DOTTED = re.compile(r"^[A-Za-z0-9]+(\.[A-Za-z0-9]*)+$")     # WW.TiberianSun, Bootstrap.....
FUNCLIKE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]*)+$")  # Dial_Modem, Ra2ts_s, Lob_41_
TAGSHAPE = re.compile(r"^[A-Z][A-Za-z0-9]{2,}$")                  # CamelCase engine key (Rotors, ActiveAnimTwoX)


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


def load_sections(paths):
    """Section HEADERS (`[Name]`) — for the fixed list-sections the engine reads as
    literals (`[TaskForces]`, `[Waypoints]`, ...). Only used for AI/map/mission files,
    never rules/art (whose sections are the thousands of object IDs)."""
    names = set()
    for path in paths:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="latin1"):
            m = re.match(r"\s*\[([A-Za-z][A-Za-z0-9._]*)\]", line)
            if m:
                names.add(m.group(1))
    return names


def load_modenc():
    """ModEnc-derived facts per tag (built by scripts/fetch_modenc.py). {} if absent."""
    path = os.path.join(ROOT, "sources", "modenc-cache.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def framework_literals():
    """Quoted string literals in each cloned framework's C++ source (sources/repos/,
    gitignored). Lets us corroborate that an engine string is a real tag some framework
    also reads/extends, and attribute WHO. {} if the clones aren't present."""
    root = os.path.join(ROOT, "sources", "repos")
    if not os.path.isdir(root):
        return {}
    lit = re.compile(r'"([A-Za-z][A-Za-z0-9._]{2,39})"')
    out = {}
    for fw in sorted(os.listdir(root)):
        base = os.path.join(root, fw)
        if not os.path.isdir(base):
            continue
        seen = set()
        for ext in ("cpp", "h", "hpp", "cc"):
            for f in glob.glob(f"{base}/**/*.{ext}", recursive=True):
                try:
                    seen.update(lit.findall(open(f, encoding="latin1").read()))
                except OSError:
                    pass
        out[fw] = seen
    return out


def classify(s, domains):
    """Bucket a pushed engine string.
      tag          - a key/section in an INI we have (named, with domain)
      tag-unlisted - CamelCase engine key shape, but in no INI we have (unnamed tag)
      file         - a filename / dotted resource name
      code         - internal identifier: type/enum/UI id, function or debug string
      unclassified - genuinely ambiguous leftover
    """
    if domains:
        return "tag"
    core = s.rstrip("\n")
    if core != s:                       # embedded newline => internal/debug string
        return "code"
    if FILE_EXT.search(core) or FILE_DOTTED.match(core):
        return "file"
    if FUNCLIKE.match(core):            # Word_Word / Lob_41_ => function or debug label
        return "code"
    if core.isupper():                  # AIRCRAFT, FACTORY, CLSID => RTTI/abstract type, UI id
        return "code"
    if core.islower():                  # none, yes, false, standard => value literal
        return "code"
    if TAGSHAPE.match(core):            # real engine key vanilla content just never sets
        return "tag-unlisted"
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
    for name, paths in SECTION_UNIVERSES.items():
        universes.setdefault(name, set()).update(load_sections(paths))
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

    # ---- domain inference for `tag-unlisted` by read-site consensus --------------
    # Tags in one INI section are parsed by the same engine loader, so their read
    # sites cluster in one code region. For a tag-unlisted string, look at the
    # single-domain KNOWN tags whose read sites fall within DGWIN bytes of its read
    # site: if they UNANIMOUSLY belong to one domain, that's a strong domain guess;
    # if they disagree (interleaved loaders), we ABSTAIN rather than mislabel.
    # Leave-one-out on the known tags gives ~100% precision at this window (art
    # 13/13, rules 206/206) at ~19% coverage — accurate where it commits, honest
    # where it can't. This is a HINT (kept separate from `domains`), not a fact.
    DGWIN = 128
    DG_DOMS = {"rules", "art", "ai", "sound", "theme", "eva", "mapsel", "battle",
               "mission", "rmg", "theater", "coop"}
    pool = []  # (addr, domain, owner_string) from unambiguous single-domain tags
    for name, v in surface.items():
        if v["kind"] == "tag" and len(v["domains"]) == 1 and v["domains"][0] in DG_DOMS:
            for a in v["read_sites"]:
                pool.append((int(a, 16), v["domains"][0], name))
    pool.sort()
    pool_addrs = [p[0] for p in pool]

    def domain_consensus(addr):
        lo = bisect.bisect_left(pool_addrs, addr - DGWIN)
        hi = bisect.bisect_right(pool_addrs, addr + DGWIN)
        best = {}
        for j in range(lo, hi):
            a, dm, owner = pool[j]
            dist = abs(a - addr)
            if dm not in best or dist < best[dm][0]:
                best[dm] = (dist, owner)
        if len(best) == 1:
            dm, (dist, owner) = next(iter(best.items()))
            return dm, dist, owner
        return None, None, None

    for name, v in surface.items():
        if v["kind"] != "tag-unlisted" or not v["read_sites"]:
            continue
        guesses = {domain_consensus(int(a, 16))[0] for a in v["read_sites"]}
        guesses.discard(None)
        if len(guesses) == 1:                       # every read site agrees (or only one)
            dm, dist, owner = domain_consensus(int(v["read_sites"][0], 16))
            # recompute closest supporting evidence across all read sites
            ev = min((domain_consensus(int(a, 16))[1:] for a in v["read_sites"]
                      if domain_consensus(int(a, 16))[0] == dm), key=lambda t: t[0])
            v["domain_guess"] = dm
            v["domain_guess_via"] = ev[1]
            v["domain_guess_dist"] = ev[0]

    # ---- provenance: attach every INDEPENDENT domain claim per string ---------------
    # A string can carry a domain opinion from several methods of DIFFERENT reliability.
    # We record ALL of them, each tagged with how it was obtained, and DO NOT pick a
    # favourite — until someone verifies experimentally, competing documented claims
    # are shown side by side. `domain_claims` is the full list; `domain_conflict` just
    # marks where two claims disagree (so it's easy to find), without resolving it.
    #   ini-direct        (certain)     : the string is literally a key/section in an INI.
    #   modenc            (documented)  : ModEnc community wiki; human-curated; cites URL.
    #   readsite-consensus(inferred)    : our binary read-site clustering heuristic.
    #   framework-source  (corroboration): a framework's C++ references the literal.
    modenc = load_modenc()
    fwlits = framework_literals()
    for s, v in surface.items():
        fws = sorted(fw for fw, lits in fwlits.items() if s in lits)
        if fws:
            v["frameworks"] = fws                       # who else reads/extends this tag
        me = modenc.get(s)
        if me and me.get("flag"):
            v["modenc"] = {"ini": me.get("ini", []), "types": me.get("types", []),
                           "status": me.get("status", []), "games": me.get("games", []),
                           "url": me.get("url")}
        elif me and me.get("present") is False:
            v["modenc"] = {"missing": True, "url": me.get("url")}  # no ModEnc page exists
        # collect every method's domain claim — no ranking, no winner
        claims = []
        if v["domains"]:
            claims.append({"source": "ini-direct", "domain": list(v["domains"])})
        if me and me.get("flag") and me.get("ini"):
            claims.append({"source": "modenc", "domain": list(me["ini"])})
        if v.get("domain_guess"):
            claims.append({"source": "readsite-consensus", "domain": [v["domain_guess"]]})
        if claims:
            v["domain_claims"] = claims
            v["domain_sources"] = [c["source"] for c in claims]  # methods with an opinion
        # flag (don't resolve) where two claims name different domains
        distinct = {d for c in claims for d in c["domain"]}
        if len(claims) > 1 and len(distinct) > 1:
            v["domain_conflict"] = {c["source"]: c["domain"] for c in claims}

    os.makedirs(REG, exist_ok=True)
    with open(os.path.join(REG, "engine-string-surface.json"), "w", encoding="utf-8") as fh:
        json.dump(surface, fh, indent=2)
        fh.write("\n")

    order = sorted(surface)
    with open(os.path.join(REG, "engine-string-surface.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["String", "Kind", "Domains", "DomainSources", "DomainGuess", "GuessVia",
                    "GuessDist", "ModEncINI", "ModEncTypes", "ModEncStatus", "Conflict",
                    "Frameworks", "ModEncURL", "ReadSites", "StringVA"])
        for s in order:
            v = surface[s]
            me = v.get("modenc") or {}
            conf = v.get("domain_conflict")
            w.writerow([
                s, v["kind"], "|".join(v["domains"]), "|".join(v.get("domain_sources", [])),
                v.get("domain_guess", ""), v.get("domain_guess_via", ""),
                v.get("domain_guess_dist", ""), "|".join(me.get("ini", [])),
                "|".join(me.get("types", [])), "|".join(me.get("status", [])),
                ("; ".join(f"{src}={'/'.join(dm)}" for src, dm in conf.items()) if conf else ""),
                "|".join(v.get("frameworks", [])), me.get("url", ""),
                " ".join(v["read_sites"]), v["string_va"]])

    kinds = defaultdict(int)
    dom = defaultdict(int)
    for v in surface.values():
        kinds[v["kind"]] += 1
        for d in v["domains"]:
            dom[d] += 1
    tag_unlisted = sorted(s for s, v in surface.items() if v["kind"] == "tag-unlisted")
    unclassified = sorted(s for s, v in surface.items() if v["kind"] == "unclassified")

    def sites_cell(v):
        shown = " ".join(f"`{r}`" for r in v["read_sites"][:3]) or "—"
        if len(v["read_sites"]) > 3:
            shown += f" (+{len(v['read_sites']) - 3})"
        return shown

    def write_table(fh, rows):
        fh.write("| String | Read site(s) | Near known hook |\n|---|---|---|\n")
        for s in rows:
            v = surface[s]
            hint = " ".join(f"`{val}`" for val in list(v["near_known_hook"].values())[:2])
            fh.write(f"| `{s}` | {sites_cell(v)} | {hint} |\n")

    def write_unlisted_table(fh, rows):
        # Every source's domain claim shown SIDE BY SIDE — no winner is chosen. The
        # `≟` column marks where two claims disagree (a lead to verify), not a verdict.
        fh.write("| String | ModEnc domain | read-site domain | ≟ | ModEnc page | Read site(s) |\n"
                 "|---|---|---|---|---|---|\n")
        for s in rows:
            v = surface[s]
            me = v.get("modenc") or {}
            me_dom = "/".join(me.get("ini", [])) if me.get("ini") else "—"
            rs_dom = v.get("domain_guess") or "—"
            if me.get("ini") and v.get("domain_guess"):
                flag = "✓" if v["domain_guess"] in me["ini"] else "⚠"
            else:
                flag = ""
            rs_cell = (f"{rs_dom} (±{v['domain_guess_dist']}b via `{v['domain_guess_via']}`)"
                       if v.get("domain_guess") else "—")
            if me.get("missing"):
                me_cell = f"[no page]({me['url']})"
            elif me:
                bits = []
                if me.get("types"):
                    bits.append(", ".join(me["types"]))
                if me.get("status"):
                    bits.append("*" + "; ".join(me["status"]) + "*")
                me_cell = f"[{' — '.join(bits) or 'documented'}]({me['url']})"
            else:
                me_cell = "—"
            fh.write(f"| `{s}` | {me_dom} | {rs_cell} | {flag} | {me_cell} | {sites_cell(v)} |\n")

    with open(os.path.join(REG, "engine-string-surface.md"), "w", encoding="utf-8") as fh:
        fh.write("# Engine string-key surface (Phase E)\n\n")
        fh.write("_Auto-generated by `scripts/build_engine_string_surface.py` from "
                 f"`gamemd.exe` (imagebase {hex(imgbase)})._\n\n")
        fh.write("> ## ⚠ UNVERIFIED / HEURISTIC\n")
        fh.write("> Every identifier-string the engine **pushes** as a call argument, with the\n")
        fh.write("> code address(es) that read it. A read site is where a tag is *parsed* — a\n")
        fh.write("> candidate hook location, **not** proof of where its behaviour lives. Strings\n")
        fh.write("> are classed as:\n")
        fh.write("> - `tag` — a key (or list-section) in an INI we checked; has a domain.\n")
        fh.write("> - `tag-unlisted` — CamelCase engine-key shape, read by the binary, but in\n")
        fh.write(">   **no** INI we have. These are real engine tags vanilla content never sets\n")
        fh.write(">   (rare/defaulted rules & art keys) — the richest lead-list of *undocumented* tags.\n")
        fh.write("> - `file` — a filename / dotted resource name.\n")
        fh.write("> - `code` — an internal identifier: RTTI/abstract type, UI id, value literal,\n")
        fh.write(">   or a function/debug string. Not a tag.\n")
        fh.write("> - `unclassified` — genuinely ambiguous leftover (small residual).\n\n")
        fh.write(f"**{len(surface)}** pushed identifier strings. "
                 f"Kinds: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])) + ".\n\n")
        fh.write("Tag domains (a string may be in more than one): "
                 + ", ".join(f"{d} {n}" for d, n in sorted(dom.items(), key=lambda x: -x[1])) + ".\n\n")
        fh.write("Full data in `engine-string-surface.csv` / `.json`. Rules tags also have a "
                 "cleaner, cross-linked view in `vanilla-tags.md` (Phase D).\n\n")

        # -- provenance summary: every method's claim is shown; none is anointed --------
        n_sourced = sum(1 for s in tag_unlisted if surface[s].get("domain_sources"))
        src_count = defaultdict(int)
        for s in tag_unlisted:
            for src in surface[s].get("domain_sources", []):
                src_count[src] += 1
        me_named = sum(1 for s in tag_unlisted if (surface[s].get("modenc") or {}).get("ini"))
        conflicts = sorted(s for s in tag_unlisted if surface[s].get("domain_conflict"))
        fw_any = sum(1 for v in surface.values() if v.get("frameworks"))
        fh.write("## How to read this — provenance, not verdicts\n\n")
        fh.write("Each domain claim below is tagged with **how it was obtained**. We deliberately "
                 "**do not pick a favourite** between competing claims — until someone verifies a "
                 "tag experimentally, every documented claim is shown side by side so you can weigh "
                 "them and reconcile them against your own findings. The methods, and what each is "
                 "worth knowing:\n\n")
        fh.write("| Source | What it means | Nature of the evidence |\n|---|---|---|\n")
        fh.write("| `ini-direct` | The string is literally a key/section in a vanilla INI we parsed. | A fact — it is that key. |\n")
        fh.write("| `modenc` | Documented on the [ModEnc](https://modenc.renegadeprojects.com) community wiki; we parsed its `{{flag}}` `files=` field. Cites the page URL. | Human-curated, but a wiki: can be wrong, dated, or contested. |\n")
        fh.write("| `readsite-consensus` | Inferred from the binary: the known tags whose read sites cluster within "
                 f"±{DGWIN} bytes of this tag's read site **unanimously** share a domain. | A heuristic. ~100% on leave-one-out, but with real misses where art/rules loaders interleave. |\n")
        fh.write("| `framework-source` | The literal appears in a framework's C++ source. | Corroboration it's a real tag, and *who* reads it — not evidence of domain. |\n\n")
        fh.write("Where two claims **disagree**, both are kept and the row is marked ⚠ in the `≟` "
                 "column. That is a *flag for someone to test*, not a ruling in ModEnc's or the "
                 "heuristic's favour.\n\n")

        fh.write(f"## Unnamed engine tags — `tag-unlisted` ({len(tag_unlisted)})\n\n")
        fh.write("_CamelCase keys the binary reads that appear in **no** INI we have — real "
                 "engine tags vanilla content never sets. The best lead-list of undocumented tags._\n\n")
        fh.write(f"**{n_sourced}/{len(tag_unlisted)}** have at least one domain claim "
                 + "(" + ", ".join(f"`{k}` {n}" for k, n in sorted(src_count.items(), key=lambda x: -x[1])) + ")"
                 + f"; **{me_named}** are documented on ModEnc. "
                 f"**{len(conflicts)}** have claims that disagree (marked ⚠ below). "
                 f"(Run `scripts/fetch_modenc.py` to widen ModEnc coverage.)\n\n")
        if conflicts:
            fh.write(f"### ⚠ Disagreements — competing claims to test ({len(conflicts)})\n\n")
            fh.write("_The methods name different domains here. Both are shown; neither is chosen. "
                     "Prime candidates for hands-on verification._\n\n")
            fh.write("| String | Claims | ModEnc page |\n|---|---|---|\n")
            for s in conflicts:
                c = surface[s]["domain_conflict"]
                me = surface[s].get("modenc") or {}
                claim_str = ", ".join(f"`{'/'.join(dm)}` ({src})" for src, dm in c.items())
                fh.write(f"| `{s}` | {claim_str} | [page]({me.get('url','')}) |\n")
            fh.write("\n")
        write_unlisted_table(fh, tag_unlisted)
        if unclassified:
            fh.write(f"\n## Unclassified — ambiguous residual ({len(unclassified)})\n\n")
            fh.write("_Leftovers that fit neither a tag, file, nor code shape. Probe individually._\n\n")
            write_table(fh, unclassified)

    print(f"OK: {len(surface)} pushed identifier strings. Kinds: {dict(kinds)}")
    print(f"  tag domains: {dict(dom)}")
    print(f"  tag-unlisted: {len(tag_unlisted)}; with >=1 domain claim: {n_sourced} "
          f"({dict(src_count)}); ModEnc-named {me_named}; disagreements {len(conflicts)}")
    print(f"  strings with framework-source corroboration: {fw_any}")
    print(f"  unclassified (ambiguous residual): {len(unclassified)}")


if __name__ == "__main__":
    main()
