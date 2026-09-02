#!/usr/bin/env python3
"""jfrsort: sort a Maven project's test classes by JFR-measured metrics.

Pipeline: run `mvn test` N times with a JFR recording on every forked JVM and
a -javaagent (agent/) whose JUnit Platform listener emits one custom
jfrsort.TestClass event spanning each top-level test class. Each JFR event is
attributed to the test class whose time window contains it, on any thread.
The per-class metric is averaged over the N runs and the classes are emitted
sorted by it, descending.

The only metric implemented today is `alloc`: estimated allocated heap bytes
per test class, from jdk.ObjectAllocationSample event weights. The sort rule
matches csto2's alloc-sort: a stable sort of the initial order by the metric,
descending, so ties keep their initial relative order.
"""

import argparse
import bisect
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

TOOL_DIR = Path(__file__).resolve().parent
WINDOW_EVENT = "jfrsort.TestClass"

# metric name -> the JFR event to collect and the field holding the per-event value
METRICS = {
    "alloc": {"event": "jdk.ObjectAllocationSample", "value_field": "weight"},
}

TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$")
DUR_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")


def iso_ns(ts: str) -> int:
    """Epoch nanoseconds from a jfr print timestamp (nanosecond ISO-8601)."""
    m = TS_RE.match(ts)
    if not m:
        sys.exit(f"jfrsort: cannot parse timestamp {ts!r}")
    offset = "+00:00" if m.group(3) == "Z" else m.group(3)
    dt = datetime.fromisoformat(m.group(1) + offset)
    frac = (m.group(2) or "").ljust(9, "0")[:9]
    return int(dt.timestamp()) * 10**9 + int(frac)


def dur_ns(s: str) -> int:
    """Nanoseconds from a jfr print ISO-8601 duration (PT...S)."""
    m = DUR_RE.match(s)
    if not m:
        sys.exit(f"jfrsort: cannot parse duration {s!r}")
    hours, minutes, seconds = m.groups()
    total = (int(hours or 0) * 3600 + int(minutes or 0) * 60) * 10**9
    if seconds:
        whole, _, frac = seconds.partition(".")
        total += int(whole) * 10**9 + int(frac.ljust(9, "0")[:9])
    return total


def ensure_agent(mvn: str) -> Path:
    jar = TOOL_DIR / "agent/target/jfrsort-agent.jar"
    if not jar.exists():
        print("[jfrsort] building agent jar ...", flush=True)
        rc = subprocess.run([mvn, "-q", "-f", str(TOOL_DIR / "agent/pom.xml"), "package"]).returncode
        if rc != 0 or not jar.exists():
            sys.exit("jfrsort: agent build failed")
    return jar


def clean_reports(project: Path):
    for rep in project.rglob("target/surefire-reports"):
        shutil.rmtree(rep, ignore_errors=True)


