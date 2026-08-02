#!/usr/bin/env python3
"""Harness glue: run ONE arm (one suite run) and append its result to a jsonl.

Chained alternately (A,B / B,A per round) this reproduces run_ab's interleaving in
task-sized pieces for long suites.
"""
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

EXT = (Path.home() / ".m2/repository/fun/jvm/surefire/flaky/surefire-changing-maven-extension/"
       "1.0-SNAPSHOT/surefire-changing-maven-extension-1.0-SNAPSHOT.jar")

project, order, arm, out_jsonl, java_home = sys.argv[1:6]
cmd = ["mvn", "initialize", "surefire:test",
       f"-Dmaven.ext.class.path={EXT}", "-Dsurefire.runOrder=testorder",
       f"-Dtest={Path(order).resolve()}", "-Dmaven.build.cache.enabled=false",
       "-Dmaven.test.failure.ignore=true", "-DforkCount=1", "-DreuseForks=true",
       f"-Djvm={java_home}/bin/java"]
import os
env = os.environ.copy()  # headless: fork must not register as a macOS GUI app and steal focus
env["KP_ARGLINE"] = ("-Djava.awt.headless=true -Dapple.awt.UIElement=true "
                     + env.get("KP_ARGLINE", "")).strip()
t0 = time.monotonic()
log = Path(out_jsonl).with_suffix(f".{int(time.time())}.log")
rc = subprocess.run(cmd, cwd=project, env=env, stdout=log.open("wb"),
                    stderr=subprocess.STDOUT).returncode
wall = (time.monotonic() - t0) * 1000
expected = {l.strip() for l in open(order) if l.strip()}
suite, fails, seen = 0.0, 0, set()
for p in Path(project, "target/surefire-reports").glob("TEST-*.xml"):
    r = ET.parse(p).getroot()
    name = r.get("name", "").split("$")[0]
    if name in expected:
        seen.add(name)
        suite += float(r.get("time", 0)) * 1000
        fails += int(r.get("failures", 0)) + int(r.get("errors", 0))
row = {"arm": arm, "suite_ms": round(suite), "failures": fails, "rc": rc,
       "covered": len(seen), "expected": len(expected), "wall_ms": round(wall)}
with open(out_jsonl, "a") as f:
    f.write(json.dumps(row) + "\n")
print(row)
