#!/usr/bin/env bash
set -euo pipefail

# Sort-granularity experiment, one module per invocation, fully through Maven Surefire.
#
# Pipeline:
#   1. clone + checkout + build the module (config JDK)
#   2. csto2 project/discover -> deps.classpath + tests.runnable (csto2's suite)
#   3. compile MethodAllocListener into target/test-classes (+ ServiceLoader file)
#   4. TRACE: one carryover Surefire run over the suite -> per-method allocBytes
#   5. gen_orders.py -> 7 arm order files (classes always contiguous)
#   6. GREEN-GATE: run initial once, drop any class that fails from every arm
#   7. MEASURE: ROUNDS x 7 arms, shuffled per round, testorder through Surefire
#   8. analyze.py -> Wilcoxon summary
#
# Requires the base image built from the updated surefire fork (method-order commit), which is what
# makes the method-level arms (mth / pkg-cls-mth / cls-mth) actually order methods on JUnit 5.

CONFIG_ID="${1:?config id required}"
ROUNDS="${ROUNDS:-10}"
TRACE_REPEATS="${TRACE_REPEATS:-1}"

CFG="/opt/csto/configs/${CONFIG_ID}.properties"
[ -f "$CFG" ] || { echo "no config for $CONFIG_ID"; exit 1; }
getp() { grep "^$1[[:space:]]*=" "$CFG" | cut -d'=' -f2- | tr -d '\r' | xargs || true; }

REPO_URL=$(getp repo_url); COMMIT=$(getp commit_sha); MODULE_DIR=$(getp module_dir)
JAVA_HOME_CFG=$(getp java); MVN_OPTS_ARGS=$(getp mvnopts)
OUT=/workspace/.csto2; REPO=/workspace/repo; MODP="$REPO/${MODULE_DIR}"
EXT=/opt/csto/surefire-changing-maven-extension.jar
export MAVEN_CONFIG=""
export MAVEN_OPTS="-Dhttps.protocols=TLSv1.2 -Djdk.tls.client.protocols=TLSv1.2"
[ -n "$JAVA_HOME_CFG" ] && export JAVA_HOME="$JAVA_HOME_CFG"
mkdir -p "$OUT/orders"

echo "=== [1] clone $REPO_URL @ $COMMIT ($MODULE_DIR) ==="
rm -rf "$REPO"; git clone "$REPO_URL" "$REPO"
( cd "$REPO" && git checkout --detach "$COMMIT" )
MVN="mvn"; [ -f "$REPO/mvnw" ] && { chmod +x "$REPO/mvnw"; MVN="$REPO/mvnw"; }
PL=""; [ -n "$MODULE_DIR" ] && [ "$MODULE_DIR" != "." ] && PL="-pl $MODULE_DIR -am"

echo "=== [2] build + discover ==="
( cd "$REPO" && $MVN clean install $PL -DskipTests -Dmaven.javadoc.skip=true \
    -Dcheckstyle.skip=true -Drat.skip=true -Djacoco.skip=true $MVN_OPTS_ARGS )
cp "$CFG" "$OUT/config.properties"
{ echo "surefire-ext = $EXT"; echo "out = $OUT"; } >> "$OUT/config.properties"
java -jar /opt/csto/csto2.jar project --dir "$MODP" --out "$OUT"
sed -i "s#^java[[:space:]]*=.*#java = ${CSTO_DISCOVER_JAVA:-}#" "$OUT/config.properties"
java -jar /opt/csto/csto2.jar discover --out "$OUT" || true
TESTS="$OUT/tests.runnable"; [ -s "$TESTS" ] || TESTS="$OUT/tests.all"
[ -s "$TESTS" ] || { echo "no test list produced"; exit 1; }
echo "suite: $(wc -l < "$TESTS") classes"

echo "=== [3] compile per-method alloc listener ==="
DEPS=$(cat "$OUT/deps.classpath")
PV=$(tr ':' '\n' <<<"$DEPS" | grep -oE 'junit-platform-commons/[0-9.]+' | grep -oE '[0-9.]+$' | head -1)
[ -n "$PV" ] || PV=1.9.0
for A in junit-platform-engine junit-platform-launcher; do
  J=$(ls "$HOME/.m2/repository/org/junit/platform/$A/$PV/$A-$PV.jar" 2>/dev/null || true)
  [ -z "$J" ] && { $MVN -q dependency:get -Dartifact="org.junit.platform:$A:$PV" || true; \
                   J="$HOME/.m2/repository/org/junit/platform/$A/$PV/$A-$PV.jar"; }
  DEPS="$DEPS:$J"
