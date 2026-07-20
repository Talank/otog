#!/usr/bin/env bash
set -euo pipefail

# Host runner for the sort-granularity experiment.
#   ./run.sh [--build-base] [--rounds N] <CONFIG_ID> [<CONFIG_ID> ...]
#
# Pins each container to the GitHub ubuntu-latest spec (4 CPU / 16 GB) so timings match GHA.
# Each module writes to results_sort_<ID>/ and runs detached (survives terminal close);
# output streams to results_sort_<ID>/run.log.
#
# The base image (csto2-runner) must exist and must have been built from the updated surefire fork
# (method-order commit). Pass --build-base to rebuild it from ../docker_template first.

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE_CTX="$HERE/../docker_template"
IMAGE="csto2-sort-runner"
BASE_IMAGE="csto2-runner"
CPUS=4; MEM=16g; ROUNDS=10; BUILD_BASE=0
IDS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --build-base) BUILD_BASE=1; shift;;
    --rounds) ROUNDS="$2"; shift 2;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) IDS+=("$1"); shift;;
  esac
done
[ ${#IDS[@]} -gt 0 ] || { echo "usage: ./run.sh [--build-base] [--rounds N] <CONFIG_ID>..."; exit 1; }

if [ "$BUILD_BASE" = 1 ] || ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo ">> building base image $BASE_IMAGE (clones the updated surefire fork)"
  docker build --platform linux/amd64 -t "$BASE_IMAGE" "$BASE_CTX"
fi

echo ">> building $IMAGE"
docker build --platform linux/amd64 -t "$IMAGE" "$HERE"

for ID in "${IDS[@]}"; do
  RESDIR="$HERE/results_sort_${ID}"
  mkdir -p "$RESDIR"
  echo ">> launching $ID (rounds=$ROUNDS) -> $RESDIR/run.log"
  docker run -d --rm --platform linux/amd64 --cpus "$CPUS" --memory "$MEM" \
    -e ROUNDS="$ROUNDS" \
    -v "$RESDIR":/workspace/.csto2 \
    --name "sort_${ID}" "$IMAGE" "$ID" \
    > "$RESDIR/container_id" 2>/dev/null
  # detach but capture logs
  ( docker logs -f "sort_${ID}" >"$RESDIR/run.log" 2>&1 & ) || true
done
echo ">> running. tail a log with: tail -f results_sort_<ID>/run.log"
