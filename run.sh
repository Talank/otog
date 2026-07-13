#!/usr/bin/env bash
set -euo pipefail

# CSTO v2 Docker runner. Pins the container to the GitHub `ubuntu-latest`
# runner spec (4 vCPU / 16 GB RAM) so local runs match GHA measurements.

IMAGE="csto2-runner"
CTX="docker_template"
CPUS=4
MEM=16g

usage() {
  cat <<EOF
Usage: ./run.sh [--build] [--java <N|path>] [-f|--foreground] <CONFIG_ID>

  <CONFIG_ID>       Module config to run (e.g. 1683). See docker_template/README.md.
  --build           Force a rebuild of the '${IMAGE}' image before running.
  --java <N|path>   JDK for the discover helper only (8/11/17/21 or a JAVA_HOME path).
                    Default: csto2's own runtime. Does NOT change the measurement JVM.
  -f, --foreground  Stream output to the terminal instead of detaching.

By default the run detaches: it keeps running after you close the terminal, and all
output is saved to results/<ID>_<timestamp>/run.log even though --rm is set.

Container is pinned to the GitHub ubuntu-latest spec: ${CPUS} CPU / ${MEM} RAM.
EOF
}

FORCE_BUILD=0
FOREGROUND=0
CONFIG_ID=""
JAVA_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --build) FORCE_BUILD=1 ;;
    -f|--foreground) FOREGROUND=1 ;;
    --java) shift; JAVA_OVERRIDE="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    *) CONFIG_ID="$1" ;;
  esac
  shift
done

if [ -z "$CONFIG_ID" ]; then
  echo "Error: CONFIG_ID is required." >&2
  usage
  exit 1
fi

cd "$(dirname "$0")"

# Resolve an optional --java shorthand to a container JAVA_HOME path.
JAVA_ENV=()
if [ -n "$JAVA_OVERRIDE" ]; then
  case "$JAVA_OVERRIDE" in
    8|11|17)  JAVA_PATH="/usr/lib/jvm/java-${JAVA_OVERRIDE}-openjdk-amd64" ;;
    21)       JAVA_PATH="/opt/java/openjdk" ;;
    /*)       JAVA_PATH="$JAVA_OVERRIDE" ;;
    *) echo "Invalid --java '$JAVA_OVERRIDE' (use 8/11/17/21 or an absolute path)." >&2; exit 1 ;;
  esac
  JAVA_ENV=(-e "CSTO_DISCOVER_JAVA=${JAVA_PATH}")
fi

# Auto-detect host architecture to run natively/cleanly on macOS (Apple Silicon).
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
  PLATFORM="linux/arm64"
else
  PLATFORM="linux/amd64"
fi

# Build the image if forced or if it doesn't exist yet.
if [ "$FORCE_BUILD" -eq 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> Building image '${IMAGE}' for platform '${PLATFORM}'..."
  docker build --platform "$PLATFORM" -t "$IMAGE" "$CTX"
fi

# Fresh results folder per run so previous results are never clobbered.
STAMP=$(date +%Y%m%d-%H%M%S)
OUT_DIR="results/${CONFIG_ID}_${STAMP}"
LOG="${OUT_DIR}/run.log"
CONTAINER="csto2_${CONFIG_ID}_${STAMP}"
mkdir -p "$OUT_DIR"

RUN_ARGS=(
  --rm
  --name "$CONTAINER"
  --platform "$PLATFORM"
  --cpus="$CPUS"
  --memory="$MEM"
  --memory-swap="$MEM"
)
# Append JAVA_ENV only if set (bash 3.2 errors on empty-array expansion under `set -u`).
[ "${#JAVA_ENV[@]}" -gt 0 ] && RUN_ARGS+=( "${JAVA_ENV[@]}" )
RUN_ARGS+=(
  -v "$(pwd)/${OUT_DIR}:/workspace/.csto2"
  "$IMAGE" "$CONFIG_ID"
)

echo ">> Config ${CONFIG_ID} | ${CPUS} CPU / ${MEM} RAM (ubuntu-latest spec)"
echo ">> Results: ${OUT_DIR}"

if [ "$FOREGROUND" -eq 1 ]; then
  # Stream to terminal and log simultaneously.
  docker run "${RUN_ARGS[@]}" 2>&1 | tee "$LOG"
else
  # Detach: survives terminal close, output captured to the log despite --rm.
  nohup docker run "${RUN_ARGS[@]}" > "$LOG" 2>&1 &
  PID=$!
  disown
  echo ">> Detached. container=${CONTAINER} pid=${PID}"
  echo "   follow: tail -f ${LOG}"
  echo "   stop:   docker stop ${CONTAINER}"
fi
