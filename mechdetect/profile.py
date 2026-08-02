#!/usr/bin/env python3
"""Harness glue: run one profiled Surefire order with the mechdetect agent + JFR, then analyze.

Command construction mirrors mechanism_study/run_ab.py (testorder fork + KP_ARGLINE injection).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

EXT = (Path.home() / ".m2/repository/fun/jvm/surefire/flaky/surefire-changing-maven-extension/"
       "1.0-SNAPSHOT/surefire-changing-maven-extension-1.0-SNAPSHOT.jar")
AGENT = Path(__file__).resolve().parent / "target/mechdetect.jar"
VINTAGE = ("org.junit.vintage:junit-vintage-engine:5.9.3,"
           "org.junit.platform:junit-platform-launcher:1.9.3,"
           "org.junit.jupiter:junit-jupiter-api:5.9.3")
JAVA17 = "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--order", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--java-home", type=Path, default=Path(JAVA17),
                   help="fork JVM (default Temurin 17; NEVER inherit maven's JVM — "
                        "the system maven runs Homebrew JDK 26)")
    p.add_argument("--vintage", action="store_true",
                   help="JUnit4 project: inject vintage engine so the platform listener runs")
    p.add_argument("--jfr-settings",
                   default=str(Path(__file__).resolve().parent / "mechdetect.jfc"))
    p.add_argument("--mvn", default="mvn")
    p.add_argument("--maven-arg", action="append", default=[])
    p.add_argument("--skip-analyze", action="store_true")
    args = p.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    jfr = out / "recording.jfr"

    argline = (f"-Djava.awt.headless=true -Dapple.awt.UIElement=true "  # never steal focus
               f"-javaagent:{AGENT}=out={out} "
               f"-XX:FlightRecorderOptions=stackdepth=256 "
               f"-XX:StartFlightRecording=settings={args.jfr_settings},filename={jfr},dumponexit=true")

    env = os.environ.copy()
    fork_java = str(args.java_home.resolve()) if args.java_home else env.get("JAVA_HOME", "")
    if "corretto-8" not in fork_java and "1.8" not in fork_java:
        argline += (" --add-opens=java.base/java.lang=ALL-UNNAMED"
                    " --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED")
    else:
        # JDK9+ flag kills a Java 8 fork; append, never clobber inherited needles
        env["KP_REMOVE_ARGS"] = (env.get("KP_REMOVE_ARGS", "") + " --illegal-access").strip()
    argline += " " + os.environ.get("MECHDETECT_EXTRA", "")
    env["KP_ARGLINE"] = argline
    if args.vintage:
        env["KP_DEPENDENCIES"] = VINTAGE

    cmd = [args.mvn, "initialize", "surefire:test",
           f"-Dmaven.ext.class.path={EXT}",
           "-Dsurefire.runOrder=testorder",
           f"-Dtest={args.order.resolve()}",
           "-Dmaven.build.cache.enabled=false",
           "-Dmaven.test.failure.ignore=true",
           "-DforkCount=1", "-DreuseForks=true", *args.maven_arg]
    if args.java_home:
        # pin the surefire FORK to this JVM; maven itself keeps its own JVM
        cmd.append(f"-Djvm={args.java_home.resolve()}/bin/java")

    log = out / "mvn.log"
    print(f"[profile] {' '.join(cmd)}\n[profile] KP_ARGLINE={argline}", flush=True)
    with log.open("wb") as stream:
        rc = subprocess.run(cmd, cwd=args.project, env=env,
                            stdout=stream, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        sys.exit(f"maven exited {rc}; see {log}")
    if not (out / "profile.jsonl").exists():
        sys.exit(f"no profile.jsonl produced; see {log}")
    print(f"[profile] ok: {out}/profile.jsonl", flush=True)

    if not args.skip_analyze:
        subprocess.run([f"{JAVA17}/bin/java", "-jar", str(AGENT), str(out)], check=False)


if __name__ == "__main__":
    main()
