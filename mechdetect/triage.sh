#!/bin/bash
# Harness glue: full budgeted triage of one subject — capture -> profile -> confirm -> emit ->
# 3-pair screen. Usage: triage.sh <name> <module-dir> [java-home] [--vintage]
set -u
cd "$(dirname "$0")"
NAME=$1; DIR=$2; JH=${3:-/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home}
VINTAGE=${4:-}
AB=~/Development/Research/otog/mechanism_study/run_ab.py
# strip jacoco agent tokens from every fork: unresolved @{jacoco.agent.args} placeholders kill
# the JVM when surefire:test runs without the jacoco plugin, and coverage perturbs timing anyway
export KP_REMOVE_ARGS="${KP_REMOVE_ARGS:-} jacoco"

echo "=== [$NAME] capture"
./capture_natural.sh "$NAME" "$DIR" || { echo "[$NAME] CAPTURE FAILED"; exit 1; }
N=$(wc -l < "subjects/$NAME.natural")
[ "$N" -ge 10 ] || { echo "[$NAME] PARK: only $N classes captured"; exit 1; }

echo "=== [$NAME] profile"
if ! python3 profile.py --project "$DIR" --order "subjects/$NAME.natural" \
  --out "out/$NAME" --java-home "$JH" $VINTAGE --maven-arg=-Dcheckstyle.skip --maven-arg=-Denforcer.skip --maven-arg=-Dbasepom.check.skip-dependency-management=true; then
  if [ -z "$VINTAGE" ] && grep -q "JUnit Platform absent" "out/$NAME/mvn.log" 2>/dev/null; then
    echo "=== [$NAME] JUnit4 detected; retrying profile with vintage bridge"
    python3 profile.py --project "$DIR" --order "subjects/$NAME.natural" \
      --out "out/$NAME" --java-home "$JH" --vintage --maven-arg=-Dcheckstyle.skip \
      --maven-arg=-Denforcer.skip --maven-arg=-Dbasepom.check.skip-dependency-management=true \
      || { echo "[$NAME] PROFILE FAILED"; exit 1; }
  else
    echo "[$NAME] PROFILE FAILED"; exit 1
  fi
fi
[ -s "out/$NAME/candidates.tsv" ] || { echo "[$NAME] PARK: zero candidates"; exit 0; }

echo "=== [$NAME] confirm"
python3 confirm_moves.py "$NAME" --project "$DIR" --java-home "$JH" \
  --maven-arg=-Dcheckstyle.skip --maven-arg=-Denforcer.skip --maven-arg=-Dbasepom.check.skip-dependency-management=true

echo "=== [$NAME] emit + screen"
python3 emit_order.py "$NAME" "applied/$NAME-applied.order"
python3 "$AB" --project "$DIR" --order "applied=applied/$NAME-applied.order" \
  --order "natural=applied/$NAME-applied.baseline" --rounds 3 --out "t2/$NAME-screen" \
  "--maven-arg=-Djvm=$JH/bin/java" "--maven-arg=-Dcheckstyle.skip" "--maven-arg=-Denforcer.skip" "--maven-arg=-Dbasepom.check.skip-dependency-management=true"
python3 - "$NAME" <<'EOF'
import json, statistics, sys
name = sys.argv[1]
rows = [json.loads(l) for l in open(f"t2/{name}-screen/runs.jsonl")]
bad = sum(1 for r in rows if r.get("failures", 1) != 0)
per = {}
for r in rows:
    per.setdefault(r["round"], {})[r["arm"]] = r["suite_runtime_ms"]
d = [v["natural"] - v["applied"] for v in per.values() if len(v) == 2]
nat = statistics.median(r["suite_runtime_ms"] for r in rows if r["arm"] == "natural")
med = statistics.median(d) if d else 0
print(f"[{name}] SCREEN: pairs={len(d)} red_runs={bad} diffs={[round(x) for x in d]} "
      f"median=+{med:.0f}ms of {nat:.0f}ms = {100*med/nat:.2f}%")
EOF
echo "=== [$NAME] DONE"
