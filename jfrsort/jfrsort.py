#!/usr/bin/env python3
"""jfrsort: sort a Maven project's test classes by JFR-measured metrics.

Pipeline: run `mvn test` N times with a JFR recording on every forked JVM,
discover the test classes from the Surefire XML reports, attribute JFR events
to test classes by stack trace, average the per-class metric over the N runs,
and emit the classes sorted by that metric, descending.

The only metric implemented today is `alloc`: estimated allocated heap bytes
per test class, from jdk.ObjectAllocationSample event weights. The sort rule
matches csto2's alloc-sort: a stable sort of the initial order by the metric,
descending, so ties keep their initial relative order.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

# metric name -> the JFR event to collect and the field holding the per-event value
METRICS = {
    "alloc": {"event": "jdk.ObjectAllocationSample", "value_field": "weight"},
}


def top_level(cls: str) -> str:
    """Collapse a nested class name (com.Foo$Bar) to its top-level class (com.Foo)."""
    return cls.split("$", 1)[0]


def frame_class(frame) -> str | None:
    """Dotted class name of one stack frame from `jfr print --json`, or None."""
    name = ((frame.get("method") or {}).get("type") or {}).get("name")
    return name.replace("/", ".") if name else None


def clean_reports(project: Path):
    for rep in project.rglob("target/surefire-reports"):
        shutil.rmtree(rep, ignore_errors=True)


def run_profiled(project: Path, run_dir: Path, mvn: str, maven_args: list[str]) -> tuple[Path, float]:
    """One `mvn test` run with JFR on every JVM. Returns (jfr dir, wall seconds)."""
    jfr_dir = run_dir / "jfr"
    jfr_dir.mkdir(parents=True, exist_ok=True)
    clean_reports(project)
    env = dict(os.environ)
    env["JAVA_TOOL_OPTIONS"] = (
        "-XX:FlightRecorderOptions:stackdepth=1024 "
        f"-XX:StartFlightRecording:settings=profile,dumponexit=true,filename={jfr_dir}/"
    )
    log = run_dir / "mvn.log"
    t0 = time.time()
    with open(log, "w") as lf:
        rc = subprocess.run([mvn, "-B", "test", *maven_args],
                            cwd=project, env=env,
                            stdout=lf, stderr=subprocess.STDOUT).returncode
    wall = time.time() - t0
    if rc != 0:
        sys.exit(f"jfrsort: mvn test failed (exit {rc}); see {log}. "
                 "The suite must be green before it can be profiled.")
    return jfr_dir, wall


def discover_tests(project: Path) -> list[str]:
    """Top-level test classes from the Surefire XML reports, in execution order.

    Surefire writes each TEST-*.xml when its class finishes, so ascending file
    mtime approximates execution order. Nested classes collapse to top-level.
    """
    reports = sorted(project.rglob("target/surefire-reports/TEST-*.xml"),
                     key=lambda p: p.stat().st_mtime)
    seen, ordered = set(), []
    for rep in reports:
        try:
            name = ElementTree.parse(rep).getroot().get("name")
        except ElementTree.ParseError:
            continue
        if not name:
            continue
        cls = top_level(name)
        if cls not in seen:
            seen.add(cls)
            ordered.append(cls)
    if not ordered:
        sys.exit(f"jfrsort: no Surefire reports found under {project}")
    return ordered


def parse_recording(jfr_bin: str, rec: Path, event: str, value_field: str,
                    test_set: set[str]) -> tuple[dict[str, float], float]:
    """Attribute one recording's events to test classes.

    Returns ({test class -> summed value}, unattributed value). An event is
    attributed to the first frame, innermost first, whose top-level class is a
    known test class; events with no such frame are unattributed.
    """
    out = subprocess.run([jfr_bin, "print", "--json", "--stack-depth", "1024",
                          "--events", event, str(rec)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"jfrsort: jfr print failed on {rec}: {out.stderr.strip()}")
    events = json.loads(out.stdout)["recording"]["events"]
    per_class: dict[str, float] = {}
    unattributed = 0.0
    for ev in events:
        vals = ev["values"]
        value = float(vals.get(value_field) or 0)
        frames = ((vals.get("stackTrace") or {}).get("frames")) or []
        owner = None
        for fr in frames:
            cls = frame_class(fr)
            if cls and top_level(cls) in test_set:
                owner = top_level(cls)
                break
        if owner is None:
            unattributed += value
        else:
            per_class[owner] = per_class.get(owner, 0.0) + value
    return per_class, unattributed


def collect_run(jfr_bin: str, jfr_dir: Path, metric: dict,
                tests: list[str]) -> dict:
    """Parse every recording of one run and merge the attributed values."""
    test_set = set(tests)
    merged: dict[str, float] = {}
    unattributed = 0.0
    kept, dropped = [], []
    for rec in sorted(jfr_dir.glob("*.jfr")):
        per_class, unattr = parse_recording(jfr_bin, rec, metric["event"],
                                            metric["value_field"], test_set)
        if not per_class:
            # A recording with no test-class frames is not a test JVM
            # (e.g. the Maven launcher, which JAVA_TOOL_OPTIONS also reaches).
            dropped.append(rec.name)
            continue
        kept.append(rec.name)
        unattributed += unattr
        for cls, v in per_class.items():
            merged[cls] = merged.get(cls, 0.0) + v
    if not kept:
        sys.exit(f"jfrsort: no recording in {jfr_dir} contained test-class frames")
    return {"per_class": merged, "unattributed": unattributed,
            "recordings_kept": kept, "recordings_dropped": dropped}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True, type=Path,
                    help="Maven project/module directory to run `mvn test` in")
    ap.add_argument("--runs", type=int, default=3,
                    help="number of profiled mvn test runs to average (default 3)")
    ap.add_argument("--metric", choices=sorted(METRICS), default="alloc")
    ap.add_argument("--out", type=Path, default=Path(".jfrsort"),
                    help="output directory (default .jfrsort)")
    ap.add_argument("--mvn", default="mvn", help="Maven binary (default mvn)")
    ap.add_argument("--jfr-bin", default="jfr", help="jfr CLI binary (default jfr)")
    ap.add_argument("--maven-args", default="",
                    help="extra arguments appended to the mvn command line")
    args = ap.parse_args()

    project = args.project.resolve()
    out = args.out.resolve()
    metric = METRICS[args.metric]
    maven_args = args.maven_args.split()

    runs = []
    tests_initial = None
    for i in range(1, args.runs + 1):
        run_dir = out / f"run-{i}"
        print(f"[jfrsort] run {i}/{args.runs}: mvn test with JFR ...", flush=True)
        jfr_dir, wall = run_profiled(project, run_dir, args.mvn, maven_args)
        tests = discover_tests(project)
        if tests_initial is None:
            tests_initial = tests            # run 1 defines the initial order
        elif set(tests) != set(tests_initial):
            print(f"[jfrsort] WARNING: run {i} test set differs from run 1; using the union",
                  file=sys.stderr)
            tests_initial += [t for t in tests if t not in tests_initial]
        data = collect_run(args.jfr_bin, jfr_dir, metric, tests)
        data["wall_seconds"] = round(wall, 1)
        (run_dir / "metrics.json").write_text(json.dumps(data, indent=1))
        runs.append(data)
        attr = sum(data["per_class"].values())
        total = attr + data["unattributed"]
        pct = 100.0 * attr / total if total else 0.0
        print(f"[jfrsort] run {i}: {wall:.0f}s, {len(data['recordings_kept'])} test JVM(s), "
              f"{pct:.1f}% of {args.metric} weight attributed", flush=True)

    # average over runs; a class with no samples in a run counts 0 for that run
    mean = {t: sum(r["per_class"].get(t, 0.0) for r in runs) / len(runs)
            for t in tests_initial}

    # csto2 alloc-sort rule: stable sort of the initial order, metric descending
    order = sorted(tests_initial, key=lambda t: -mean[t])

    out.mkdir(parents=True, exist_ok=True)
    order_file = out / f"order-{args.metric}-sort.txt"
    order_file.write_text("\n".join(order) + "\n")
    with open(out / "metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["test", f"mean_{args.metric}"] +
                   [f"run{i+1}_{args.metric}" for i in range(len(runs))])
        for t in order:
            w.writerow([t, round(mean[t])] +
                       [round(r["per_class"].get(t, 0.0)) for r in runs])

    print(f"\n[jfrsort] {len(order)} test classes, sorted by mean {args.metric} (descending):")
    for t in order:
        print(f"  {mean[t]/1e6:12.1f} MB  {t}")
    print(f"\n[jfrsort] order written to {order_file}")
    print(f"[jfrsort] per-run metrics in {out}/run-*/metrics.json, table in {out}/metrics.csv")


if __name__ == "__main__":
    main()
