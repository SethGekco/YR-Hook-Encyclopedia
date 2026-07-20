#!/usr/bin/env python3
"""
build_vanilla_tag_candidates.py — Phase D: vanilla INI tag -> candidate read site.

Vanilla (original-game) rules tags aren't in any framework source, so Phase C
can't see them. But the game reads them by pushing the tag's string address as a
call argument: on x86 that's `push offset "Tag"` = byte `68 <VA-little-endian>`.
So we can, with no Ghidra:

  1. enumerate the vanilla tag universe from an unedited rules INI,
  2. locate each tag's null-terminated string in gamemd.exe -> its virtual address,
  3. scan .text for `push <that VA>` -> the exact code sites that read the tag.

Each such site is a *candidate hook location* for that tag.

*** UNVERIFIED / HEURISTIC. *** A push-ref proves the tag string is referenced at
that address; it does NOT prove that's where the behaviour lives, nor that a hook
there is correct. It's a starting point that beats a blank slate. Tags read via
tables/loops (no per-tag push) show up as no-candidate — honestly.

Outputs: registry/vanilla-tags.csv, vanilla-tags.json, vanilla-tags.md.
"""

import csv
import json
import os
import re
import struct
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry")

EXE = "/home/rex/gamemd.exe"
RULES = ("/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/"
         "Tools/0 INI FILES/Patched YR/Uneditted Rules/rulesmd.ini")


def parse_pe(data):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE"
    nsec = struct.unpack_from("<H", data, e_lfanew + 6)[0]
    sizeopt = struct.unpack_from("<H", data, e_lfanew + 20)[0]
    opt = e_lfanew + 24
    imgbase = struct.unpack_from("<I", data, opt + 28)[0]
    so = opt + sizeopt
    secs = []
    for i in range(nsec):
        b = so + i * 40
        name = data[b:b + 8].rstrip(b"\0").decode("latin1")
        vs, va, rs, pr = struct.unpack_from("<IIII", data, b + 8)
        secs.append({"name": name, "vs": vs, "va": va, "rs": rs, "pr": pr})
    return imgbase, secs


def make_maps(imgbase, secs):
    def off2va(off):
        for s in secs:
            if s["pr"] <= off < s["pr"] + s["rs"]:
                return imgbase + s["va"] + (off - s["pr"])
        return None

    def va2off(vaddr):
        r = vaddr - imgbase
        for s in secs:
            if s["va"] <= r < s["va"] + max(s["vs"], s["rs"]):
                return s["pr"] + (r - s["va"])
        return None

    return off2va, va2off


def text_section(secs):
    for s in secs:
        if s["name"] == ".text":
            return s
    return secs[0]


def load_vanilla_tags():
    keys = []
    seen = set()
    with open(RULES, encoding="latin1") as fh:
        for line in fh:
            m = re.match(r"\s*([A-Za-z][A-Za-z0-9._]*)\s*=", line)
            if m:
                k = m.group(1)
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
    return keys


def find_standalone_string(data, tag):
    """First null-terminated occurrence of tag not preceded by an identifier byte."""
    needle = tag.encode("latin1") + b"\x00"
    i = data.find(needle)
    while i != -1:
        prev = data[i - 1:i]
        # standalone if preceded by NUL or non-identifier byte
        if prev == b"\x00" or not re.match(rb"[A-Za-z0-9_.]", prev):
            return i
        i = data.find(needle, i + 1)
    return -1


