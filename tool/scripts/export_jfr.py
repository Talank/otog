#!/usr/bin/env python3
#
# usage: python3 scripts/export_jfr.py <version_dir> <export_dir>
# e.g.   python3 scripts/export_jfr.py runs/1685/0 exports/1685/0
#
# Copies the recordings of one module version into a directory that holds
# nothing else, so that they can be moved off the machine and sorted with
# jfrsort. Each directory jfr_run_<n> that has status PASS and at least one
# .jfr file becomes one run: its recordings, its order.txt, and its wall time.
# The file collect.json lists the runs in the form that the sort command of
# jfrsort reads. All paths in it are relative to <export_dir>.
#
# in : a directory runs/<module>/<version>
# out: <export_dir>/collect.json, <export_dir>/order_<k>/jfr_run_<n>/jfr/*.jfr
#      and order.txt; the number of runs and the size on stdout

import json
import re
import shutil
import sys
from pathlib import Path

MANIFEST = "collect.json"


def passed(run_dir):
    try:
        return (run_dir / "status").read_text().split("\n")[0] == "PASS"
    except OSError:
        return False


def run_number(run_dir):
    match = re.fullmatch(r"jfr_run_(\d+)", run_dir.name)
    return int(match.group(1)) if match else None


def wall_seconds(run_dir):
    try:
        start, end = (run_dir / "wall_time.txt").read_text().split()
        return round(float(end) - float(start), 1)
    except (OSError, ValueError):
        return None


def profiled_runs(version_dir):
    # The sort command takes the initial test order from the first run in
    # the list. The list is sorted by order directory, then by run number.
    runs = []
    for order_dir in sorted(version_dir.glob("order_*"), key=lambda p: p.name):
        for run_dir in sorted(order_dir.glob("jfr_run_*"), key=lambda p: run_number(p) or 0):
            if run_number(run_dir) is None or not passed(run_dir):
                continue
            if any((run_dir / "jfr").glob("*.jfr")):
                runs.append(run_dir)
    return runs


def export_run(run_dir, version_dir, export_dir):
    rel = run_dir.relative_to(version_dir)
    dest = export_dir / rel
    (dest / "jfr").mkdir(parents=True, exist_ok=True)
    copied = 0
    for rec in (run_dir / "jfr").glob("*.jfr"):
        shutil.copyfile(rec, dest / "jfr" / rec.name)
        copied += rec.stat().st_size
    order = run_dir / "order.txt"
    if order.is_file():
        shutil.copyfile(order, dest / "order.txt")
    return {
        # "arm" is the key that jfrsort uses for the group name of a run.
        "arm": rel.parts[0],
        "order": f"{rel}/order.txt" if order.is_file() else None,
        "dir": str(rel),
        "wall_seconds": wall_seconds(run_dir),
    }, copied


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: python3 scripts/export_jfr.py <version_dir> <export_dir>")
    version_dir = Path(argv[1])
    export_dir = Path(argv[2])
    if not version_dir.is_dir():
        sys.exit(f"no directory at {version_dir}")

    runs = profiled_runs(version_dir)
    if not runs:
        sys.exit(f"no passed jfr_run_* with a recording under {version_dir}")

    export_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    total = 0
    for run_dir in runs:
        entry, copied = export_run(run_dir, version_dir, export_dir)
        entries.append(entry)
        total += copied
        print(f"  {entry['dir']}", flush=True)

    # The project name is the path runs/<module>/<version>.
    project = "/".join(version_dir.resolve().parts[-3:])
    (export_dir / MANIFEST).write_text(json.dumps({"project": project, "runs": entries}, indent=1))
    print(f"{len(entries)} run(s), {total / 1e6:.1f} MB of recordings, in {export_dir}")


if __name__ == "__main__":
    main(sys.argv)
