#!/usr/bin/env python3
"""
check_hook_chain.py — fail the build if one of this project's hooks can
SILENTLY TRUNCATE another DLL's hook chain.

Why this exists
---------------
check_hook_overlap.py already catches two hooks whose byte RANGES intersect, and
it correctly treats two hooks at the SAME address as safe: Syringe chains those
and runs both handlers. Its advice when you overlap someone is even to move onto
their exact address so the two chain.

That advice is right, and it opens a second failure mode it cannot see.

Syringe's chain is return-value driven. Each handler returns 0 to mean "carry on"
— the next handler in the chain runs, then the stolen original instructions are
replayed. A handler that returns NON-ZERO means "jump to this address", and that
jump happens immediately: the remaining handlers in the chain never run, and the
original instructions are never replayed.

So if you share an address with Ares/Phobos/Kratos and your handler can return
non-zero, you silently disable theirs on that path. Nothing is malformed — your
bytes are correct, their bytes are correct, every bounds and overlap check
passes — the chain just stops early. There is no crash and no module to blame,
which is what makes it expensive to find in game.

This is not hypothetical either. KratosPP's own design notes record hooking
0x424CB0 (Phobos' site) in a first version and realising it would have "silently
cut off Phobos' Layer_UseObjectLayer", so they moved to 0x424CCA. They also keep
their command-registration hook at 0x533066 returning 0 unconditionally,
specifically so Ares' and Phobos' commands still register.

What it reports
---------------
For every project hook sharing an EXACT address with another framework:
  * ERROR  — the handler can return non-zero (chain-breaking), or it is a
             DEFINE_JUMP (which never chains at all)
  * ok     — the handler provably only ever returns 0

Intentional takeovers are allowed. Annotate the return with a marker comment:

    if (ShouldOverride) return 0x6FE360;   // CHAIN-OK: deliberately replaces
                                           // Phobos' handler, see docs/x.md

Usage
-----
    check_hook_chain.py <registry-hooks.csv> [src-dir] [--project NAME]

`--project` excludes that Framework's own rows from the registry so a project
already catalogued in the encyclopedia does not match itself. It defaults to the
basename of the repo containing src-dir.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HOOK_RE = re.compile(
    r'\bDEFINE_(HOOK(?:_AGAIN)?|JUMP)\s*\(\s*'
    r'(?:([A-Z]+)\s*,\s*)?'                         # DEFINE_JUMP(LJMP, addr,..)
    r'((?:0[xX])?[0-9A-Fa-f]+)\s*,\s*(\w+)?'
)
CHAIN_OK = re.compile(r'//[^\n]*CHAIN-OK', re.I)
RETURN_RE = re.compile(r'\breturn\b([^;]*);')


def _strip_noise(text):
    """Blank out comments and string/char literals so brace counting and return
    scanning don't trip over them. Keeps length so offsets stay valid."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif c in '"\'':
            q, j = c, i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2
                    continue
                if text[j] == q:
                    j += 1
                    break
                j += 1
            for k in range(i, min(j, n)):
                out[k] = ' '
            i = j
        else:
            i += 1
    return ''.join(out)


def _body(clean, start):
    """Source slice of the handler body following the macro at `start`."""
    b = clean.find('{', start)
    if b < 0:
        return None, None
    depth, i, n = 0, b, len(clean)
    while i < n:
        if clean[i] == '{':
            depth += 1
        elif clean[i] == '}':
            depth -= 1
            if depth == 0:
                return b, i + 1
        i += 1
    return b, n


