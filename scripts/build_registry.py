#!/usr/bin/env python3
"""
build_registry.py — Tier 1 registry builder for the YR Hook Encyclopedia.

Merges every known gamemd.exe hook into a single address-keyed registry. The
address is the primary key: when two frameworks hook the same address in their
shipped (release) code, that is a real compatibility conflict, and this script
makes it visible.

Two channels per hook consumer:
  release   the hook is in the framework's mainline source (a cloned upstream repo)
  PR#NNNN   the hook only exists in an unmerged pull request (a "loose" hook)

Sources:
  release  extracted live from the cloned repos under ../sources/repos/<Framework>/
           (run scripts/update_repos.sh to clone/update them).
  PRs      read from ../sources/pr_hooks.json, produced by scripts/fetch_pr_hooks.py.

Outputs (../registry/):
  hooks.csv        One row per (address, framework, channel) consumer.
  hooks.json       Address-keyed; each address lists every consumer.
  conflicts.md     Auto: addresses hooked by 2+ frameworks in the RELEASE channel.
  pr-hooks.md      Auto: loose hooks grouped by framework then PR (with links).
  STATS.md         Auto: counts.
  PROVENANCE.md    Auto: the exact upstream commit each framework was read from.

Nothing here is project-specific; only public frameworks are included.
"""

import csv
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")
REPOS = os.path.join(ROOT, "sources", "repos")
PR_JSON = os.path.join(ROOT, "sources", "pr_hooks.json")

# Frameworks whose release hooks come from a cloned upstream repo.
# Order = display priority. Each has a src/ subdir under sources/repos/<name>/.
# AggressiveStance is a small standalone Syringe DLL (loads alongside Ares/Phobos;
# co-loadable with everything, so not in any exclusive group).
# CnCNet-Spawner is CnCNet's online spawner DLL (repo `CnCNet/yrpp-spawner`): a
# Syringe DLL built on the same YRpp framework, so it co-loads like Phobos — its
# hooks are the network/online layer (spawn.ini launch, netcode, online QoL/balance).
FRAMEWORKS = ["Ares", "Antares", "Phobos", "Kratos", "AggressiveStance", "CnCNet-Spawner"]

# Mutually-exclusive frameworks: you load at most ONE from each group at a time,
# so two of them hooking the same address is NOT a real conflict — it's usually
# inherited code. Antares is a continuation of Ares; you run one or the other
# (Ares.dll must be removed to run Antares). Everything else co-loads.
EXCLUSIVE_GROUPS = [{"Ares", "Antares"}]


def co_loadable(a, b):
    """True if frameworks a and b can be loaded at the same time."""
    return not any(a in g and b in g for g in EXCLUSIVE_GROUPS)


def is_real_conflict(frameworks):
    """A real conflict needs two co-loadable frameworks at the same address."""
    fw = list(frameworks)
    return any(co_loadable(fw[i], fw[k]) for i in range(len(fw)) for k in range(i + 1, len(fw)))

# Handles BOTH dialects: Ares/Antares write the address and size as bare hex
# (DEFINE_HOOK(47AE36, Name, 8)); Phobos/Kratos prefix 0x (DEFINE_HOOK(0x..., Name, 0x8)).
# Everything is parsed as hex.
HOOK_RE = re.compile(
    r"DEFINE_HOOK(?:_AGAIN)?\s*\(\s*(?:0x)?([0-9A-Fa-f]+)\s*,\s*([A-Za-z_]\w*)\s*,\s*(?:0x)?([0-9A-Fa-f]+)"
)


def norm_addr(hexdigits):
    return "0x" + hexdigits.upper().lstrip("0").rjust(1, "0")


def git_head(repo):
    try:
        sha = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        date = subprocess.check_output(
            ["git", "-C", repo, "log", "-1", "--format=%cs"], text=True
        ).strip()
        return sha, date
    except Exception:
        return "?", "?"


def subsystem_for(rel):
    """rel is path under the repo's src/. Use its directory as the subsystem."""
    d = os.path.dirname(rel)
    return d.replace(os.sep, "/") if d else "."


def load_release(rows, provenance):
    for fw in FRAMEWORKS:
        repo = os.path.join(REPOS, fw)
        src = os.path.join(repo, "src")
        if not os.path.isdir(src):
            print(f"WARN: missing repo src for {fw}: {src}", file=sys.stderr)
            continue
        sha, date = git_head(repo)
        provenance.append((fw, sha, date))
        for dp, _, files in os.walk(src):
            for f in files:
                if not f.endswith((".cpp", ".h")):
                    continue
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, src)
                text = open(full, encoding="utf-8", errors="replace").read()
                for line in text.splitlines():
                    if "#define" in line:  # skip the macro definition itself
                        continue
                    for m in HOOK_RE.finditer(line):
                        rows.append({
                            "address": norm_addr(m.group(1)),
                            "framework": fw,
                            "channel": "release",
                            "function": m.group(2),
                            "stolen_bytes": int(m.group(3), 16),
                            "subsystem": subsystem_for(rel),
                            "source_file": "src/" + rel.replace(os.sep, "/"),
                        })


