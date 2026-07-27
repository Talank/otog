#!/usr/bin/env bash
set -uo pipefail

# Replication experiment: re-run the prior researcher's version-0 orders (3 per module, 3
# iterations each; originals + their logged times in /opt/csto/replication) and record the same
# metric they logged: the sum of Surefire testsuite times. Invoked by repo-runner (entrypoint)
# after the project build, with these exported: CONFIG_ID, REPO_PATH, MODULE_DIR, MVN_BIN,
# MVN_OPTS_ARGS, OUT_DIR.
# NOTE: this uses csto2's measurement invocation (testorder extension + forced single REUSED fork).
# The prior results were measured with per-class forks for every project except paimon, so a
# systematic offset for non-paimon modules is expected — that difference is part of the experiment.

ORDERS_DIR="/opt/csto/replication/${CONFIG_ID}"
EXT="/opt/csto/surefire-changing-maven-extension.jar"
CSV="${OUT_DIR}/replication.csv"
LOGS="${OUT_DIR}/replication-logs"
mkdir -p "${LOGS}"

if [ ! -d "${ORDERS_DIR}" ]; then
  echo "No replication orders for module ${CONFIG_ID} (missing ${ORDERS_DIR})"; exit 1
fi

[ "${MVN_BIN}" = "./mvnw" ] && MVN_BIN="${REPO_PATH}/mvnw"
cd "${REPO_PATH}/${MODULE_DIR}"
echo "module,order_id,iteration,measured_total_s,wall_s,mvn_exit" > "${CSV}"

for ORDER_FILE in "${ORDERS_DIR}"/order_*.order; do
  OID=$(basename "${ORDER_FILE}" .order | sed 's/^order_//')
  for ITER in 1 2 3; do
    LOG="${LOGS}/order${OID}_iter${ITER}.log"
    T0=$(date +%s)
    # Mirrors csto2's SurefireOrchestrator.runOrder, agent off. Fork flags LAST so they win.
    ${MVN_BIN} initialize surefire:test \
      "-Dmaven.ext.class.path=${EXT}" \
      -Dsurefire.runOrder=testorder \
      "-Dtest=${ORDER_FILE}" \
      -Dmaven.build.cache.enabled=false \
      -Dmaven.test.failure.ignore=true \
      ${MVN_OPTS_ARGS} \
      -DforkCount=1 -DreuseForks=true > "${LOG}" 2>&1
    RC=$?
    WALL=$(( $(date +%s) - T0 ))
    TOTAL=$(grep -h '<testsuite' target/surefire-reports/TEST-*.xml 2>/dev/null \
      | sed -n 's/.*[[:space:]]time="\([0-9.,]*\)".*/\1/p' | tr -d ',' \
      | awk '{s+=$1} END{printf "%.3f", s}')
    echo "${CONFIG_ID},${OID},${ITER},${TOTAL:-0},${WALL},${RC}" | tee -a "${CSV}"
  done
done

echo "Replication done -> ${CSV} (compare against /opt/csto/replication/expected.csv)"
cp /opt/csto/replication/expected.csv "${OUT_DIR}/expected.csv"