def run_profiled(project: Path, run_dir: Path, mvn: str, agent_jar: Path,
                 maven_args: list[str]) -> tuple[Path, float]:
    """One `mvn test` run with the agent and JFR on every JVM."""
    jfr_dir = run_dir / "jfr"
    jfr_dir.mkdir(parents=True, exist_ok=True)
    clean_reports(project)
    env = dict(os.environ)
    env["JAVA_TOOL_OPTIONS"] = (
        f"-javaagent:{agent_jar} "
        "-XX:StartFlightRecording:settings=profile,"
        "jdk.ObjectAllocationSample#throttle=1000/s,"
        f"dumponexit=true,filename={jfr_dir}/"
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


def report_classes(project: Path) -> set[str]:
    """Top-level test classes named by the Surefire XML reports (cross-check only)."""
    classes = set()
    for rep in project.rglob("target/surefire-reports/TEST-*.xml"):
        try:
            name = ElementTree.parse(rep).getroot().get("name")
        except ElementTree.ParseError:
            continue
        if name:
            classes.add(name.split("$", 1)[0])
    return classes


def parse_recording(jfr_bin: str, rec: Path, metric: dict) -> dict | None:
    """Windows + attributed metric values for one recording.

    Returns None when the recording holds no jfrsort.TestClass events (a JVM
    that ran no tests, e.g. the Maven launcher, which JAVA_TOOL_OPTIONS also
    reaches). Every metric event is attributed to the test class whose time
    window contains its timestamp, regardless of thread.
    """
    out = subprocess.run([jfr_bin, "print", "--json",
                          "--events", f"{WINDOW_EVENT},{metric['event']}", str(rec)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"jfrsort: jfr print failed on {rec}: {out.stderr.strip()}")
    events = json.loads(out.stdout)["recording"]["events"]

    windows = []                                   # (start_ns, end_ns, class)
    samples = []                                   # (ts_ns, value)
    for ev in events:
        vals = ev["values"]
        if ev["type"] == WINDOW_EVENT:
            start = iso_ns(vals["startTime"])
            windows.append((start, start + dur_ns(vals["duration"]), vals["testClass"]))
        else:
            samples.append((iso_ns(vals["startTime"]),
                            float(vals.get(metric["value_field"]) or 0)))
    if not windows:
        return None

    windows.sort()
    for (s1, e1, c1), (s2, _, c2) in zip(windows, windows[1:]):
        if s2 < e1:
            sys.exit(f"jfrsort: test windows of {c1} and {c2} overlap in {rec.name}; "
                     "parallel test execution is not supported")
    starts = [w[0] for w in windows]

    per_class: dict[str, float] = {}
    window_ns: dict[str, int] = {}
    for start, end, cls in windows:
        per_class.setdefault(cls, 0.0)
        window_ns[cls] = window_ns.get(cls, 0) + (end - start)

    unattributed = 0.0
    for ts, value in samples:
        i = bisect.bisect_right(starts, ts) - 1
        if i >= 0 and ts <= windows[i][1]:
            per_class[windows[i][2]] += value
        else:
            unattributed += value
    order = list(dict.fromkeys(w[2] for w in windows))   # execution order, deduped
    return {"per_class": per_class, "unattributed": unattributed,
            "window_ms": {c: round(ns / 1e6, 1) for c, ns in window_ns.items()},
            "order": order}


def collect_run(jfr_bin: str, jfr_dir: Path, metric: dict) -> dict:
    """Parse every recording of one run and merge the test-JVM results."""
    merged: dict[str, float] = {}
    window_ms: dict[str, float] = {}
    order: list[str] = []
    unattributed = 0.0
    kept, dropped = [], []
    for rec in sorted(jfr_dir.glob("*.jfr")):
        data = parse_recording(jfr_bin, rec, metric)
        if data is None:
            dropped.append(rec.name)
            continue
        kept.append(rec.name)
        unattributed += data["unattributed"]
        for cls, v in data["per_class"].items():
            merged[cls] = merged.get(cls, 0.0) + v
        for cls, ms in data["window_ms"].items():
            window_ms[cls] = window_ms.get(cls, 0.0) + ms
        order += [c for c in data["order"] if c not in order]
    if not kept:
        sys.exit(f"jfrsort: no recording in {jfr_dir} contained {WINDOW_EVENT} events. "
                 "The target must run its tests through the JUnit Platform "
                 "(JUnit 5, or JUnit 4 via the vintage engine).")
    return {"per_class": merged, "unattributed": unattributed, "window_ms": window_ms,
            "order": order, "recordings_kept": kept, "recordings_dropped": dropped}


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
    agent_jar = ensure_agent(args.mvn)

    runs = []
    tests_initial = None
    for i in range(1, args.runs + 1):
        run_dir = out / f"run-{i}"
        print(f"[jfrsort] run {i}/{args.runs}: mvn test with JFR ...", flush=True)
        jfr_dir, wall = run_profiled(project, run_dir, args.mvn, agent_jar, maven_args)
        data = collect_run(args.jfr_bin, jfr_dir, metric)
        data["wall_seconds"] = round(wall, 1)
        (run_dir / "metrics.json").write_text(json.dumps(data, indent=1))
        runs.append(data)

        reported = report_classes(project)
        if reported != set(data["order"]):
            print(f"[jfrsort] WARNING: run {i}: JFR windows and Surefire reports disagree "
                  f"(windows only: {sorted(set(data['order']) - reported)}, "
                  f"reports only: {sorted(reported - set(data['order']))})", file=sys.stderr)
        if tests_initial is None:
            tests_initial = data["order"]        # run 1 defines the initial order
        elif set(data["order"]) != set(tests_initial):
            print(f"[jfrsort] WARNING: run {i} test set differs from run 1; using the union",
                  file=sys.stderr)
            tests_initial += [t for t in data["order"] if t not in tests_initial]

        attr = sum(data["per_class"].values())
        total = attr + data["unattributed"]
        pct = 100.0 * attr / total if total else 0.0
        print(f"[jfrsort] run {i}: {wall:.0f}s, {len(data['recordings_kept'])} test JVM(s), "
              f"{len(data['order'])} classes, {pct:.1f}% of {args.metric} weight attributed",
              flush=True)

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
