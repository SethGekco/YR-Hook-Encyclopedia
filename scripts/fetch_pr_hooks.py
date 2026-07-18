#!/usr/bin/env python3
"""
fetch_pr_hooks.py — sweep open pull requests for "loose" hooks.

For each configured repo, lists open PRs (via `gh`), fetches each PR's diff, and
records every DEFINE_HOOK / DEFINE_HOOK_AGAIN that the PR *adds* (a `+` line in
the diff) — i.e. hooks that exist only in an unmerged proposal, not in any
framework's mainline. Writes ../sources/pr_hooks.json, which build_registry.py
merges as the PR channel.

Requires the `gh` CLI to be authenticated (`gh auth status`). Network-bound and
slow-ish (one diff fetch per PR), so it's a separate step from the fast local
build. Re-run when you want to refresh the loose-hook picture.
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "sources", "pr_hooks.json")

# repo -> framework label used in the registry / pr-hooks.md
REPOS = {
    "Phobos-developers/Phobos": "Phobos",
    "ra2diy/KratosPP": "Kratos",
    "CnCRAZER/Ares": "Ares (CnCRAZER fork)",
    # Antares & Ares upstream have 0 open PRs today, but listing them is cheap
    # and future-proofs the sweep.
    "Phobos-developers/Antares": "Antares",
    "Ares-Developers/Ares": "Ares",
}

HOOK_RE = re.compile(
    r"DEFINE_HOOK(?:_AGAIN)?\s*\(\s*(?:0x)?([0-9A-Fa-f]+)\s*,\s*([A-Za-z_]\w*)\s*,\s*(?:0x)?([0-9A-Fa-f]+)"
)


def sh(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def list_open_prs(repo):
    r = sh(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "500",
            "--json", "number,title,url,author"])
    if r.returncode != 0:
        print(f"  WARN: gh pr list failed for {repo}: {r.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


def subsystem_for(path):
    # path like src/Ext/Aircraft/Hooks.cpp -> Ext/Aircraft
    p = path
    if p.startswith("src/"):
        p = p[4:]
    d = os.path.dirname(p)
    return d if d else "."


def added_hooks_from_diff(diff_text):
    """Yield (address, function, size_hex, path) for DEFINE_HOOK on added (+) lines."""
    cur_path = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            # +++ b/src/... or +++ /dev/null
            p = line[4:].strip()
            if p.startswith("b/"):
                p = p[2:]
            cur_path = None if p == "/dev/null" else p
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if cur_path and not cur_path.endswith((".cpp", ".h")):
                continue
            content = line[1:]
            if "#define" in content:
                continue
            m = HOOK_RE.search(content)
            if m:
                yield m.group(1), m.group(2), m.group(3), cur_path or "?"


def main():
    all_hooks = []
    for repo, fw in REPOS.items():
        prs = list_open_prs(repo)
        print(f"{repo}: {len(prs)} open PRs")
        for pr in prs:
            num = pr["number"]
            r = sh(["gh", "pr", "diff", str(num), "-R", repo], timeout=180)
            if r.returncode != 0:
                print(f"  PR #{num}: diff failed ({r.stderr.strip()[:80]})", file=sys.stderr)
                continue
            found = 0
            seen = set()
            for addr, fn, size, path in added_hooks_from_diff(r.stdout):
                key = (addr.upper(), fn, path)
                if key in seen:
                    continue
                seen.add(key)
                all_hooks.append({
                    "framework": fw,
                    "repo": repo,
                    "pr": num,
                    "pr_title": pr.get("title", ""),
                    "pr_author": (pr.get("author") or {}).get("login", ""),
                    "pr_url": pr.get("url", ""),
                    "address": "0x" + addr.upper(),
                    "function": fn,
                    "stolen_bytes": "0x" + size.upper(),
                    "subsystem": subsystem_for(path),
                    "source_file": path,
                })
                found += 1
            if found:
                print(f"  PR #{num}: +{found} hook(s) — {pr.get('title','')[:60]}")
            time.sleep(0.05)  # be gentle with the API

    out = {
        "meta": {"fetched": time.strftime("%Y-%m-%d %H:%M:%S"), "repos": list(REPOS)},
        "hooks": all_hooks,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    prs_with_hooks = len({(h["repo"], h["pr"]) for h in all_hooks})
    print(f"\nWrote {OUT}: {len(all_hooks)} loose hooks across {prs_with_hooks} PRs.")


if __name__ == "__main__":
    main()
