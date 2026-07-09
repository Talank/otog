#!/usr/bin/env bash
set -euo pipefail

# Print usage if no config ID is provided
if [ -z "${1:-}" ]; then
  echo "Error: Config ID is required as the first argument."
  echo "Usage: docker run --rm -v \$(pwd)/results:/workspace/.csto2 csto2-runner <CONFIG_ID>"
  echo ""
  echo "Available Config IDs:"
  if [ -d "/opt/csto/configs" ]; then
    for cfg in /opt/csto/configs/*.properties; do
      basename "$cfg" .properties | sed 's/^/  - /'
    done
  fi
  exit 1
fi

CONFIG_ID="$1"
CONFIG_FILE="/opt/csto/configs/${CONFIG_ID}.properties"

if [ ! -f "${CONFIG_FILE}" ]; then
  echo "Error: Configuration file not found for ID: ${CONFIG_ID}"
  exit 1
fi

echo "============================================="
echo "Starting CSTO Pipeline for Config ID: ${CONFIG_ID}"
echo "============================================="

# 1. Parse metadata from the config file
REPO_URL=$(grep "^repo_url\s*=" "${CONFIG_FILE}" | cut -d'=' -f2- | tr -d '\r' | xargs)
COMMIT_SHA=$(grep "^commit_sha\s*=" "${CONFIG_FILE}" | cut -d'=' -f2- | tr -d '\r' | xargs)
MODULE_DIR=$(grep "^module_dir\s*=" "${CONFIG_FILE}" | cut -d'=' -f2- | tr -d '\r' | xargs)
JAVA_HOME_PATH=$(grep "^java\s*=" "${CONFIG_FILE}" | cut -d'=' -f2- | tr -d '\r' | xargs)
MVN_OPTS_ARGS=$(grep "^mvnopts\s*=" "${CONFIG_FILE}" | cut -d'=' -f2- | tr -d '\r' | xargs || echo "")

echo "Repository: ${REPO_URL}"
echo "Commit:     ${COMMIT_SHA}"
echo "Module Dir: ${MODULE_DIR}"
echo "Java Home:  ${JAVA_HOME_PATH}"

# 2. Clone and checkout the repository
REPO_PATH="/workspace/repo"
rm -rf "${REPO_PATH}"
echo "Cloning repository..."
git clone "${REPO_URL}" "${REPO_PATH}"

cd "${REPO_PATH}"
echo "Checking out commit ${COMMIT_SHA}..."
git checkout --detach "${COMMIT_SHA}"

# 3. Setup Java environment
if [ -n "${JAVA_HOME_PATH}" ]; then
  export JAVA_HOME="${JAVA_HOME_PATH}"
  echo "Exported JAVA_HOME=${JAVA_HOME}"
fi

# Workaround TLS 1.3 resumption bugs ('No PSK available') in older JDKs (e.g. 11.0.2)
export MAVEN_OPTS="-Dhttps.protocols=TLSv1.2 -Djdk.tls.client.protocols=TLSv1.2"

# Ensure correct maven binary is used
MVN_BIN="mvn"
if [ -f "./mvnw" ]; then
  chmod +x ./mvnw
  MVN_BIN="./mvnw"
fi

PL_ARGS=""
if [ -n "${MODULE_DIR}" ] && [ "${MODULE_DIR}" != "." ]; then
  PL_ARGS="-pl ${MODULE_DIR} -am"
fi

echo "Installing project dependencies locally from the root..."
# Fix for "Unknown lifecycle phase '/root/.m2'" caused by official Maven Docker image
export MAVEN_CONFIG=""
echo "Running: ${MVN_BIN} clean install ${PL_ARGS} -DskipTests -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true -Drat.skip=true -Djacoco.skip=true ${MVN_OPTS_ARGS}"
${MVN_BIN} clean install ${PL_ARGS} -DskipTests -Dmaven.javadoc.skip=true -Dcheckstyle.skip=true -Drat.skip=true -Djacoco.skip=true ${MVN_OPTS_ARGS}





# 4. Initialize CSTO workspace and merge config
OUT_DIR="/workspace/.csto2"
mkdir -p "${OUT_DIR}"

# Copy the properties to the active csto config location
cp "${CONFIG_FILE}" "${OUT_DIR}/config.properties"

# Append surefire extension path to the config
echo "surefire-ext = /opt/csto/surefire-changing-maven-extension.jar" >> "${OUT_DIR}/config.properties"
echo "out = ${OUT_DIR}" >> "${OUT_DIR}/config.properties"

# 5. Run csto2 project setup command (autodetects classpath and tests)
echo "Running CSTO Project Setup..."
java -jar /opt/csto/csto2.jar project --dir "${REPO_PATH}/${MODULE_DIR}" --out "${OUT_DIR}"

# 6. Run csto2 scientific pipeline (runs discover -> trace -> select)
echo "Running CSTO Scientific Pipeline (repeats=10 + Wilcoxon signed-rank rank test)..."
java -jar /opt/csto/csto2.jar scientific --out "${OUT_DIR}"

echo "============================================="
echo "CSTO Pipeline completed successfully!"
echo "============================================="
