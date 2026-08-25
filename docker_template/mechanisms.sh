#!/usr/bin/env bash
set -uo pipefail

# Mechanism A/B experiment: for one project, run the pairwise (two-class) and whole-suite
# arms of its confirmed mechanism (findings/mechanisms.md) for MECH_ROUNDS interleaved
# paired rounds, then run an exact Wilcoxon signed-rank test on the paired differences.
# Invoked by repo-runner (entrypoint) after the project build, with these exported:
# CONFIG_ID, REPO_PATH, MODULE_DIR, MVN_BIN, MVN_OPTS_ARGS, OUT_DIR.
#
# Measurement mirrors csto2's SurefireOrchestrator.runOrder (testorder extension, one
# reused fork, agent off). Metric: sum of Surefire testsuite times + wall clock. Results
# are appended to results.csv after EVERY arm run and the Wilcoxon summary is rewritten
# after every round, so a killed container still leaves usable data. Greenness is
# recorded per run; red rounds are excluded from the test. An arm that is red in both of
# the first two rounds aborts its experiment (a structurally red order can never ship,
# measuring it 10x is waste).

MECH_DIR="/opt/csto/mechanisms"
SPEC="${MECH_DIR}/specs/${CONFIG_ID}.spec"
EXT="/opt/csto/surefire-changing-maven-extension.jar"
ROUNDS="${MECH_ROUNDS:-10}"
CSV="${OUT_DIR}/results.csv"
SUMMARY="${OUT_DIR}/wilcoxon.txt"
LOGS="${OUT_DIR}/mech-logs"
ORDERS="${OUT_DIR}/orders"
mkdir -p "${LOGS}" "${ORDERS}"

if [ ! -f "${SPEC}" ]; then
  echo "No mechanism spec for config ${CONFIG_ID} (missing ${SPEC})"; exit 1
fi
# shellcheck source=/dev/null
source "${SPEC}"
echo "Mechanism: ${MECHANISM} (config ${CONFIG_ID}, ${ROUNDS} rounds)"

[ "${MVN_BIN}" = "./mvnw" ] && MVN_BIN="${REPO_PATH}/mvnw"
MODULE_PATH="${REPO_PATH}/${MODULE_DIR}"
cd "${MODULE_PATH}"

# The project's Surefire excludes (config `exclude = a,b`) must apply to the shipped
# natural order too -- -Dtest overrides pom excludes, so we filter here.
EXCLUDE=$(grep '^exclude\s*=' "/opt/csto/configs/${CONFIG_ID}.properties" | cut -d'=' -f2- | tr -d ' \r' || echo "")

# --- Build arm order files ------------------------------------------------------------
# Whole-suite arms: natural order minus excludes/absent classes, plus the spec's moves.
python3 "${MECH_DIR}/make_arm.py" "${MECH_DIR}/natural/${NATURAL}" "${ORDERS}/whole_fast.order" \
  --exclude "${EXCLUDE}" --moves "${WHOLE_FAST_MOVES}" --present-dir target/test-classes || exit 1
python3 "${MECH_DIR}/make_arm.py" "${MECH_DIR}/natural/${NATURAL}" "${ORDERS}/whole_slow.order" \
  --exclude "${EXCLUDE}" --moves "${WHOLE_SLOW_MOVES}" --present-dir target/test-classes || exit 1
# Pairwise arms: exactly the two spec classes.
printf '%s\n' ${PAIR_FAST} > "${ORDERS}/pair_fast.order"
printf '%s\n' ${PAIR_SLOW} > "${ORDERS}/pair_slow.order"

if [ "$(wc -l < "${ORDERS}/whole_fast.order")" != "$(wc -l < "${ORDERS}/whole_slow.order")" ]; then
  echo "FATAL: whole-suite arms have different class counts"; exit 1
fi

echo "config,mechanism,experiment,arm,round,slot,expected,reported,failures,errors,green,total_s,wall_s,mvn_exit" > "${CSV}"

