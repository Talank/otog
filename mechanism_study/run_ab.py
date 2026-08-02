#!/usr/bin/env python3
"""Run complete test orders as an interleaved Surefire A/B experiment."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_EXTENSION = (
    Path.home()
    / ".m2/repository/fun/jvm/surefire/flaky/"
    / "surefire-changing-maven-extension/1.0-SNAPSHOT/"
    / "surefire-changing-maven-extension-1.0-SNAPSHOT.jar"
)
DEFAULT_AGENT = Path(__file__).resolve().parents[1] / "csto2/target/csto2-agent.jar"

TIME_L_FIELDS = {
    "maximum resident set size": "max_rss_bytes",
    "page reclaims": "page_reclaims",
    "page faults": "page_faults",
    "block input operations": "block_inputs",
    "block output operations": "block_outputs",
    "voluntary context switches": "voluntary_context_switches",
    "involuntary context switches": "involuntary_context_switches",
    "instructions retired": "instructions_retired",
    "cycles elapsed": "cycles_elapsed",
    "peak memory footprint": "peak_memory_footprint_bytes",
}


def order_arg(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if not separator or not name or not path:
        raise argparse.ArgumentTypeError("--order must be NAME=PATH")
    return name, Path(path).resolve()


def read_order(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def parse_time_l(log: Path) -> dict[str, int]:
    metrics: dict[str, int] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.fullmatch(r"\s*(\d+)\s+(.+)", line)
        if match and match.group(2) in TIME_L_FIELDS:
            metrics[TIME_L_FIELDS[match.group(2)]] = int(match.group(1))
    return metrics


def parse_reports(reports: Path, expected: list[str]) -> tuple[float, list[dict]]:
    rows: list[dict] = []
    by_name: dict[str, dict] = {}
    if reports.is_dir():
        for path in reports.glob("TEST-*.xml"):
            try:
                root = ET.parse(path).getroot()
            except (ET.ParseError, OSError):
                continue
            if root.tag != "testsuite":
                continue
            name = root.attrib.get("name", "")
            row = {
                "test": name,
                "runtime_ms": float(root.attrib.get("time", 0)) * 1000.0,
                "tests": int(root.attrib.get("tests", 0)),
                "failures": int(root.attrib.get("failures", 0))
                + int(root.attrib.get("errors", 0)),
                "testcases": [
                    {
                        "class": case.attrib.get("classname", ""),
                        "method": case.attrib.get("name", ""),
                        "runtime_ms": float(case.attrib.get("time", 0)) * 1000.0,
                        "failures": len(case.findall("failure")) + len(case.findall("error")),
                    }
                    for case in root.findall("testcase")
                ],
            }
            by_name[name] = row

    # Surefire writes one XML report for a test class even when the order file
    # contains method selectors. Count each class report once. Keep read_order()
    # method-aware so the A/B set check still detects a missing or extra method.
    expected_classes = list(dict.fromkeys(test.split("#", 1)[0] for test in expected))
    missing = []
    for test in expected_classes:
        # JUnit can write one report for the top-level container and more reports
        # for its nested containers. The top-level report can contain zero tests,
        # so always aggregate all of them.
        matching = [
            value
            for key, value in by_name.items()
            if key == test or key.startswith(test + "$")
        ]
        if not matching:
            missing.append(test)
        else:
            rows.append(
                {
                    "test": test,
                    "runtime_ms": sum(item["runtime_ms"] for item in matching),
                    "tests": sum(item["tests"] for item in matching),
                    "failures": sum(item["failures"] for item in matching),
                    "testcases": [
                        case for item in matching for case in item["testcases"]
                    ],
                }
            )
    if missing:
        raise RuntimeError(
            f"{len(missing)} ordered classes produced no Surefire report; first: {missing[:5]}"
        )
    return sum(row["runtime_ms"] for row in rows), rows


def summarize(records: list[dict], arms: list[str]) -> None:
    print("\nSummary (Surefire XML suite time)")
    medians: dict[str, float] = {}
    for arm in arms:
        values = [record["suite_runtime_ms"] for record in records if record["arm"] == arm]
        medians[arm] = statistics.median(values)
        print(
            f"  {arm:16s} median={medians[arm]:9.1f} ms "
            f"min={min(values):9.1f} max={max(values):9.1f}"
        )
    baseline = arms[0]
    for arm in arms[1:]:
        speedup = (medians[baseline] - medians[arm]) / medians[baseline] * 100.0
        print(f"  {arm} vs {baseline}: {speedup:+.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--order", action="append", required=True, type=order_arg)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--jvm-args", default="")
    parser.add_argument(
        "--profile-jfr",
        action="store_true",
        help="record a profile-settings JFR with CSTO2 test-class interval events",
    )
    parser.add_argument(
        "--instrument",
        action="store_true",
        help="attach the CSTO2 boundary agent without enabling JFR",
    )
    parser.add_argument(
        "--jfr-settings",
        default="profile",
        help="JFR settings name or absolute .jfc path (used with --profile-jfr)",
    )
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--mvn", default="mvn")
    parser.add_argument("--extension", type=Path, default=DEFAULT_EXTENSION)
    parser.add_argument("--maven-arg", action="append", default=[])
    parser.add_argument(
        "--os-time",
        action="store_true",
        help="wrap Maven with macOS /usr/bin/time -l and record process-tree OS counters",
    )
    args = parser.parse_args()

    args.project = args.project.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.extension.is_file():
        raise SystemExit(f"Surefire test-order extension not found: {args.extension}")

    arms = [name for name, _ in args.order]
    if len(set(arms)) != len(arms):
        raise SystemExit("order arm names must be unique")
    orders = {name: path for name, path in args.order}
    expected = {name: read_order(path) for name, path in args.order}
    if len({tuple(sorted(value)) for value in expected.values()}) != 1:
        raise SystemExit("all arms must contain exactly the same test classes")

    records: list[dict] = []
    jsonl = args.out / "runs.jsonl"
    if jsonl.exists():
        raise SystemExit(f"refusing to overwrite existing experiment: {jsonl}")

    for round_number in range(args.rounds):
        sequence = arms if round_number % 2 == 0 else list(reversed(arms))
        for slot, arm in enumerate(sequence):
            run_id = f"{round_number:02d}-{slot:02d}-{arm}"
            log = args.out / f"{run_id}.log"
            cmd = [
                args.mvn,
                "initialize",
                "surefire:test",
                f"-Dmaven.ext.class.path={args.extension.resolve()}",
                "-Dsurefire.runOrder=testorder",
                f"-Dtest={orders[arm]}",
                "-Dmaven.build.cache.enabled=false",
                "-Dmaven.test.failure.ignore=true",
                "-DforkCount=1",
                "-DreuseForks=true",
                *args.maven_arg,
            ]
            if args.os_time:
                cmd = ["/usr/bin/time", "-l", *cmd]
            env = os.environ.copy()
            if args.java_home:
                env["JAVA_HOME"] = str(args.java_home.resolve())
            # headless: the fork must never register as a macOS GUI app and steal window focus
            fork_args = f"-Djava.awt.headless=true -Dapple.awt.UIElement=true {args.jvm_args or ''}".strip()
            if args.profile_jfr or args.instrument:
                if not args.agent.is_file():
                    raise SystemExit(f"CSTO2 profiling agent not found: {args.agent}")
                facts = args.out / f"{run_id}.facts.jsonl"
                profiling_args = (
                    f"-javaagent:{args.agent.resolve()}=out={facts},order={run_id}"
                )
                if args.profile_jfr:
                    recording = args.out / f"{run_id}.jfr"
                    settings = args.jfr_settings
                    settings_path = Path(settings)
                    if settings_path.exists():
                        settings = str(settings_path.resolve())
                    profiling_args += (
                        " -XX:FlightRecorderOptions=stackdepth=256 "
                        "-XX:StartFlightRecording="
                        f"name=csto2,settings={settings},filename={recording},dumponexit=true"
                    )
                fork_args = (
                    profiling_args if not fork_args else f"{profiling_args} {fork_args}"
                )
            if fork_args:
                env["KP_ARGLINE"] = fork_args

            print(f"[{run_id}] {' '.join(shlex.quote(part) for part in cmd)}", flush=True)
            started = time.monotonic()
            with log.open("wb") as stream:
                completed = subprocess.run(
                    cmd,
                    cwd=args.project,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            wall_ms = (time.monotonic() - started) * 1000.0
            if completed.returncode != 0:
                raise SystemExit(
                    f"Maven exited with status {completed.returncode}; "
                    f"reports can be stale, so this run is invalid; inspect {log}"
                )
            suite_ms, rows = parse_reports(
                args.project / "target/surefire-reports", expected[arm]
            )
            classes_file = args.out / f"{run_id}.classes.jsonl"
            with classes_file.open("w", encoding="utf-8") as stream:
                for position, row in enumerate(rows):
                    stream.write(
                        json.dumps(
                            {"position": position, **row},
                            sort_keys=True,
                        )
                        + "\n"
                    )
            failures = sum(row["failures"] for row in rows)
            record = {
                "round": round_number,
                "slot": slot,
                "arm": arm,
                "order": str(orders[arm]),
                "jvm_args": args.jvm_args,
                "profile_jfr": args.profile_jfr,
                "instrument": args.instrument,
                "maven_exit": completed.returncode,
                "wall_ms": wall_ms,
                **(parse_time_l(log) if args.os_time else {}),
                "suite_runtime_ms": suite_ms,
                "failures": failures,
                "classes": len(rows),
                "class_results": str(classes_file),
                "log": str(log),
            }
            with jsonl.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
            records.append(record)
            print(
                f"[{run_id}] suite={suite_ms:.1f} ms wall={wall_ms:.1f} ms "
                f"exit={completed.returncode} failures={failures}",
                flush=True,
            )
            if failures:
                raise SystemExit(f"non-green run; inspect {log}")

    summarize(records, arms)


if __name__ == "__main__":
    main()
