#!/usr/bin/env python3
"""
build_tag_index.py — Phase C: framework INI-tag -> candidate-hook cross-reference.

For every INI tag a framework ADDS (parsed in its own source), this records where
the tag is read and a HEURISTIC shortlist of the hooks most likely to implement it.
The point is triage, not proof: "the hook you want is probably one of these N,"
which beats trial-and-error from a blank slate.

*** EVERYTHING HERE IS UNVERIFIED / HEURISTIC. ***
The tag->hook links are inferred from source structure, not confirmed by reading
each function. Two link bases, strongest first:
  member-referenced : the field the tag is parsed into (e.g. `ShieldType`) textually
                      appears in this hooked function's source file. Fairly strong.
  same-subsystem    : fallback — a hook in the same Ext family as the parse site.
                      Weak; a wide net.
Vanilla (non-framework) tags are NOT covered here — that's Phase D (Ghidra).

Inputs : cloned repos under sources/repos/ (via update_repos.sh) + registry/hooks.json.
Outputs: registry/tags.csv, registry/tag-hooks.json, registry/tag-hooks.md.
"""

import csv
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")
REPOS = os.path.join(ROOT, "sources", "repos")
HOOKS_JSON = os.path.join(REG, "hooks.json")

FRAMEWORKS = ["Ares", "Antares", "Phobos", "Kratos", "AggressiveStance"]

# Parse-site patterns. Each yields (member_or_None, tag). Applied per line, first hit wins.
PATS = [
    # typed:  this->Foo.Read(exINI, section, "Tag")  /  Foo.Read<..>(exINI, pSection, "Tag")
    re.compile(r'(?:this->)?(\w+)\s*\.\s*(?:Read|Parse)\s*(?:<[^>]*>)?\s*\(\s*(?:exINI|pINI|ini|reader)\b[^;]*?"([A-Za-z][\w.]*)"'),
    # kratos:  member = reader->Get*( [TITLE +] "Tag" )
    re.compile(r'(\w+)\s*=\s*reader->Get\w*\(\s*(?:[A-Za-z_]\w*\s*\+\s*)?"([A-Za-z][\w.]*)"'),
    # raw CCINI with LHS:  member = pINI->ReadBool(section, "Tag")
    re.compile(r'(\w+)\s*=\s*\w+->(?:Read|Get)\w+\(\s*[^,]+,\s*"([A-Za-z][\w.]*)"'),
    # raw CCINI no LHS:  ->ReadString(section, "Tag")
    re.compile(r'->(?:Read|Get)\w+\(\s*[^,]+,\s*"([A-Za-z][\w.]*)"'),
]

# tokens that are members-in-name-only but far too generic to link on
GENERIC_MEMBERS = {"value", "buffer", "ret", "result", "tmp", "str", "name", "type", "data", "flag"}

# Lifecycle / storage / serialization hooks. They reference every member of their
# Ext (allocate/load/save it), so they match every tag and tell you nothing about
# what a tag DOES. Excluded from candidate behaviour-hook lists.
BOILERPLATE_RE = re.compile(
    r"(_CTOR|_DTOR|LoadFromINI|ReadFromINI|WriteToINI|_Load(_|$|Suffix|Prefix)|_Save|SaveLoad"
    r"|Serialize|Constructor|Destructor|Detach|InvalidatePointer|_Init(_|$)|ExtMap|Container)",
    re.IGNORECASE,
)
BROAD_THRESHOLD = 40  # more candidates than this = flagged "broad" (weak shortlist)


def is_boilerplate(fn):
    return bool(BOILERPLATE_RE.search(fn))


def norm_addr(a):
    return a


def subsystem_family(sub):
    """Ext/TechnoType <-> Ext/Techno etc. Return the set of related subsystem strings."""
    fam = {sub}
    if sub.endswith("Type"):
        fam.add(sub[:-4])
    else:
        fam.add(sub + "Type")
    return fam


