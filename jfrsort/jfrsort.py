#!/usr/bin/env python3
"""jfrsort: sort the test classes of a Maven project by a metric from JFR recordings.

  jfrsort.py sort [--out DIR] [--metric alloc] [--jfr-bin BIN]

The recordings come from the tool (../tool), which runs the suite in a container
with the agent in ../tool/agent attached. The agent's JUnit Platform listener
writes one jfrsort.TestClass event for each top-level test class, spanning the
class's execution. `sort` gives each metric event to the test class whose time
window contains it, on any thread, averages the per-class value over all runs
in the directory, and writes the classes sorted by it, descending. The sort is
stable on the order of the first run, so ties keep their order.

The directory has a file collect.json that lists the runs, and each run has a
directory jfr/ with its recordings. The tool's script scripts/export_jfr.py
writes such a directory from a module version's runs.

The metric `alloc` is the number of heap bytes each test class allocates: the
sum of the buffers handed out (jdk.ObjectAllocationInNewTLAB, field tlabSize)
and of the objects allocated outside a buffer (jdk.ObjectAllocationOutsideTLAB,
field allocationSize) inside the class window. It is a measurement, rounded to
whole buffers, and the two events exist on every JDK from 8 on.
"""

import argparse
import bisect
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WINDOW_EVENT = "jfrsort.TestClass"
MANIFEST = "collect.json"

# metric name -> the JFR events that carry it, and the field of each that holds the value
METRICS = {
    "alloc": {
        "jdk.ObjectAllocationInNewTLAB": "tlabSize",
        "jdk.ObjectAllocationOutsideTLAB": "allocationSize",
    },
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


def parse_recording(jfr_bin: str, rec: Path, metric: dict) -> dict | None:
    """Windows and attributed metric values for one recording.

    Returns None when the recording holds no jfrsort.TestClass events. That is
    a JVM that ran no tests, for example the Maven launcher, which the tool's
    JAVA_TOOL_OPTIONS also reach. Every metric event is attributed to the test
    class whose time window contains its timestamp, on any thread.
    """
    out = subprocess.run([jfr_bin, "print", "--json",
                          "--events", ",".join([WINDOW_EVENT, *metric]), str(rec)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"jfrsort: jfr print failed on {rec}: {out.stderr.strip()}")
    events = json.loads(out.stdout)["recording"]["events"]

    windows = []                                   # (start_ns, end_ns, class)
    samples = []                                   # (ts_ns, value)
    seen: dict[str, int] = {}                      # metric event type -> count
    for ev in events:
        vals = ev["values"]
        if ev["type"] == WINDOW_EVENT:
            start = iso_ns(vals["startTime"])
            windows.append((start, start + dur_ns(vals["duration"]), vals["testClass"]))
        else:
            seen[ev["type"]] = seen.get(ev["type"], 0) + 1
            samples.append((iso_ns(vals["startTime"]),
                            float(vals.get(metric[ev["type"]]) or 0)))
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
            "order": order, "events": seen}


def collect_run(jfr_bin: str, jfr_dir: Path, metric: dict) -> dict:
    """Parse every recording of one run and merge the test-JVM results."""
    merged: dict[str, float] = {}
    window_ms: dict[str, float] = {}
    order: list[str] = []
    events: dict[str, int] = {}
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
        for ev, n in data["events"].items():
            events[ev] = events.get(ev, 0) + n
        order += [c for c in data["order"] if c not in order]
    if not kept:
        sys.exit(f"jfrsort: no recording in {jfr_dir} contained {WINDOW_EVENT} events. "
                 "The target must run its tests through the JUnit Platform "
                 "(JUnit 5, or JUnit 4 via the vintage engine).")
    return {"per_class": merged, "unattributed": unattributed, "window_ms": window_ms,
            "order": order, "events": events,
            "recordings_kept": kept, "recordings_dropped": dropped}


def cmd_sort(args):
    out = args.out.resolve()
    metric = METRICS[args.metric]
    manifest_path = out / MANIFEST
    if not manifest_path.is_file():
        sys.exit(f"jfrsort: {manifest_path} not found")
    manifest = json.loads(manifest_path.read_text())
    if not manifest["runs"]:
        sys.exit("jfrsort: collect.json lists no runs")

    runs = []
    tests_initial = None
    for rec in manifest["runs"]:                 # the first run gives the initial order
        run_dir = out / rec["dir"]
        if not (run_dir / "jfr").is_dir():
            sys.exit(f"jfrsort: {run_dir}/jfr missing")
        data = collect_run(args.jfr_bin, run_dir / "jfr", metric)
        (run_dir / "metrics.json").write_text(json.dumps(data, indent=1))
        runs.append(data)
        if tests_initial is None:
            tests_initial = data["order"]
        elif set(data["order"]) != set(tests_initial):
            print(f"[jfrsort] WARNING: {rec['dir']} test set differs; using the union",
                  file=sys.stderr)
            tests_initial += [t for t in data["order"] if t not in tests_initial]
        attr = sum(data["per_class"].values())
        total = attr + data["unattributed"]
        pct = 100.0 * attr / total if total else 0.0
        sources = ", ".join(f"{n} {ev.split('.')[-1]}" for ev, n in sorted(data["events"].items()))
        print(f"[jfrsort] {rec['dir']}: {len(data['order'])} classes, "
              f"{pct:.1f}% of {args.metric} weight attributed, from {sources or 'no events'}",
              flush=True)

    # average over all runs; a class with no samples in a run counts 0 for that run
    mean = {t: sum(r["per_class"].get(t, 0.0) for r in runs) / len(runs)
            for t in tests_initial}

    # csto2 alloc-sort rule: stable sort of the initial order, metric descending
    order = sorted(tests_initial, key=lambda t: -mean[t])

    order_file = out / f"order-{args.metric}-sort.txt"
    order_file.write_text("\n".join(order) + "\n")
    with open(out / "metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["test", f"mean_{args.metric}", "runs_with_samples"])
        for t in order:
            vals = [r["per_class"].get(t, 0.0) for r in runs]
            w.writerow([t, round(mean[t]), sum(1 for v in vals if v > 0)])

    print(f"\n[jfrsort] {len(order)} test classes over {len(runs)} run(s), "
          f"sorted by mean {args.metric} (descending):")
    for t in order:
        print(f"  {mean[t]/1e6:12.1f} MB  {t}")
    print(f"\n[jfrsort] order written to {order_file}")
    print(f"[jfrsort] per-run metrics in {out}/<run>/metrics.json, table in {out}/metrics.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sort", help="parse the recordings and write the sorted order")
    s.add_argument("--out", type=Path, default=Path(".jfrsort"),
                   help="the directory with collect.json and the runs")
    s.add_argument("--metric", choices=sorted(METRICS), default="alloc")
    s.add_argument("--jfr-bin", default="jfr")
    s.set_defaults(func=cmd_sort)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
