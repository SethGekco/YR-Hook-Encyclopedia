#!/usr/bin/env bash
# Clone or update the upstream framework repos that build_registry.py reads the
# RELEASE-channel hooks from. Shallow clones; not committed to this repo.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPOS="$HERE/../sources/repos"
mkdir -p "$REPOS"

declare -A URLS=(
  [Ares]=https://github.com/Ares-Developers/Ares.git
  [Antares]=https://github.com/Phobos-developers/Antares.git
  [Phobos]=https://github.com/Phobos-developers/Phobos.git
  [Kratos]=https://github.com/ra2diy/KratosPP.git
)

for name in "${!URLS[@]}"; do
  d="$REPOS/$name"
  if [ -d "$d/.git" ]; then
    echo "updating $name ..."
    git -C "$d" fetch --depth 1 origin >/dev/null 2>&1 \
      && git -C "$d" reset --hard origin/HEAD >/dev/null 2>&1 \
      && echo "  OK $name @ $(git -C "$d" rev-parse --short HEAD)" \
      || echo "  FAIL update $name"
  else
    echo "cloning $name ..."
    git clone --depth 1 "${URLS[$name]}" "$d" >/dev/null 2>&1 \
      && echo "  OK $name @ $(git -C "$d" rev-parse --short HEAD)" \
      || echo "  FAIL clone $name"
  fi
done
echo "Done. Now run: python3 scripts/build_registry.py"
