#!/usr/bin/env python3
#
# usage: python3 scripts/same_batch_board.py <runs_dir> [version] [workers]
#
# Score every approach's order against the random orders collected in the SAME
# window, and refuse to compare across windows.
#
# Why: approach and collection date are collinear in the main campaign -- random
# came from 09-01, position_sort 09-14, z3 09-23, jfrsort 09-25, warmsort 09-26,
# combosort 09-27 -- and the day moves runtime by up to 27% on orders whose
# composition never changed. A pooled percentile therefore measures the day as
# much as the order. Grouping by the hour a run finished removes that: an order
# is only ranked against references from its own hour, and an order with no
# same-hour reference is reported as unscorable rather than scored wrongly.
#
# Runtime is surefire seconds via surefire_times, the one reader of those reports.
# Plain runs only; a jfr_run_* is never counted.

import collections
import datetime
import os
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surefire_times as S

# A name here groups every input set of that approach into one family, the way
# position_sort_past_24 and position_sort_v0_99 both score as "position_sort".
# An order whose family is not listed is reported as unscorable under its own
# name rather than folded into the random reference.
APPROACHES = ("position_sort", "z3", "jfrsort", "warmsort", "combosort", "agentic")

# amd060 runs 5x to 10.8x slower than its siblings on IO-heavy modules -- module
# 3613 reaches 7,300 s there against a 519 s median. Every approach feeder already
# excludes it, but the v0 random campaign ran before the exclusion existed, so its
# reference distribution carries 34 such runs out of 3,900. They are dropped here
# so the reference is not inflated by hardware the approaches never ran on.
BAD_NODES = ("amd059", "amd060", "amd045")


def node_of(run_dir):
    try:
        with open(os.path.join(run_dir, "node.txt")) as f:
            return f.read().strip().split(".")[0]
    except OSError:
        return ""


def kind(order_dir):
    """Which family an order dir belongs to. Only order_<digits> is random.

    Named by what it is, not by matching the five known approaches: orders/ also
    holds an ml_* family (5 variants per module-version) that has never been run,
    and a substring test would have filed those under "random" and quietly put
    them in the reference distribution. Anything not order_<digits> is returned
    under its own name, so a new family shows up as unscorable rather than as
    reference data.
    """
    rest = order_dir[6:] if order_dir.startswith("order_") else order_dir
    if rest.isdigit():
        return "random"
    for a in APPROACHES:            # position_sort before z3: its name has a _
        if rest.startswith(a):
            return a
    return rest


def score_one(job):
    """(module, approach, order, seconds, hour) for one run dir."""
    runs_dir, module, version, od, run = job
    d = os.path.join(runs_dir, module, version, od, run)
    status = os.path.join(d, "status")
    if not os.path.exists(status):
        return None
    if node_of(d) in BAD_NODES:
        return None
    hour = datetime.datetime.fromtimestamp(os.stat(status).st_mtime).strftime("%Y-%m-%d %H")
    secs = S.total(d)
    return (module, kind(od), od, secs, hour) if secs > 0 else None


def jobs_for(runs_dir, version):
    out = []
    for module in sorted(os.listdir(runs_dir)):
        vd = os.path.join(runs_dir, module, version)
        if not os.path.isdir(vd):
            continue
        for od in sorted(os.listdir(vd)):
            if not od.startswith("order_"):
                continue
            for run in S.run_dirs(os.path.join(vd, od)):
                out.append((runs_dir, module, version, od, run))
    return out


def main(runs_dir, version="0", workers=12):
    jobs = jobs_for(runs_dir, str(version))
    print("scoring %d run dirs" % len(jobs), flush=True)
    res = []
    with ProcessPoolExecutor(max_workers=int(workers)) as pool:
        for r in pool.map(score_one, jobs, chunksize=8):
            if r:
                res.append(r)

    board = collections.defaultdict(list)
    skipped = collections.Counter()
    print("\n%-7s %-14s %6s %9s %5s  %s" % ("module", "approach", "n", "mean_pct", "ref", "window"))
    print("-" * 68)
    for module in sorted({r[0] for r in res}, key=lambda m: (len(m), m)):
        rows = [r for r in res if r[0] == module]
        # group references by window; an approach is scored only inside its own
        by_hour = collections.defaultdict(list)
        for r in rows:
            if r[1] == "random":
                by_hour[r[4]].append(r[3])
        for a in APPROACHES:
            for hour in sorted({r[4] for r in rows if r[1] == a}):
                ref = sorted(by_hour.get(hour, []))
                vals = [r[3] for r in rows if r[1] == a and r[4] == hour]
                if len(ref) < 5:
                    skipped[a] += len(vals)
                    continue
                pcts = [100.0 * sum(1 for x in ref if x < v) / len(ref) for v in vals]
                board[a] += pcts
                print("%-7s %-14s %6d %9.1f %5d  %s" % (module, a, len(vals), st.mean(pcts), len(ref), hour))

    print("-" * 68)
    print("SAME-BATCH mean percentile (50 = no better than random):")
    for a in sorted(board, key=lambda a: st.mean(board[a])):
        print("  %-14s %5.1f   (n=%d)" % (a, st.mean(board[a]), len(board[a])))
    if skipped:
        print("\nunscorable -- no same-window random reference:")
        for a, n in sorted(skipped.items()):
            print("  %-14s %d runs" % (a, n))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: same_batch_board.py <runs_dir> [version] [workers]")
    main(*sys.argv[1:4])
