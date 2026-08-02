#!/bin/bash
# Harness glue: capture the real mvn-test execution order of a project.
set -u
p=$1; dir=$2
cd "$dir"
mvn test -Dmaven.test.failure.ignore=true -Drat.skip -Djacoco.skip -Danimal.sniffer.skip -Dcheckstyle.skip -Dspotless.check.skip -Denforcer.skip -Dlicense.skip 2>&1 \
  | grep -E "^(\[INFO\] )?Running " | sed -E 's/^(\[INFO\] )?Running //' > /tmp/natural-$p.raw
python3 - "$p" <<'PY'
import sys
p = sys.argv[1]
seen = {}
for l in open(f"/tmp/natural-{p}.raw"):
    c = l.strip()
    if c and "$" not in c and c not in seen:
        seen[c] = 1
out = f"/Users/gabriel/Development/Research/otog/mechdetect/subjects/{p}.natural"
open(out, "w").write("\n".join(seen) + "\n")
print(p, len(seen), "classes ->", out)
PY