def load_prs(rows):
    if not os.path.exists(PR_JSON):
        print(f"note: no PR data yet ({PR_JSON}); run scripts/fetch_pr_hooks.py", file=sys.stderr)
        return
    data = json.load(open(PR_JSON, encoding="utf-8"))
    for h in data.get("hooks", []):
        rows.append({
            "address": norm_addr(h["address"].lower().replace("0x", "")),
            "framework": h["framework"],
            "channel": "PR#%s" % h["pr"],
            "function": h["function"],
            "stolen_bytes": int(str(h["stolen_bytes"]).replace("0x", ""), 16) if h.get("stolen_bytes") not in (None, "") else None,
            "subsystem": h.get("subsystem", "?"),
            "source_file": h.get("source_file", "?"),
            "pr_title": h.get("pr_title", ""),
            "pr_author": h.get("pr_author", ""),
            "pr_url": h.get("pr_url", ""),
        })


def addr_key(a):
    return int(a, 16)


def sb_str(v):
    return "" if v is None else "0x%X" % v


def main():
    rows, provenance = [], []
    load_release(rows, provenance)
    load_prs(rows)

    # Dedupe identical consumer rows.
    seen, uniq = set(), []
    for r in rows:
        k = (r["address"], r["framework"], r["channel"], r["function"], r["source_file"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    rows = uniq
    rows.sort(key=lambda r: (addr_key(r["address"]), r["channel"] != "release", r["framework"], r["function"]))

    os.makedirs(REG, exist_ok=True)

    # hooks.csv
    with open(os.path.join(REG, "hooks.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Address", "Framework", "Channel", "Function", "StolenBytes", "Subsystem", "SourceFile"])
        for r in rows:
            w.writerow([r["address"], r["framework"], r["channel"], r["function"],
                        sb_str(r["stolen_bytes"]), r["subsystem"], r["source_file"]])

    # hooks.json (address-keyed)
    by_addr = defaultdict(list)
    for r in rows:
        by_addr[r["address"]].append(r)
    j = {}
    for addr in sorted(by_addr, key=addr_key):
        cons = by_addr[addr]
        rel_fw = sorted({c["framework"] for c in cons if c["channel"] == "release"})
        pr_fw = sorted({c["framework"] for c in cons if c["channel"] != "release"})
        j[addr] = {
            "release_frameworks": rel_fw,
            "pr_frameworks": pr_fw,
            "release_shared": len(rel_fw) > 1,
            "real_conflict": len(rel_fw) > 1 and is_real_conflict(rel_fw),
            "consumers": [
                {k: (sb_str(c["stolen_bytes"]) if k == "stolen_bytes" else c.get(k))
                 for k in ("framework", "channel", "function", "stolen_bytes",
                           "subsystem", "source_file", "pr_title", "pr_author", "pr_url")
                 if c.get(k) not in (None, "")}
                for c in cons
            ],
        }
    with open(os.path.join(REG, "hooks.json"), "w", encoding="utf-8") as fh:
        json.dump(j, fh, indent=2)
        fh.write("\n")

    # conflicts.md — RELEASE-channel collisions between CO-LOADABLE frameworks
    conflicts = [(a, v) for a, v in j.items() if v["real_conflict"]]
    inherited = [(a, v) for a, v in j.items() if v["release_shared"] and not v["real_conflict"]]
    with open(os.path.join(REG, "conflicts.md"), "w", encoding="utf-8") as fh:
        fh.write("# Shared-address map (potential conflicts)\n\n")
        fh.write("_Auto-generated by `scripts/build_registry.py`. Do not edit by hand._\n\n")
        fh.write(
            "These are addresses hooked by **two or more frameworks you can run at the same "
            "time**. Two co-loadable frameworks patching one address is the classic source of "
            "incompatibility: whichever loads second may overwrite the first, or their stolen "
            "bytes may overlap. Not *automatically* a bug — some are the same well-known engine "
            "call site everyone hooks compatibly — but each is worth a human look.\n\n"
        )
        fh.write(
            "**Excluded** from this list: overlaps that only occur between mutually-exclusive "
            f"frameworks ({' / '.join(' vs '.join(sorted(g)) for g in EXCLUSIVE_GROUPS)}), which "
            "you never load together — those are almost all inherited code, counted separately "
            "below. Loose PR hooks are excluded too; see `pr-hooks.md`.\n\n"
        )
        fh.write(f"**{len(conflicts)}** real (co-loadable) conflicts. "
                 f"_({len(inherited)} additional inherited Ares↔Antares-only overlaps, not shown.)_\n\n")
        fh.write("| Address | Frameworks | Functions |\n|---|---|---|\n")
        for a, v in sorted(conflicts, key=lambda kv: addr_key(kv[0])):
            rel = [c for c in v["consumers"] if c["channel"] == "release"]
            fns = "<br>".join(f"`{c['framework']}`: {c['function']}" for c in rel)
            fh.write(f"| `{a}` | {', '.join(v['release_frameworks'])} | {fns} |\n")

    # pr-hooks.md — loose hooks grouped by framework then PR
    pr_rows = [r for r in rows if r["channel"] != "release"]
    by_fw_pr = defaultdict(lambda: defaultdict(list))
    pr_meta = {}
    for r in pr_rows:
        by_fw_pr[r["framework"]][r["channel"]].append(r)
        pr_meta[(r["framework"], r["channel"])] = (r.get("pr_title", ""), r.get("pr_author", ""), r.get("pr_url", ""))
    with open(os.path.join(REG, "pr-hooks.md"), "w", encoding="utf-8") as fh:
        fh.write("# Loose hooks — from unmerged pull requests\n\n")
        fh.write("_Auto-generated by `scripts/build_registry.py` from `sources/pr_hooks.json`._\n\n")
        if not pr_rows:
            fh.write("_No PR data loaded yet. Run `scripts/fetch_pr_hooks.py`, then rebuild._\n")
        else:
            fh.write(
                "Hooks that exist **only in an open pull request**, not in any framework's "
                "mainline. They are proposals: they may change address, get rewritten, or "
                "never merge. Listed so you know what's in flight and where a future collision "
                "might land.\n\n"
            )
            total_prs = len({(r["framework"], r["channel"]) for r in pr_rows})
            fh.write(f"**{len(pr_rows)}** loose hooks across **{total_prs}** PRs.\n\n")
            for fw in sorted(by_fw_pr):
                fh.write(f"## {fw}\n\n")
                for chan in sorted(by_fw_pr[fw], key=lambda c: int(c.split("#")[1])):
                    title, author, url = pr_meta[(fw, chan)]
                    hooks = by_fw_pr[fw][chan]
                    head = f"### {chan}"
                    if title:
                        head += f" — {title}"
                    fh.write(head + "\n")
                    meta = []
                    if author:
                        meta.append(f"by @{author}")
                    if url:
                        meta.append(url)
                    if meta:
                        fh.write("_" + " · ".join(meta) + "_\n")
                    fh.write(f"\n{len(hooks)} hook(s):\n\n")
                    fh.write("| Address | Function | Stolen | Also in release? |\n|---|---|---|---|\n")
                    for h in sorted(hooks, key=lambda x: addr_key(x["address"])):
                        also = j[h["address"]]["release_frameworks"]
                        also_s = ", ".join(also) if also else "—"
                        fh.write(f"| `{h['address']}` | {h['function']} | {sb_str(h['stolen_bytes'])} | {also_s} |\n")
                    fh.write("\n")

    # STATS.md
    per = defaultdict(lambda: defaultdict(int))
    for r in rows:
        per[r["framework"]]["release" if r["channel"] == "release" else "pr"] += 1
    with open(os.path.join(REG, "STATS.md"), "w", encoding="utf-8") as fh:
        fh.write("# Registry statistics\n\n_Auto-generated by `scripts/build_registry.py`._\n\n")
        fh.write(f"- Total consumer rows: **{len(rows)}**\n")
        fh.write(f"- Distinct addresses: **{len(by_addr)}**\n")
        fh.write(f"- Real conflicts (co-loadable frameworks share an address): **{len(conflicts)}**\n")
        fh.write(f"- Inherited overlaps (Ares↔Antares only, not co-loaded): **{len(inherited)}**\n")
        fh.write(f"- Loose PR hooks: **{len(pr_rows)}**\n\n")
        fh.write("## Hooks per framework\n\n| Framework | Release | PR (loose) |\n|---|---|---|\n")
        for fw in sorted(per, key=lambda f: -per[f]["release"]):
            fh.write(f"| {fw} | {per[fw]['release']} | {per[fw]['pr']} |\n")

    # PROVENANCE.md
    with open(os.path.join(REG, "PROVENANCE.md"), "w", encoding="utf-8") as fh:
        fh.write("# Provenance — exact upstream commits\n\n")
        fh.write("_Auto-generated by `scripts/build_registry.py`. Release hooks were read "
                 "from these commits of the cloned upstream repos._\n\n")
        fh.write("| Framework | Commit | Date |\n|---|---|---|\n")
        for fw, sha, date in provenance:
            fh.write(f"| {fw} | `{sha}` | {date} |\n")
        if os.path.exists(PR_JSON):
            meta = json.load(open(PR_JSON)).get("meta", {})
            if meta.get("fetched"):
                fh.write(f"\nPR data fetched: {meta['fetched']}\n")

    print(f"OK: {len(rows)} rows, {len(by_addr)} addresses, "
          f"{len(conflicts) + len(inherited)} release-shared ({len(conflicts)} real conflicts), "
          f"{len(pr_rows)} loose PR hooks.")
    for fw in sorted(per, key=lambda f: -per[f]["release"]):
        print(f"  {fw}: release={per[fw]['release']} pr={per[fw]['pr']}")


if __name__ == "__main__":
    main()
