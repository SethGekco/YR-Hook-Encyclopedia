#!/usr/bin/env python3
"""
fetch_modenc.py — enrich the engine string surface with ModEnc's documented facts.

ModEnc (modenc.renegadeprojects.com) is the community wiki that documents vanilla
RA2/YR/TS INI flags. It is a MediaWiki, so each flag page exposes clean structured
wikitext via `?action=raw`, with a `{{flag}}` template whose named parameters tell
us, authoritatively and citably, which INI file/section a tag belongs to and its
status (functional / parsed-but-no-effect / obsolete / hardcoded).

We fetch that, parse it, and cache ONLY the derived facts + the source URL + the
fetch date into sources/modenc-cache.json. That cache is committed (it is small
public-wiki metadata, NOT game data, and NOT article prose) so the enrichment is
reproducible and every datum is traceable back to its page. build_engine_string_
surface.py reads the cache and records a `modenc` provenance entry per tag.

*** PROVENANCE. *** A ModEnc datum is "as documented by a community wiki" — usually
reliable and human-verified, occasionally wrong, incomplete, or contested. It is a
DIFFERENT kind of evidence from our read-site consensus (derived from the binary).
When they agree, confidence is high; when they disagree, BOTH are recorded so the
conflict is visible rather than silently resolved.

Usage:
  python3 scripts/fetch_modenc.py                # fetch the tag-unlisted set (default)
  python3 scripts/fetch_modenc.py --all          # every tag/tag-unlisted string
  python3 scripts/fetch_modenc.py Foo Bar Baz    # specific tags
  python3 scripts/fetch_modenc.py --refresh ...  # refetch even if already cached
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")
CACHE = os.path.join(ROOT, "sources", "modenc-cache.json")
BASE = "https://modenc.renegadeprojects.com/index.php"
UA = "YR-Hook-Encyclopedia/1.0 (modding research; github.com/SethGekco/YR-Hook-Encyclopedia)"


def fetch_raw(title, _depth=0):
    """Raw wikitext of a page, following one #REDIRECT. None if the page is absent."""
    q = urllib.parse.urlencode({"title": title, "action": "raw"})
    req = urllib.request.Request(f"{BASE}?{q}", headers={"User-Agent": UA})
    try:
        txt = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if _depth == 0:
        m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", txt, re.I)
        if m:
            return fetch_raw(m.group(1).strip(), _depth=1)
    return txt


def extract_template(txt, name="flag"):
    """Body of the first {{name ...}} template, brace-balanced. None if not present."""
    m = re.search(r"\{\{\s*" + name + r"\b", txt, re.I)
    if not m:
        return None
    i = m.end()
    depth = 1
    while i < len(txt) - 1 and depth:
        pair = txt[i:i + 2]
        if pair == "{{":
            depth += 1; i += 2
        elif pair == "}}":
            depth -= 1; i += 2
        else:
            i += 1
    return txt[m.end():i - 2]


def split_params(body):
    """Split a template body on top-level '|' (ignoring '|' inside nested {{ }} / [[ ]])."""
    parts, buf, depth = [], [], 0
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1; buf.append(two); i += 2
        elif two in ("}}", "]]"):
            depth -= 1; buf.append(two); i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(buf)); buf = []; i += 1
        else:
            buf.append(body[i]); i += 1
    parts.append("".join(buf))
    return parts


def parse_flag(txt):
    body = extract_template(txt, "flag")
    if body is None:
        return None
    params = {}
    for p in split_params(body):
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().lower()] = v.strip()
    files = params.get("files", "")
    toks = set(re.findall(r"ini\s*=\s*([a-z0-9]+)", files, re.I))        # {{categ|ini=rules}}
    toks |= set(re.findall(r"\[\[\s*([a-z0-9]+)\.ini", files, re.I))      # [[sun.ini]]
    toks |= set(re.findall(r"\{\{\s*ini\s*\|\s*([a-z0-9]+)", files, re.I))  # {{Ini|sun}}
    toks |= set(re.findall(r"([a-z0-9]+)\(?md\)?\.ini", files, re.I))     # rulesmd.ini (text)
    ini = sorted({t.lower() for t in toks if t and t.lower() != "md"})
    types = sorted(set(re.findall(r"\{\{\s*categ\s*\|\s*([A-Za-z0-9 ]+?)\s*\}\}",
                                  params.get("types", ""), re.I)))
    status = []
    for flag, label in (("ra2obsolete", "ra2-obsolete"), ("yrobsolete", "yr-obsolete"),
                        ("obsolete", "obsolete"), ("removed", "removed"),
                        ("parsed", "parsed-no-effect"), ("hardcoded", "hardcoded"),
                        ("broken", "broken")):
        if flag in params:
            status.append(label)
    games = [g for g in ("ts", "fs", "ra2", "yr", "rp") if params.get(g, "").lower() in ("yes", "1")]
    return {"ini": [x.lower() for x in ini], "types": types, "status": status, "games": games}


def target_tags(argv):
    refresh = "--refresh" in argv
    argv = [a for a in argv if a != "--refresh"]
    surf = json.load(open(os.path.join(REG, "engine-string-surface.json")))
    if argv and argv[0] == "--all":
        tags = [s for s, v in surf.items() if v["kind"] in ("tag", "tag-unlisted")]
    elif argv:
        tags = argv
    else:  # default: the unnamed set that most needs naming
        tags = [s for s, v in surf.items() if v["kind"] == "tag-unlisted"]
    return sorted(set(tags)), refresh


def main():
    tags, refresh = target_tags(sys.argv[1:])
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE))
    today = time.strftime("%Y-%m-%d")
    todo = [t for t in tags if refresh or t not in cache]
    print(f"{len(tags)} target tags; {len(todo)} to fetch (cache has {len(cache)}).")
    done = miss = flg = 0
    for n, tag in enumerate(todo, 1):
        try:
            txt = fetch_raw(tag)
        except Exception as e:  # noqa: BLE001 — record and move on, don't lose progress
            print(f"  ! {tag}: {type(e).__name__} {e}", file=sys.stderr)
            continue
        url = f"https://modenc.renegadeprojects.com/{urllib.parse.quote(tag)}"
        if txt is None:
            cache[tag] = {"present": False, "url": url, "fetched": today}
            miss += 1
        else:
            flag = parse_flag(txt)
            if flag is None:
                cache[tag] = {"present": True, "flag": False, "url": url, "fetched": today}
            else:
                cache[tag] = {"present": True, "flag": True, **flag, "url": url, "fetched": today}
                flg += 1
        done += 1
        if n % 25 == 0:
            print(f"  ...{n}/{len(todo)}")
            json.dump(cache, open(CACHE, "w"), indent=2, sort_keys=True)  # checkpoint
        time.sleep(0.35)  # be polite to the wiki
    json.dump(cache, open(CACHE, "w"), indent=2, sort_keys=True)
    print(f"Done. fetched {done} (flag pages {flg}, missing {miss}). Cache -> {CACHE}")
    print("Now re-run: python3 scripts/build_engine_string_surface.py")


if __name__ == "__main__":
    main()