done
javac -cp "$DEPS" -d "$MODP/target/test-classes" /opt/csto/sortexp/MethodAllocListener.java
mkdir -p "$MODP/target/test-classes/META-INF/services"
echo "sortexp.MethodAllocListener" \
  > "$MODP/target/test-classes/META-INF/services/org.junit.platform.launcher.TestExecutionListener"

echo "=== [4] trace per-method allocation ($TRACE_REPEATS repeats) ==="
: > "$OUT/alloc.jsonl"
for i in $(seq 1 "$TRACE_REPEATS"); do
  ( cd "$MODP" && rm -rf target/surefire-reports && \
    $MVN -q surefire:test -Dmaven.ext.class.path="$EXT" -Dsurefire.runOrder=testorder \
      -Dtest="$TESTS" -Dmethodalloc.out="$OUT/alloc.jsonl" $MVN_OPTS_ARGS ) || true
done
python3 - "$OUT/alloc.jsonl" "$OUT/method_order.txt" "$OUT/class_order.txt" <<'PY'
import json,sys
alloc,mo,co=sys.argv[1:4]
seen=set();ms=[];cs=[];cseen=set()
for l in open(alloc):
    l=l.strip()
    if not l: continue
    t=json.loads(l)["test"]
    if t not in seen: seen.add(t); ms.append(t)
    c=t.split("#")[0]
    if c not in cseen: cseen.add(c); cs.append(c)
open(mo,"w").write("\n".join(ms)+"\n"); open(co,"w").write("\n".join(cs)+"\n")
PY

echo "=== [5] generate 7 arm orders ==="
python3 /opt/csto/sortexp/gen_orders.py "$OUT/alloc.jsonl" "$OUT/class_order.txt" \
  "$OUT/method_order.txt" "$OUT/orders"

echo "=== [6] green-gate (drop classes failing at baseline) ==="
# measurement must NOT run the trace listener (adds overhead)
rm -f "$MODP/target/test-classes/META-INF/services/org.junit.platform.launcher.TestExecutionListener"
( cd "$MODP" && rm -rf target/surefire-reports && \
  $MVN -q surefire:test -Dmaven.ext.class.path="$EXT" -Dsurefire.runOrder=testorder \
    -Dtest="$OUT/orders/initial.order" $MVN_OPTS_ARGS ) || true
python3 - "$MODP/target/surefire-reports" "$OUT/orders" "$OUT/excluded.txt" <<'PY'
import glob,os,sys,xml.etree.ElementTree as ET
reports,orders,exc=sys.argv[1:4]
bad=set()
for x in glob.glob(os.path.join(reports,"TEST-*.xml")):
    e=ET.parse(x).getroot()
    for tc in e.findall("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            bad.add(tc.get("classname"))
for f in glob.glob(os.path.join(orders,"*.order")):
    keep=[l for l in open(f) if l.strip() and l.split("#")[0] not in bad]
    open(f,"w").writelines(keep)
open(exc,"w").write("\n".join(sorted(bad))+"\n")
print("excluded %d classes: %s"%(len(bad),[c.split('.')[-1] for c in sorted(bad)]))
PY

echo "=== [7] measure: $ROUNDS rounds x 7 arms ==="
RES="$OUT/results.tsv"; : > "$RES"
for r in $(seq 1 "$ROUNDS"); do
  ARMS=$(python3 -c "import random;a=['initial','mth','pkg','pkg-cls','pkg-cls-mth','cls','cls-mth'];random.seed(900+$r);random.shuffle(a);print(' '.join(a))")
  for arm in $ARMS; do
    ( cd "$MODP" && rm -rf target/surefire-reports && \
      $MVN -q surefire:test -Dmaven.ext.class.path="$EXT" -Dsurefire.runOrder=testorder \
        -Dtest="$OUT/orders/$arm.order" $MVN_OPTS_ARGS ) || true
    read ms cls fails < <(python3 - "$MODP/target/surefire-reports" <<'PY'
import glob,os,sys,xml.etree.ElementTree as ET
t=0.0;c=0;f=0
for x in glob.glob(os.path.join(sys.argv[1],"TEST-*.xml")):
    e=ET.parse(x).getroot();c+=1
    t+=float(e.get("time",0)); f+=int(e.get("failures",0))+int(e.get("errors",0))
print(int(t*1000),c,f)
PY
)
    printf "%s\t%s\t%s\t%s\t%s\n" "$r" "$arm" "$ms" "$cls" "$fails" >> "$RES"
    echo "  r$r $arm: ${ms}ms classes=$cls fails=$fails"
  done
done

echo "=== [8] analysis ==="
python3 /opt/csto/sortexp/analyze.py "$RES" | tee "$OUT/summary.txt"
echo "artifacts in $OUT: results.tsv summary.txt orders/ alloc.jsonl excluded.txt"
