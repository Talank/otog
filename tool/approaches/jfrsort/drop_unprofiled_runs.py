#!/usr/bin/env python3
#
# usage: python3 approaches/jfrsort/drop_unprofiled_runs.py <export_dir>
# e.g.   python3 approaches/jfrsort/drop_unprofiled_runs.py /scratch/tbaral/jfrsort_work/1117/past_49/export
#
# Drops the runs whose recordings carry no jfrsort.TestClass event, in place,
# from an export made by scripts/export_jfr.py.
#
# The agent writes that event from a JUnit Platform listener, once per test
# class. A run whose test fork died, or whose recording was truncated, keeps
# its allocation events but loses the markers that say which class was running
# -- and jfrsort stops at the first such run rather than skipping it. Dropping
# them here leaves the sort with the runs it can actually read, and says how
# many it lost, so a thin input set is visible rather than silent.
#
# The marker is looked for in the file's bytes: the event name is in every
# chunk's metadata, so a recording that has one is matched without parsing.
#
# in : <export_dir>/collect.json and the run directories it names
# out: the same collect.json with the unreadable runs removed, and the count
#      kept and dropped on stdout; exit 1 if nothing readable is left

import json
import os
import sys

MARKER = b"jfrsort.TestClass"
CHUNK = 1 << 20


def has_marker(path):
    """True if the file's bytes contain the event name anywhere."""
    tail = b""
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(CHUNK)
                if not block:
                    return False
                if MARKER in tail + block:
                    return True
                tail = block[-len(MARKER):]
    except OSError:
        return False


def profiled(run_dir):
    jfr = os.path.join(run_dir, "jfr")
    try:
        names = os.listdir(jfr)
    except OSError:
        return False
    return any(n.endswith(".jfr") and has_marker(os.path.join(jfr, n)) for n in names)


def main(export_dir):
    manifest = os.path.join(export_dir, "collect.json")
    with open(manifest) as f:
        data = json.load(f)

    keep, dropped = [], []
    for run in data["runs"]:
        (keep if profiled(os.path.join(export_dir, run["dir"])) else dropped).append(run)

    if not keep:
        sys.exit("  no run in %s has jfrsort.TestClass events -- this suite does "
                 "not run through the JUnit Platform, so jfrsort cannot rank it"
                 % export_dir)

    if dropped:
        for run in dropped:
            # hardlinked recordings; removing the export copy keeps the runs dir intact
            for root, _, files in os.walk(os.path.join(export_dir, run["dir"]), topdown=False):
                for name in files:
                    os.unlink(os.path.join(root, name))
                os.rmdir(root)
        data["runs"] = keep
        with open(manifest, "w") as f:
            json.dump(data, f, indent=1)

    print("  %d run(s) readable, %d dropped for having no jfrsort events"
          % (len(keep), len(dropped)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: drop_unprofiled_runs.py <export_dir>")
    main(sys.argv[1])
