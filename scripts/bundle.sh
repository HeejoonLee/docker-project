#!/usr/bin/env bash
# Build an offline install package: dist/stonepedia-<version>.tar
# containing every Docker image the stack needs, a compose file pinned to this version,
# the Temporal init scripts, .env.example and INSTALL.md.
set -euo pipefail
cd "$(dirname "$0")/.."

base=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
VERSION=${VERSION:-$base-$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . ':!dist' || echo "-dirty")}
NAME=stonepedia-$VERSION
OUT=dist/$NAME

images=(
  "stonepedia:$VERSION"
  postgres:16
  temporalio/server:1.31.0
  temporalio/admin-tools:1.31.0
  temporalio/ui:2.49.1
)

echo "Building stonepedia:$VERSION"
if ! log=$(docker build -t "stonepedia:$VERSION" . 2>&1); then
  echo "$log" | tail -40 >&2
  echo "docker build failed" >&2
  exit 1
fi
for image in "${images[@]:1}"; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image"
done

rm -rf "$OUT" && mkdir -p "$OUT/deploy"
echo "Saving images (this takes a minute)"
docker save "${images[@]}" | gzip -1 > "$OUT/images.tar.gz"

# The installed compose file uses the saved image instead of building from source.
sed -e '/^    build: \.$/d' \
    -e "s|image: stonepedia:\${STONEPEDIA_VERSION:-latest}|image: stonepedia:$VERSION|" \
    docker-compose.yml > "$OUT/docker-compose.yml"
grep -q "image: stonepedia:$VERSION" "$OUT/docker-compose.yml"
cp -r deploy/temporal "$OUT/deploy/"
cp .env.example "$OUT/.env.example"
cp docs/install.md "$OUT/INSTALL.md"
echo "$VERSION" > "$OUT/VERSION"

tar -C dist -cf "dist/$NAME.tar" "$NAME"
rm -rf "$OUT"
echo
echo "  dist/$NAME.tar ($(du -h "dist/$NAME.tar" | cut -f1))"
echo "  Copy it to the server and follow INSTALL.md inside."