def parse_our_hooks(src_dir):
    hooks = []
    for path in sorted(Path(src_dir).rglob('*.cpp')):
        raw = path.read_text(encoding='utf-8', errors='replace')
        clean = _strip_noise(raw)
        for m in HOOK_RE.finditer(clean):
            kind, _lj, addr, name = m.groups()
            pasted = not addr.lower().startswith('0x')
            b0, b1 = _body(clean, m.end())
            returns = []
            if kind != 'JUMP' and b0 is not None:
                for r in RETURN_RE.finditer(clean, b0, b1):
                    expr = r.group(1).strip()
                    # The marker lives in the ORIGINAL text, which still has
                    # comments; look at the line the return sits on.
                    ls = raw.rfind('\n', 0, r.start()) + 1
                    le = raw.find('\n', r.end())
                    le = len(raw) if le < 0 else le
                    line_no = raw.count('\n', 0, r.start()) + 1
                    waived = bool(CHAIN_OK.search(raw[ls:le]))
                    if not waived and le < len(raw):      # allow marker on the
                        nl = raw.find('\n', le + 1)        # following line
                        waived = bool(CHAIN_OK.search(raw[le:nl if nl > 0 else len(raw)]))
                    returns.append({'expr': expr, 'line': line_no,
                                    'waived': waived})
            hooks.append({
                'addr': int(addr, 16), 'name': name or '?', 'kind': kind,
                'where': str(path), 'returns': returns,
                'line': clean.count('\n', 0, m.start()) + 1,
                '_pasted': pasted,
            })
    return hooks


def parse_registry(csv_path, skip_framework=None):
    by_addr = defaultdict(list)
    skip = (skip_framework or '').lower()
    with open(csv_path, newline='', encoding='utf-8', errors='replace') as fh:
        for row in csv.DictReader(fh):
            try:
                addr = int(row['Address'], 16)
            except (ValueError, KeyError, TypeError):
                continue
            fw = (row.get('Framework') or '?').strip()
            if skip and fw.lower() == skip:
                continue
            by_addr[addr].append((fw, (row.get('Function') or '?').strip()))
    return by_addr


def nonzero_returns(hook):
    """Returns that would jump, i.e. break the chain, minus any waived."""
    out = []
    for r in hook['returns']:
        e = r['expr']
        if e == '' or re.fullmatch(r'0|0x0+|0X0+', e):
            continue
        if r['waived']:
            continue
        out.append(r)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opts = {a.split('=', 1)[0]: (a.split('=', 1)[1] if '=' in a else '')
            for a in sys.argv[1:] if a.startswith('--')}
    if not args:
        print(__doc__)
        return 2
    csv_path = args[0]
    src_dir = args[1] if len(args) > 1 else 'src'
    project = opts.get('--project') or Path(src_dir).resolve().parent.name

    ours = parse_our_hooks(src_dir)
    if not ours:
        print('check_hook_chain: found no DEFINE_HOOK in %s — refusing to pass '
              'vacuously.' % src_dir)
        return 2
    registry = parse_registry(csv_path, skip_framework=project)

    shared, errors, waived_n = [], [], 0
    for h in ours:
        others = registry.get(h['addr'])
        if not others:
            continue
        fws = sorted({fw for fw, _ in others})
        shared.append((h, fws))
        waived_n += sum(1 for r in h['returns'] if r['waived'])
        if h['kind'] == 'JUMP':
            errors.append((h, fws, None))
            continue
        bad = nonzero_returns(h)
        if bad:
            errors.append((h, fws, bad))

    print(f"check_hook_chain: {len(ours)} project hooks, "
          f"{len(shared)} sharing an address with {project and 'other' or ''} "
          f"frameworks, {waived_n} waived return(s)")

    for h, fws in shared:
        if not any(e[0] is h for e in errors):
            print(f"  ok     0x{h['addr']:06X} {h['name']} "
                  f"chains with {', '.join(fws)}")

    if errors:
        print('\nCHAIN-BREAKING HOOKS — these silently disable the other DLL:\n')
        for h, fws, bad in errors:
            with_ = ', '.join(fws)
            if bad is None:
                print(f"  0x{h['addr']:06X} {h['name']} is a DEFINE_JUMP but "
                      f"{with_} also hook here — a jump never chains, so their "
                      f"handler never runs.")
            else:
                print(f"  0x{h['addr']:06X} {h['name']} shares with {with_} and "
                      f"can return non-zero:")
                for r in bad:
                    print(f"      {h['where']}:{r['line']}  return {r['expr']};")
        print("\nEach non-zero return jumps immediately: the rest of the chain "
              "and the stolen original instructions are skipped. Either return 0 "
              "and let the chain finish, or — if the takeover is deliberate — "
              "annotate that return with a `// CHAIN-OK: <reason>` comment.")
        return 1

    print('check_hook_chain: no chain-breaking returns at shared addresses.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