def extract_tag(line):
    for i, pat in enumerate(PATS):
        m = pat.search(line)
        if not m:
            continue
        if pat.groups == 2 or len(m.groups()) == 2:
            return m.group(1), m.group(2)
        return None, m.group(1)
    return None


def main():
    hooks = json.load(open(HOOKS_JSON, encoding="utf-8"))

    # Per-framework hook inventory: file -> [ (address, function) ], and hook->subsystem.
    fw_file_hooks = defaultdict(lambda: defaultdict(list))
    hook_meta = {}  # (fw, address, function) -> subsystem
    for addr, v in hooks.items():
        for c in v["consumers"]:
            if c["channel"] != "release":
                continue
            fw = c["framework"]
            sf = c.get("source_file", "")
            fw_file_hooks[fw][sf].append((addr, c["function"]))
            hook_meta[(fw, addr, c["function"])] = c.get("subsystem", "?")

    # Precompute identifier sets for each framework hook file (for member-reference test).
    file_idents = {}      # (fw, relfile) -> set(identifiers)
    for fw in FRAMEWORKS:
        src = os.path.join(REPOS, fw, "src")
        for sf in fw_file_hooks[fw]:
            full = os.path.join(REPOS, fw, sf)  # sf already begins "src/"
            try:
                text = open(full, encoding="utf-8", errors="replace").read()
            except OSError:
                file_idents[(fw, sf)] = set()
                continue
            file_idents[(fw, sf)] = set(re.findall(r"[A-Za-z_]\w+", text))

    # Extract parse sites.
    tags = {}  # (fw, tag) -> {"members": set, "sites": [(file,line)], "subsys": set}
    for fw in FRAMEWORKS:
        src = os.path.join(REPOS, fw, "src")
        if not os.path.isdir(src):
            continue
        for dp, _, files in os.walk(src):
            for f in files:
                if not f.endswith((".cpp", ".h")):
                    continue
                full = os.path.join(dp, f)
                rel = "src/" + os.path.relpath(full, src).replace(os.sep, "/")
                subsys = os.path.dirname(os.path.relpath(full, src)).replace(os.sep, "/") or "."
                for ln, line in enumerate(open(full, encoding="utf-8", errors="replace"), 1):
                    if "#define" in line:
                        continue
                    res = extract_tag(line)
                    if not res:
                        continue
                    member, tag = res
                    key = (fw, tag)
                    e = tags.setdefault(key, {"members": set(), "sites": [], "subsys": set()})
                    if member and member.lower() not in GENERIC_MEMBERS:
                        e["members"].add(member)
                    e["sites"].append((rel, ln))
                    e["subsys"].add(subsys)

    # Link each tag to candidate hooks.
    out = {}
    for (fw, tag), e in tags.items():
        members = e["members"]
        # member-referenced hooks
        member_hooks = []
        if members:
            for sf, hlist in fw_file_hooks[fw].items():
                idents = file_idents.get((fw, sf), set())
                if idents & members:
                    for addr, fn in hlist:
                        if is_boilerplate(fn):
                            continue
                        member_hooks.append((addr, fn, "member-referenced"))
        # same-subsystem fallback
        fam = set()
        for s in e["subsys"]:
            fam |= subsystem_family(s)
        subsys_hooks = []
        member_addrs = {a for a, _, _ in member_hooks}
        for (mfw, addr, fn), sub in hook_meta.items():
            if mfw != fw:
                continue
            if is_boilerplate(fn):
                continue
            if sub in fam and addr not in member_addrs:
                subsys_hooks.append((addr, fn, "same-subsystem"))

        cands = member_hooks[:]
        # only add subsystem fallback when member linkage is empty or very small
        if len(member_hooks) < 3:
            cands += subsys_hooks
        # dedupe, sort by address
        seen = set()
        uniq = []
        for a, fn, basis in cands:
            if (a, fn) in seen:
                continue
            seen.add((a, fn))
            uniq.append({"address": a, "function": fn, "basis": basis})
        uniq.sort(key=lambda c: int(c["address"], 16))

        if member_hooks:
            conf = "member-referenced-broad" if len(uniq) > BROAD_THRESHOLD else "member-referenced"
        elif uniq:
            conf = "same-subsystem-broad" if len(uniq) > BROAD_THRESHOLD else "same-subsystem"
        else:
            conf = "no-candidate"
        out[f"{fw}::{tag}"] = {
            "framework": fw,
            "tag": tag,
            "members": sorted(members),
            "parse_sites": [f"{p}:{l}" for p, l in e["sites"]],
            "confidence": conf,
            "candidate_count": len(uniq),
            # addresses only — resolve function names via registry/hooks.json
            "candidates": [c["address"] for c in uniq],
        }
        # keep the richer form around for the .md renderer below
        out[f"{fw}::{tag}"]["_rich"] = uniq

    os.makedirs(REG, exist_ok=True)

    # tags.csv — the confirmed parse facts
    with open(os.path.join(REG, "tags.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Framework", "Tag", "Members", "Confidence", "CandidateHooks", "ParseSites"])
        for k in sorted(out, key=lambda k: (out[k]["framework"], out[k]["tag"].lower())):
            v = out[k]
            w.writerow([v["framework"], v["tag"], ";".join(v["members"]),
                        v["confidence"], v["candidate_count"], " ; ".join(v["parse_sites"][:6])])

    slim = {k: {kk: vv for kk, vv in v.items() if kk != "_rich"} for k, v in out.items()}
    with open(os.path.join(REG, "tag-hooks.json"), "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
        fh.write("\n")

    # tag-hooks.md — readable, with a loud UNVERIFIED banner
    per_fw = defaultdict(list)
    for k, v in out.items():
        per_fw[v["framework"]].append(v)
    conf_counts = defaultdict(int)
    for v in out.values():
        conf_counts[v["confidence"]] += 1
    with open(os.path.join(REG, "tag-hooks.md"), "w", encoding="utf-8") as fh:
        fh.write("# Tag → candidate-hook index (Phase C: framework tags)\n\n")
        fh.write("_Auto-generated by `scripts/build_tag_index.py`._\n\n")
        fh.write("> ## ⚠ UNVERIFIED / HEURISTIC — read this first\n")
        fh.write("> These tag→hook links are **inferred from source structure, not confirmed.**\n")
        fh.write("> They are a **triage shortlist** to narrow trial-and-error, not ground truth.\n")
        fh.write("> - **member-referenced**: the parsed field's name appears in the hook's source\n")
        fh.write(">   file. Fairly strong, but \"appears in the same file\" ≠ \"is this hook.\"\n")
        fh.write("> - **same-subsystem**: a hook in the same Ext family as the parse site. A wide net.\n")
        fh.write("> The one thing here that IS confirmed is the **parse site** (where the tag is read).\n")
        fh.write("> Vanilla (non-framework) tags are out of scope — see Phase D (Ghidra).\n\n")
        total = len(out)
        fh.write(f"**{total}** framework tags. Confidence: " +
                 ", ".join(f"{c} {n}" for c, n in sorted(conf_counts.items(), key=lambda x: -x[1])) + ".\n\n")
        for fw in FRAMEWORKS:
            rows = per_fw.get(fw, [])
            if not rows:
                continue
            fh.write(f"## {fw} — {len(rows)} tags\n\n")
            fh.write("| Tag | Conf | Parsed in | Candidate hooks (address · function) |\n|---|---|---|---|\n")
            for v in sorted(rows, key=lambda v: v["tag"].lower()):
                site = v["parse_sites"][0] if v["parse_sites"] else "?"
                site = site.replace("src/", "")
                cnd = v["_rich"]
                shown = " ".join(f"`{c['address']}`" for c in cnd[:6])
                if len(cnd) > 6:
                    shown += f" (+{len(cnd) - 6})"
                if not cnd:
                    shown = "—"
                fh.write(f"| `{v['tag']}` | {v['confidence'].split('-')[0]} | `{site}` | {shown} |\n")
            fh.write("\n")

    print(f"OK: {total} framework tags indexed. Confidence: {dict(conf_counts)}")


if __name__ == "__main__":
    main()