def main():
    data = open(EXE, "rb").read()
    imgbase, secs = parse_pe(data)
    off2va, va2off = make_maps(imgbase, secs)
    text = text_section(secs)
    text_lo, text_hi = text["pr"], text["pr"] + text["rs"]

    # One pass over .text: index every `push imm32` (0x68) by its target VA.
    push_index = defaultdict(list)
    off = text_lo
    tb = data
    while off < text_hi - 5:
        if tb[off] == 0x68:
            target = struct.unpack_from("<I", tb, off + 1)[0]
            push_index[target].append(off2va(off))
        off += 1

    tags = load_vanilla_tags()

    # Also cross-reference: known registry hook addresses, to hint when a read site
    # sits near an already-documented hook.
    known = set()
    hp = os.path.join(REG, "hooks.json")
    if os.path.exists(hp):
        known = {int(a, 16) for a in json.load(open(hp))}

    def nearest_known(va, window=0x400):
        best = None
        for k in known:
            d = abs(k - va)
            if d <= window and (best is None or d < abs(best - va)):
                best = k
        return best

    out = {}
    conf_counts = defaultdict(int)
    for tag in tags:
        soff = find_standalone_string(data, tag)
        if soff == -1:
            out[tag] = {"tag": tag, "confidence": "no-string", "string_va": None, "push_refs": [], "data_refs": []}
            conf_counts["no-string"] += 1
            continue
        sva = off2va(soff)
        push_refs = [hex(v) for v in push_index.get(sva, []) if v]
        data_refs = []
        if not push_refs:
            # fallback: any 4-byte occurrence of the VA inside .text (mov/lea/table)
            pat = struct.pack("<I", sva)
            j = data.find(pat, text_lo)
            while j != -1 and j < text_hi:
                va = off2va(j)
                if va:
                    data_refs.append(hex(va))
                j = data.find(pat, j + 1)
        if push_refs:
            conf = "push-ref"
        elif data_refs:
            conf = "data-ref"
        else:
            conf = "no-ref"
        conf_counts[conf] += 1
        hints = {}
        for r in push_refs + data_refs:
            nk = nearest_known(int(r, 16))
            if nk is not None:
                hints[r] = hex(nk)
        out[tag] = {
            "tag": tag,
            "confidence": conf,
            "string_va": hex(sva),
            "push_refs": push_refs,
            "data_refs": data_refs,
            "near_known_hook": hints,  # candidate_va -> nearby registered hook addr
        }

    os.makedirs(REG, exist_ok=True)
    with open(os.path.join(REG, "vanilla-tags.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(REG, "vanilla-tags.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Tag", "Confidence", "StringVA", "PushRefs", "DataRefs"])
        for tag in tags:
            v = out[tag]
            w.writerow([tag, v["confidence"], v.get("string_va") or "",
                        " ".join(v["push_refs"]), " ".join(v.get("data_refs", []))])

    with open(os.path.join(REG, "vanilla-tags.md"), "w", encoding="utf-8") as fh:
        fh.write("# Vanilla tag → candidate read-site index (Phase D)\n\n")
        fh.write("_Auto-generated by `scripts/build_vanilla_tag_candidates.py` from "
                 f"`gamemd.exe` (imagebase {hex(imgbase)}) and the unedited vanilla rules._\n\n")
        fh.write("> ## ⚠ UNVERIFIED / HEURISTIC — read this first\n")
        fh.write("> A **push-ref** means the tag's string address is pushed as a call argument\n")
        fh.write("> at that code address — i.e. the game reads the tag there. That is a strong\n")
        fh.write("> hint at *where the tag is parsed*, **not** proof of where its behaviour lives\n")
        fh.write("> or that a hook there is correct. **data-ref** is weaker (the string address\n")
        fh.write("> appears in code but not as a clean push). Confirm before relying on any of it.\n")
        fh.write("> Tags read via tables/loops have no per-tag push and show as no-ref.\n\n")
        fh.write(f"**{len(tags)}** vanilla tags. Confidence: " +
                 ", ".join(f"{c} {n}" for c, n in sorted(conf_counts.items(), key=lambda x: -x[1])) + ".\n\n")
        fh.write("| Tag | Conf | Candidate read site(s) | Near known hook |\n|---|---|---|---|\n")
        for tag in tags:
            v = out[tag]
            refs = v["push_refs"] or v.get("data_refs", [])
            shown = " ".join(f"`{r}`" for r in refs[:6]) or "—"
            if len(refs) > 6:
                shown += f" (+{len(refs) - 6})"
            hints = v.get("near_known_hook", {})
            hint = " ".join(f"`{k}`→`{val}`" for k, val in list(hints.items())[:3]) or ""
            fh.write(f"| `{tag}` | {v['confidence']} | {shown} | {hint} |\n")

    print(f"OK: {len(tags)} vanilla tags. Confidence: {dict(conf_counts)}")
    print(f"  push-index size: {len(push_index)} distinct push targets in .text")


if __name__ == "__main__":
    main()
