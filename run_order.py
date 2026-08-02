#!/usr/bin/env python3
"""Harness glue: run ONE agentless order (any subset) through the testorder fork and print
per-class times parsed from surefire XML reports, as JSON on stdout's last line."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EXT = (Path.home() / ".m2/repository/fun/jvm/surefire/flaky/surefire-changing-maven-extension/"
       "1.0-SNAPSHOT/surefire-changing-maven-extension-1.0-SNAPSHOT.jar")
JAVA17 = "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--order", required=True, type=Path)
    p.add_argument("--java-home", default=JAVA17)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--maven-arg", action="append", default=[])
    args = p.parse_args()

    classes = [l.strip() for l in args.order.open() if l.strip()]
    reports = args.project / "target/surefire-reports"
    for c in classes:  # stale reports from earlier runs must not be readable as this run's
        (reports / f"TEST-{c}.xml").unlink(missing_ok=True)

    cmd = ["mvn", "initialize", "surefire:test",
           f"-Dmaven.ext.class.path={EXT}",
           "-Dsurefire.runOrder=testorder",
           f"-Dtest={args.order.resolve()}",
           "-Dmaven.build.cache.enabled=false",
           "-Dmaven.test.failure.ignore=true",
           "-DforkCount=1", "-DreuseForks=true",
           f"-Djvm={Path(args.java_home).resolve()}/bin/java", *args.maven_arg]
    import os
    env = os.environ.copy()  # headless: fork must not register as a macOS GUI app / steal focus
    env["KP_ARGLINE"] = ("-Djava.awt.headless=true -Dapple.awt.UIElement=true "
                         + env.get("KP_ARGLINE", "")).strip()
    with args.log.open("wb") as stream:
        rc = subprocess.run(cmd, cwd=args.project, env=env, stdout=stream,
                            stderr=subprocess.STDOUT).returncode

    out = {"rc": rc, "classes": {}}
    for c in classes:
        f = reports / f"TEST-{c}.xml"
        if f.exists():
            head = f.read_text(errors="replace")
            t = re.search(r'time="([0-9.,]+)"', head)
            bad = sum(int(x) for x in re.findall(r'(?:failures|errors)="(\d+)"', head[:600]))
            out["classes"][c] = {"time": float(t.group(1).replace(",", "")) if t else None,
                                 "green": bad == 0}
    print(json.dumps(out))
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
