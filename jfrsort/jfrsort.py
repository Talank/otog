#!/usr/bin/env python3
"""jfrsort: sort a Maven project's test classes by JFR-measured metrics.

Two phases, run separately:

  jfrsort.py collect --project DIR [--runs N] [--order FILE ...] [--random K]
                     [--seed S] [--clean] [--out DIR]
  jfrsort.py sort    [--out DIR] [--metric alloc]

`collect` runs the suite with a JFR recording on every forked JVM and a
-javaagent (agent/) whose JUnit Platform listener emits one custom
jfrsort.TestClass event spanning each top-level test class. Recordings and
build logs are organized under the output directory. Every invocation APPENDS
to that directory (run numbers continue; collect.json logs each run), so an
outer script can call it repeatedly and `sort` aggregates everything collected
so far; --clean wipes the directory first. --order FILE (repeatable) runs the
given order — one test class per line — through the surefire testorder fork
(installed in ~/.m2; its extension is loaded per invocation); --random K
generates K shuffled orders from the project's class list and runs them the
same way. --runs is the number of repeats per order.

`sort` parses the collected recordings: each JFR event is attributed to the
test class whose time window contains it, on any thread; the per-class metric
is averaged over all collected runs and the classes are written sorted by it,
descending. The only metric today is `alloc` (estimated allocated heap bytes,
from jdk.ObjectAllocationSample event weights); the sort rule matches csto2's
alloc-sort: a stable sort of the initial order, so ties keep their order.
"""

import argparse
import bisect
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
WINDOW_EVENT = "jfrsort.TestClass"
MANIFEST = "collect.json"

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


# ---------------------------------------------------------------- collect ---

def ensure_agent(mvn: str) -> Path:
    jar = TOOL_DIR / "agent/target/jfrsort-agent.jar"
    if not jar.exists():
        print("[jfrsort] building agent jar ...", flush=True)
        rc = subprocess.run([mvn, "-q", "-f", str(TOOL_DIR / "agent/pom.xml"), "package"]).returncode
        if rc != 0 or not jar.exists():
            sys.exit("jfrsort: agent build failed")
    return jar


def find_surefire_ext(override: str | None) -> Path:
    """The surefire testorder fork's Maven extension jar, installed in ~/.m2."""
    if override:
        p = Path(override)
        if not p.is_file():
            sys.exit(f"jfrsort: --surefire-ext {p} not found")
        return p
    base = Path.home() / ".m2/repository/fun/jvm/surefire/flaky/surefire-changing-maven-extension"
    jars = sorted(base.rglob("surefire-changing-maven-extension-*.jar")) if base.is_dir() else []
    if not jars:
        sys.exit("jfrsort: ordered runs need the surefire testorder fork installed "
                 "(mvn install -DskipTests -Drat.skip -Denforcer.skip in the fork), "
                 "or pass --surefire-ext <jar>")
    return jars[-1]


def mvn_command(mvn: str, order: str | None, ext: Path | None, maven_args: list[str]) -> list[str]:
    """Plain `mvn test`; with an order file, the surefire testorder fork's form,
    loading its extension for this invocation only (-Dmaven.ext.class.path)."""
    if order is None:
        return [mvn, "-B", "test", *maven_args]
    return [mvn, "-B", "test", f"-Dmaven.ext.class.path={ext}",
            "-Dsurefire.runOrder=testorder", f"-Dtest={order}", *maven_args]


def run_profiled(project: Path, run_dir: Path, cmd: list[str], agent_jar: Path) -> float:
    """One profiled suite run; recordings land in <run_dir>/jfr. Returns wall seconds."""
    jfr_dir = run_dir / "jfr"
    jfr_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["JAVA_TOOL_OPTIONS"] = (
        f"-javaagent:{agent_jar} "
        "-XX:StartFlightRecording:settings=profile,"
        "jdk.ObjectAllocationSample#throttle=1000/s,"
        # events behind the PROBO metric set (Baz/Lam/Shi, ISSTA 2026): the
        # profile preset's thresholds suppress these events almost entirely
        "jdk.Compilation#threshold=0ms,"
        "jdk.ClassLoad#enabled=true,"
        "jdk.FileRead#threshold=0ms,jdk.FileWrite#threshold=0ms,"
        "jdk.SocketRead#threshold=0ms,jdk.SocketWrite#threshold=0ms,"
        "jdk.JavaMonitorEnter#threshold=0ms,jdk.ThreadSleep#threshold=0ms,"
        f"dumponexit=true,filename={jfr_dir}/"
    )
    log = run_dir / "mvn.log"
    t0 = time.time()
    with open(log, "w") as lf:
        rc = subprocess.run(cmd, cwd=project, env=env,
                            stdout=lf, stderr=subprocess.STDOUT).returncode
    wall = time.time() - t0
    if rc != 0:
        sys.exit(f"jfrsort: build failed (exit {rc}); see {log}. "
                 "The suite must be green before it can be profiled.")
    return wall


def load_manifest(out: Path) -> dict:
    p = out / MANIFEST
    if p.is_file():
        return json.loads(p.read_text())
    return {"project": None, "runs": []}


def save_manifest(out: Path, manifest: dict):
    (out / MANIFEST).write_text(json.dumps(manifest, indent=1))


def next_run_number(out: Path, label: str) -> int:
    nums = [int(p.name[4:]) for p in (out / label).glob("run-*") if p.name[4:].isdigit()]
    return max(nums, default=0) + 1


def class_list(out: Path, manifest: dict, jfr_bin: str) -> list[str] | None:
    """Test classes in execution order from the earliest default-order run."""
    for rec in manifest["runs"]:
        if rec["order"] is None:
            data = collect_run(jfr_bin, out / rec["dir"] / "jfr", METRICS["alloc"])
            return data["order"]
    return None


