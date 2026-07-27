#!/usr/bin/env bash
set -euo pipefail

# Replication experiment runner: re-runs the prior researcher's version-0 orders (3 per module,
# 3 iterations each) through the csto2-style Surefire invocation, to compare this machine's
# results against their logged times. Results land in results_<ID>_replication/replication.csv
# next to expected.csv (their logged times). Usage:
#   ./run_replication.sh 1683 [--build]     one module, detached
#   ./run_replication.sh all  [--build]     all 10 modules, sequentially, detached

IMAGE="csto2-runner"
CTX="docker_template"
CPUS=4
MEM=16g
MODULES=(1305 1683 1685 1778 20 29 33 3320 3323 3613)

cd "$(dirname "$0")"

ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then PLATFORM="linux/arm64"; else PLATFORM="linux/amd64"; fi

run_one() {
  local id=$1
  local out="results_${id}_replication"
  local name="csto2_repl_${id}"
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    echo "!! ${name} already running, skipping ${id}"; return 0
  fi
  mkdir -p "$out"
  echo ">> Replicating module ${id} -> ${out}/"
  docker run --rm --name "$name" --platform "$PLATFORM" \
    --cpus="$CPUS" --memory="$MEM" --memory-swap="$MEM" \
    -v "$(pwd)/${out}:/workspace/.csto2" \
    "$IMAGE" "$id" replicate > "${out}/run.log" 2>&1 || echo "!! ${id} exited non-zero"
  echo ">> ${id} done. CSV: ${out}/replication.csv"
}

# Internal foreground modes (what the detached process actually runs).
if [ "${1:-}" = "__fg" ]; then run_one "$2"; exit 0; fi
if [ "${1:-}" = "__fg_all" ]; then for id in "${MODULES[@]}"; do run_one "$id"; done; echo "ALL_DONE"; exit 0; fi

if [ -z "${1:-}" ]; then echo "Usage: $0 <CONFIG_ID|all> [--build]" >&2; exit 1; fi
TARGET="$1"

if [ "${2:-}" = "--build" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> Building image '${IMAGE}' for '${PLATFORM}'..."
  docker build --platform "$PLATFORM" -t "$IMAGE" "$CTX"
fi

if [ "$TARGET" = "all" ]; then
  # One container at a time: concurrent runs would contend for CPU and skew the timings.
  nohup "$0" __fg_all > replication_all.log 2>&1 &
  disown
  echo ">> Running all ${#MODULES[@]} modules sequentially in the background."
  echo "   follow: tail -f replication_all.log   (per-module: results_<ID>_replication/run.log)"
else
  nohup "$0" __fg "$TARGET" > "replication_${TARGET}.launch.log" 2>&1 &
  disown
  echo ">> Detached. follow: tail -f results_${TARGET}_replication/run.log ; stop: docker stop csto2_repl_${TARGET}"
fi