# run_arm EXPERIMENT ARM ROUND SLOT -> appends one CSV row; echoes green flag (0/1)
run_arm() {
  local exp="$1" arm="$2" rnd="$3" slot="$4"
  local order="${ORDERS}/${exp}_${arm}.order"
  local expected; expected=$(wc -l < "${order}" | xargs)
  local log="${LOGS}/${exp}_${arm}_r${rnd}.log"
  rm -rf target/surefire-reports
  local t0; t0=$(date +%s)
  # Mirrors csto2's SurefireOrchestrator.runOrder, agent off. Fork flags LAST so they win.
  timeout -k 60 5400 ${MVN_BIN} initialize surefire:test \
    "-Dmaven.ext.class.path=${EXT}" \
    -Dsurefire.runOrder=testorder \
    "-Dtest=${order}" \
    -Dmaven.build.cache.enabled=false \
    -Dmaven.test.failure.ignore=true \
    ${MVN_OPTS_ARGS} \
    -DforkCount=1 -DreuseForks=true > "${log}" 2>&1
  local rc=$?
  local wall=$(( $(date +%s) - t0 ))
  local reported failures errors total
  reported=$(ls target/surefire-reports/TEST-*.xml 2>/dev/null | wc -l | xargs)
  failures=$(grep -h '<testsuite' target/surefire-reports/TEST-*.xml 2>/dev/null \
    | sed -n 's/.*[[:space:]]failures="\([0-9]*\)".*/\1/p' | awk '{s+=$1} END{print s+0}')
  errors=$(grep -h '<testsuite' target/surefire-reports/TEST-*.xml 2>/dev/null \
    | sed -n 's/.*[[:space:]]errors="\([0-9]*\)".*/\1/p' | awk '{s+=$1} END{print s+0}')
  total=$(grep -h '<testsuite' target/surefire-reports/TEST-*.xml 2>/dev/null \
    | sed -n 's/.*[[:space:]]time="\([0-9.,]*\)".*/\1/p' | tr -d ',' \
    | awk '{s+=$1} END{printf "%.3f", s}')
  local green=0
  if [ "${rc}" -eq 0 ] && [ "${reported}" = "${expected}" ] \
     && [ "${failures}" = "0" ] && [ "${errors}" = "0" ]; then
    green=1
  fi
  # Per-class times for the mechanism's tracked classes, for the report narrative.
  for cls in ${TRACK}; do
    local xml="target/surefire-reports/TEST-${cls}.xml"
    if [ -f "${xml}" ]; then
      local ct; ct=$(sed -n 's/.*<testsuite[^>]*[[:space:]]time="\([0-9.,]*\)".*/\1/p' "${xml}" | head -1 | tr -d ',')
      echo "${exp},${arm},${rnd},${cls},${ct}" >> "${OUT_DIR}/tracked-classes.csv"
    fi
  done
  echo "${CONFIG_ID},${MECHANISM},${exp},${arm},${rnd},${slot},${expected},${reported},${failures},${errors},${green},${total:-0},${wall},${rc}" >> "${CSV}"
  echo "  [${exp}/${arm} r${rnd}] total=${total:-?}s wall=${wall}s reported=${reported}/${expected} fail=${failures} err=${errors} green=${green}"
  return $(( 1 - green ))
}

echo "experiment,arm,round,class,class_s" > "${OUT_DIR}/tracked-classes.csv"

for EXP in pair whole; do
  echo "--- Experiment: ${EXP} (${ROUNDS} interleaved rounds) ---"
  declare -A REDS=( [fast]=0 [slow]=0 )
  ABORT=0
  for RND in $(seq 1 "${ROUNDS}"); do
    # Alternate which arm runs first each round so neither arm is pinned to a slot
    # (decorrelates slot bias like machine timing modes from the arm).
    if [ $(( RND % 2 )) -eq 1 ]; then ARMS="fast slow"; else ARMS="slow fast"; fi
    SLOT=1
    for ARM in ${ARMS}; do
      if ! run_arm "${EXP}" "${ARM}" "${RND}" "${SLOT}"; then
        REDS[${ARM}]=$(( REDS[${ARM}] + 1 ))
      fi
      SLOT=2
    done
    # Intermittent stats after every round.
    python3 "${MECH_DIR}/wilcoxon.py" "${CSV}" --partial > "${SUMMARY}" 2>&1 || true
    if [ "${RND}" -ge 2 ] && { [ "${REDS[fast]}" -ge 2 ] || [ "${REDS[slow]}" -ge 2 ]; } && [ "${RND}" -le 2 ]; then
      echo "ABORT ${EXP}: an arm was red in both of the first two rounds (structurally red order)"
      ABORT=1; break
    fi
  done
  [ "${ABORT}" -eq 1 ] && continue
done

echo "--- Final Wilcoxon signed-rank report ---"
python3 "${MECH_DIR}/wilcoxon.py" "${CSV}" | tee "${SUMMARY}"
echo "Mechanism experiment done -> ${CSV}, ${SUMMARY}, ${OUT_DIR}/tracked-classes.csv"
