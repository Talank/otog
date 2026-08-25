#!/usr/bin/env bash
set -euo pipefail

# Mechanism A/B experiment runner: for each of the four confirmed mechanisms
# (csto2/findings/mechanisms.md sections 5-8), runs the pairwise (two-class) and
# whole-suite arm pairs for 10 interleaved rounds each through the csto2-style Surefire
# invocation, with an exact Wilcoxon signed-rank test at the end. Results land in
# results_<ID>_mechanisms/{results.csv,wilcoxon.txt,tracked-classes.csv} and are written
# incrementally (results.csv after every arm run, wilcoxon.txt after every round).
# Modules: sy = SnakeYAML first-use init (s5, JDK8), 1683 = JavaParser symbol solver
# shared JIT code (s6, JDK11), text = Commons Text inline mocks (s7, JDK11),
# 1305 = AsyncHttpClient Netty leak policy (s8, JDK11). Usage:
#   ./run_mechanisms.sh 1305 [--build]     one module, detached
#   ./run_mechanisms.sh all  [--build]     all 4 modules, sequentially, detached

IMAGE="csto2-runner"
CTX="docker_template"
CPUS=4
MEM=16g
MODULES=(sy 1683 text 1305)

cd "$(dirname "$0")"

ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then PLATFORM="linux/arm64"; else PLATFORM="linux/amd64"; fi

run_one() {
  local id=$1
  local out="results_${id}_mechanisms"
  local name="csto2_mech_${id}"
  if docker ps --format '{{.Names}}' | grep -qx "$name"; then
    echo "!! ${name} already running, skipping ${id}"; return 0
  fi
  mkdir -p "$out"
  echo ">> Mechanism experiment ${id} -> ${out}/"
  docker run --rm --name "$name" --platform "$PLATFORM" \
    --cpus="$CPUS" --memory="$MEM" --memory-swap="$MEM" \
    -v "$(pwd)/${out}:/workspace/.csto2" \
    "$IMAGE" "$id" mechanisms > "${out}/run.log" 2>&1 || echo "!! ${id} exited non-zero"
  echo ">> ${id} done. Report: ${out}/wilcoxon.txt"
}

# Internal foreground modes (what the detached process actually runs).
if [ "${1:-}" = "__fg" ]; then run_one "$2"; exit 0; fi
if [ "${1:-}" = "__fg_all" ]; then for id in "${MODULES[@]}"; do run_one "$id"; done; echo "ALL_DONE"; exit 0; fi

if [ -z "${1:-}" ]; then echo "Usage: $0 <sy|1683|text|1305|all> [--build]" >&2; exit 1; fi
TARGET="$1"

if [ "${2:-}" = "--build" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> Building image '${IMAGE}' for '${PLATFORM}'..."
  docker build --platform "$PLATFORM" -t "$IMAGE" "$CTX"
fi

if [ "$TARGET" = "all" ]; then
  # One container at a time: concurrent runs would contend for CPU and skew the timings.
  nohup "$0" __fg_all > mechanisms_all.log 2>&1 &
  disown
  echo ">> Running all ${#MODULES[@]} mechanism modules sequentially in the background."
  echo "   follow: tail -f mechanisms_all.log   (per-module: results_<ID>_mechanisms/run.log)"
else
  nohup "$0" __fg "$TARGET" > "mechanisms_${TARGET}.launch.log" 2>&1 &
  disown
  echo ">> Detached. follow: tail -f results_${TARGET}_mechanisms/run.log ; stop: docker stop csto2_mech_${TARGET}"
fi