def cmd_collect(args):
    project = args.project.resolve()
    out = args.out.resolve()
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(out)
    if manifest["project"] and manifest["project"] != str(project):
        sys.exit(f"jfrsort: {out} holds runs of {manifest['project']}; "
                 "use another --out or --clean")
    manifest["project"] = str(project)
    agent_jar = ensure_agent(args.mvn)
    maven_args = args.maven_args.split()

    # arms: (label, order file or None)
    arms: list[tuple[str, Path | None]] = []
    for of in args.order or []:
        path = Path(of).resolve()
        if not path.is_file():
            sys.exit(f"jfrsort: order file {path} not found")
        arms.append((path.stem, path))
    if args.random:
        classes = class_list(out, manifest, args.jfr_bin)
        if classes is None:
            print("[jfrsort] no default-order run yet; collecting one to learn the class list",
                  flush=True)
            do_runs(project, out, manifest, [("default", None)], 1, args, agent_jar, maven_args)
            classes = class_list(out, manifest, args.jfr_bin)
        seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
        rng = random.Random(seed)
        existing = [int(r["arm"][7:]) for r in manifest["runs"]
                    if r["arm"].startswith("random-") and r["arm"][7:].isdigit()]
        k0 = max(existing, default=0) + 1
        (out / "orders").mkdir(exist_ok=True)
        for k in range(k0, k0 + args.random):
            order = list(classes)
            rng.shuffle(order)
            path = out / "orders" / f"random-{k}.txt"
            path.write_text("\n".join(order) + "\n")
            arms.append((f"random-{k}", path))
        print(f"[jfrsort] {args.random} random order(s) generated with seed {seed}", flush=True)
    if not arms:
        arms.append(("default", None))

    args.ext = find_surefire_ext(args.surefire_ext) if any(o for _, o in arms) else None
    do_runs(project, out, manifest, arms, args.runs, args, agent_jar, maven_args)
    n = len(manifest["runs"])
    print(f"[jfrsort] {out} now holds {n} run(s) — jfrsort.py sort --out {out}")


def do_runs(project, out, manifest, arms, runs, args, agent_jar, maven_args):
    """Rounds outside, arms inside: repeats of one arm are spread over time."""
    for _ in range(runs):
        for label, order in arms:
            i = next_run_number(out, label)
            run_dir = out / label / f"run-{i}"
            print(f"[jfrsort] collect {label} run {i} ...", flush=True)
            cmd = mvn_command(args.mvn, str(order) if order else None,
                              getattr(args, "ext", None), maven_args)
            wall = run_profiled(project, run_dir, cmd, agent_jar)
            if order is not None:
                shutil.copy(order, run_dir / "order.txt")
            manifest["runs"].append({
                "arm": label, "order": str(order) if order else None,
                "dir": f"{label}/run-{i}", "wall_seconds": round(wall, 1),
                "collected": datetime.now().isoformat(timespec="seconds")})
            save_manifest(out, manifest)       # progress survives interruption
            n = len(list((run_dir / "jfr").glob("*.jfr")))
            print(f"[jfrsort] collect {label} run {i}: {wall:.0f}s, {n} recording(s)", flush=True)


# ------------------------------------------------------------------- sort ---

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


def cmd_sort(args):
    out = args.out.resolve()
    metric = METRICS[args.metric]
    manifest_path = out / MANIFEST
    if not manifest_path.is_file():
        sys.exit(f"jfrsort: {manifest_path} not found — run `jfrsort.py collect` first")
    manifest = json.loads(manifest_path.read_text())
    if not manifest["runs"]:
        sys.exit("jfrsort: nothing collected yet")

    runs = []
    tests_initial = None
    # the initial order comes from the earliest default-order run, else the earliest run
    records = sorted(manifest["runs"], key=lambda r: (r["order"] is not None, r["collected"]))
    for rec in records:
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
        print(f"[jfrsort] {rec['dir']}: {len(data['order'])} classes, "
              f"{pct:.1f}% of {args.metric} weight attributed", flush=True)

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
    print(f"[jfrsort] per-run metrics in {out}/<arm>/run-*/metrics.json, table in {out}/metrics.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="run the suite under JFR and store recordings + logs")
    c.add_argument("--project", required=True, type=Path,
                   help="Maven project/module directory to run the suite in")
    c.add_argument("--runs", type=int, default=3,
                   help="repeats per order (default 3)")
    c.add_argument("--order", action="append", metavar="FILE",
                   help="test-order file (one class per line); repeatable. Needs the "
                        "surefire testorder fork installed in ~/.m2")
    c.add_argument("--random", type=int, metavar="K",
                   help="generate K shuffled orders from the class list and run each --runs times")
    c.add_argument("--seed", type=int, help="seed for --random (default: random, printed)")
    c.add_argument("--clean", action="store_true",
                   help="delete the output directory's collected runs first")
    c.add_argument("--surefire-ext", help="path to the fork's extension jar "
                                          "(default: newest under ~/.m2)")
    c.add_argument("--out", type=Path, default=Path(".jfrsort"))
    c.add_argument("--jfr-bin", default="jfr")
    c.add_argument("--mvn", default="mvn")
    c.add_argument("--maven-args", default="",
                   help="extra arguments appended to the mvn command line")
    c.set_defaults(func=cmd_collect)

    s = sub.add_parser("sort", help="parse collected recordings and write the sorted order")
    s.add_argument("--out", type=Path, default=Path(".jfrsort"))
    s.add_argument("--metric", choices=sorted(METRICS), default="alloc")
    s.add_argument("--jfr-bin", default="jfr")
    s.set_defaults(func=cmd_sort)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
