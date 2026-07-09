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
Usage: ./run.sh [--build] <CONFIG_ID>

  <CONFIG_ID>   Module config to run (e.g. 1683). See docker_template/README.md.
  --build       Force a rebuild of the '${IMAGE}' image before running.

Pins the container to the GitHub ubuntu-latest spec: ${CPUS} CPU / ${MEM} RAM.
Results land in a fresh timestamped folder: results/<ID>_<timestamp>/
EOF
}

FORCE_BUILD=0
CONFIG_ID=""
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown option: $arg" >&2; usage; exit 1 ;;
    *) CONFIG_ID="$arg" ;;
  esac
done

if [ -z "$CONFIG_ID" ]; then
  echo "Error: CONFIG_ID is required." >&2
  usage
  exit 1
fi

cd "$(dirname "$0")"

# Build the image if forced or if it doesn't exist yet.
if [ "$FORCE_BUILD" -eq 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> Building image '${IMAGE}'..."
  docker build --platform linux/amd64 -t "$IMAGE" "$CTX"
fi

# Fresh results folder per run so previous results are never clobbered.
STAMP=$(date +%Y%m%d-%H%M%S)
OUT_DIR="results/${CONFIG_ID}_${STAMP}"
mkdir -p "$OUT_DIR"
echo ">> Results: ${OUT_DIR}"

echo ">> Running config ${CONFIG_ID} (${CPUS} CPU / ${MEM} RAM, ubuntu-latest spec)..."
docker run --rm \
  --platform linux/amd64 \
  --cpus="$CPUS" \
  --memory="$MEM" \
  --memory-swap="$MEM" \
  -v "$(pwd)/${OUT_DIR}:/workspace/.csto2" \
  "$IMAGE" "$CONFIG_ID"

echo ">> Done. Results in ${OUT_DIR}"
