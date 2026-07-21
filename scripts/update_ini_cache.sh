#!/usr/bin/env bash
# Refresh the vanilla-INI cache that build_engine_string_surface.py reads.
# Extracts the vanilla YR and RA2 INI zips into sources/ini-cache/ (gitignored).
# The loose "0 INI FILES" folder is volatile; the zips are the stable source.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CACHE="$HERE/../sources/ini-cache"
D="/mnt/wwn-0x50014ee6b383afb8-part1/(3) Games Data/RA2 & Yuri's Revenge/Tools/0 INI FILES"

mkdir -p "$CACHE/yr" "$CACHE/ra2"
if [ -f "$D/YRinis.zip" ]; then
  unzip -o -j "$D/YRinis.zip" -d "$CACHE/yr" >/dev/null && \
    echo "YR:  $(ls "$CACHE/yr"  | grep -ic '\.ini') ini"
else echo "WARN: missing $D/YRinis.zip"; fi
if [ -f "$D/RA2inis.zip" ]; then
  unzip -o -j "$D/RA2inis.zip" -d "$CACHE/ra2" >/dev/null && \
    echo "RA2: $(ls "$CACHE/ra2" | grep -ic '\.ini') ini + $(ls "$CACHE/ra2"/*.pkt 2>/dev/null | wc -l) pkt"
else echo "WARN: missing $D/RA2inis.zip"; fi

# Tiberian Sun INIs (the base engine) from the Vinifera community mirror.
if [ -d "$CACHE/ts/.git" ]; then
  git -C "$CACHE/ts" pull --depth 1 --ff-only >/dev/null 2>&1 && echo "TS:  updated @ $(git -C "$CACHE/ts" rev-parse --short HEAD)"
else
  git clone --depth 1 https://github.com/Vinifera-Developers/Tiberian-Sun-INIs.git "$CACHE/ts" >/dev/null 2>&1 && \
    echo "TS:  cloned @ $(git -C "$CACHE/ts" rev-parse --short HEAD)" || echo "WARN: TS clone failed"
fi
echo "Done. Now run: python3 scripts/build_engine_string_surface.py"
