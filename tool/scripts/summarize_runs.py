#!/usr/bin/env python3
#
# usage: python3 scripts/summarize_runs.py <runs_dir> <summary_dir> [modules] [workers] [--force]
# e.g.   python3 scripts/summarize_runs.py runs/ summary/ \
#                                          "" 8 --all-runs
#        python3 scripts/summarize_runs.py ... "29 1685" 32
#
# One directory per order, holding the order that was run and what it cost:
#
#   <summary_dir>/29/0/order_1/order.txt    the order, one test per line
#   <summary_dir>/29/0/order_1/tests.csv    one row per test, in that order
#
# mirroring <runs_dir>/29/0/order_1/run_{1,2,3,...}/surefire-reports/.
#
# Runtime and result come from the surefire reports, read through
# scripts/surefire_times.py. That module is the only reader of those reports;
# this output is a rendering of it, never a source anything computes runtime
# from. Timings are from the plain runs only -- jfr_run_* are excluded, because
# recording inflates the very thing being measured.
#
# columns: position,test,runs,times,avg_time,statuses,status
#   runs             how many repetitions recorded this test (3, 4, 5, ...)
#   times, statuses  one value per repetition, ";"-joined, in run order
#   avg_time         the mean of times
#   status           the worst repetition: FAIL beats SKIP beats PASS
#   Only times and statuses are lists; "," separates columns, ";" separates reps.
#
# --jfr summarizes the jfr_run_* repetitions instead, into tests_jfr.csv beside
# tests.csv. Their times are inflated by the recording, so they are kept in a
# separate file and never mixed into tests.csv; the pair is what gives the JFR
# overhead. Profiled runs exist at v0 and the historical versions only.
#
# --all-runs appends four columns and narrows four existing ones:
#
#   times, avg_time, statuses, status   cover run_1..run_3 ONLY, so the
#                     three-repetition figures the campaign was analysed on keep
#                     their values unchanged when repetitions 4 and 5 arrive
#   runs              counts EVERY repetition present, so the row still says how
#                     many there are
#   times_all_runs    one value per repetition, every repetition, ";"-joined
#   statuses_all_runs likewise
#   average_all_runs  mean over every repetition
#   result_all_runs   worst status over every repetition
#
# Nothing is lost: the original block is the three-repetition campaign as it was
# analysed, and the four new columns are the full picture beside it.
#
# Without the flag every column keeps its original meaning and the header is
# unchanged, so a pass that predates repetition 4 rewrites byte-identical files.
# A test that appears in no run_1..run_3 -- possible, a class can emit zero test
# cases in one repetition and some in another -- gets empty times, avg_time,
# statuses and status rather than numbers quietly borrowed from a later
# repetition; its all_runs columns are still filled.
#
# Rows are what the suite actually ran, in the order it ran them, so "position"
# is a real execution position. order.txt is the order as issued, so it can be
# longer than the csv. Two kinds of row are absent on purpose:
#   - a test the order asked for that the build never ran. An order file is the
#     order requested, not a log of what executed, and in some modules the two
#     differ sharply (1497 asks for 3382 tests; maven runs 866). Keeping such a
#     test as an empty row would number every later test wrongly.
#   - a class-level record, which surefire writes with no method name when a
#     whole class is skipped or errors before any method runs. It is not a test
#     and sits at no position. surefire_times.total() still counts its seconds.
#
# Already-summarized orders are skipped, so a second pass only does what is new.
# Pass --force to rewrite them.

import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surefire_times as S


BASE_RUNS = ("run_1", "run_2", "run_3")
JFR_BASE_RUNS = ("jfr_run_1", "jfr_run_2", "jfr_run_3")


def jfr_run_dirs(order_dir):
    """The PROFILED repetitions, jfr_run_1, jfr_run_2, ... in order.

    surefire_times.run_dirs never returns these, because recording inflates the
    runtime and a profiled time must never enter a timing average. They are
    summarized separately, into tests_jfr.csv, so the JFR overhead can be
    measured by comparing the two files.
    """
    try:
        names = os.listdir(order_dir)
    except OSError:
        return []
    return sorted((n for n in names if n.startswith("jfr_run_")),
                  key=lambda n: (len(n), n))


def keyed_profile(order_dir, jfr=False):
    """[(test, {run_name: (seconds, status)})] in execution order.

    Why not S.order_profile: it returns parallel lists and drops a test from a
    repetition it is missing from, so index r stops meaning "repetition r" as
    soon as one run's reports are short. That happens for real -- module 20's
    IPv6 unicast datagram classes emit zero test cases in 45.6% of runs, so
    their tests have one fewer entry than their neighbours. Keying by run name
    makes "run_1..run_3" mean exactly that, whatever is missing.
    """
    seq, by_test = [], {}
    for name in (jfr_run_dirs(order_dir) if jfr else S.run_dirs(order_dir)):
        placed, _ = S.in_order(os.path.join(order_dir, name))
        for test, secs, state in placed:
            if test not in by_test:
                by_test[test] = {}
                seq.append(test)
            by_test[test][name] = (secs, state)
    return [(t, by_test[t]) for t in seq]


def agg(vals):
    """(mean seconds, worst status) over [(seconds, status), ...]."""
    if not vals:
        return "", ""
    worst = vals[0][1]
    for _, state in vals[1:]:
        worst = S.worse(worst, state)
    return round(sum(v for v, _ in vals) / len(vals), 4), worst


def write_order(order_dir, out_dir):
    """The order as it was issued, copied beside the csv."""
    runs = S.run_dirs(order_dir)
    tests = S.order_file(os.path.join(order_dir, runs[0])) if runs else []
    if not tests:
        return
    tmp = os.path.join(out_dir, "order.txt.part")
    with open(tmp, "w") as f:
        f.write("\n".join(tests) + "\n")
    os.replace(tmp, os.path.join(out_dir, "order.txt"))


def in_run_order(per_run):
    """Run names of one test, run_1 before run_2 before run_10."""
    return sorted(per_run, key=lambda n: (len(n), n))


def write_csv(seq, out_csv, all_runs=False, base=BASE_RUNS):
    head = ["position", "test", "runs", "times", "avg_time", "statuses", "status"]
    if all_runs:
        head += ["times_all_runs", "statuses_all_runs",
                 "average_all_runs", "result_all_runs"]
    tmp = out_csv + ".part"
    with open(tmp, "w", newline="") as f:
        # LF, not csv.writer's default CRLF: the stray \r lands on the last
        # column, so awk -F, and cut read "PASS\r" and every comparison against
        # the 3-run block fails. csv.reader and pandas never saw it; shell did.
        w = csv.writer(f, lineterminator="\n")
        w.writerow(head)
        for i, (test, per_run) in enumerate(seq, 1):
            names = in_run_order(per_run)
            every = [per_run[n] for n in names]
            shown = [per_run[n] for n in names if n in base] if all_runs else every
            avg, status = agg(shown)
            row = [i, test, len(every),
                   ";".join("%.3f" % v for v, _ in shown), avg,
                   ";".join(st for _, st in shown), status]
            if all_runs:
                row += [";".join("%.3f" % v for v, _ in every),
                        ";".join(st for _, st in every)] + list(agg(every))
            w.writerow(row)
    os.replace(tmp, out_csv)


def summarize(job):
    order_dir, out_dir, force, all_runs, jfr = job
    out_csv = os.path.join(out_dir, "tests_jfr.csv" if jfr else "tests.csv")
    if not force and os.path.exists(out_csv):
        return "skipped"
    if not (jfr_run_dirs(order_dir) if jfr else S.run_dirs(order_dir)):
        return "no jfr runs" if jfr else "no plain runs"
    seq = keyed_profile(order_dir, jfr)
    if not seq:
        return "no reports"
    os.makedirs(out_dir, exist_ok=True)
    if not jfr:
        write_order(order_dir, out_dir)
    write_csv(seq, out_csv, all_runs, JFR_BASE_RUNS if jfr else BASE_RUNS)
    return "written"


def jobs_for(runs_dir, summary_dir, modules, force, all_runs, jfr=False):
    for module in sorted(os.listdir(runs_dir)):
        if modules and module not in modules:
            continue
        mdir = os.path.join(runs_dir, module)
        if not os.path.isdir(mdir):
            continue
        for version in sorted(os.listdir(mdir)):
            vdir = os.path.join(mdir, version)
            if not os.path.isdir(vdir):
                continue
            for order in sorted(os.listdir(vdir)):
                if not order.startswith("order_"):
                    continue
                yield (os.path.join(vdir, order),
                       os.path.join(summary_dir, module, version, order),
                       force, all_runs, jfr)


def run_pass(todo, workers, tally):
    """One pass over the work at a given width. Returns how many jobs finished
    and whether a worker was killed before the rest could run. Results arrive in
    submission order, so the finished count is exactly how far the list got."""
    done = 0
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for res in pool.map(summarize, todo, chunksize=16):
                tally[res] = tally.get(res, 0) + 1
                done += 1
                if done % 2000 == 0:
                    print("  %d/%d %s" % (done, len(todo), tally), flush=True)
    except BrokenProcessPool:
        return done, True
    return done, False


def main(runs_dir, summary_dir, modules="", workers=32, *flags):
    given = tuple(flags) + (modules, str(workers))
    force = "--force" in given
    all_runs = "--all-runs" in given
    jfr = "--jfr" in given
    mods = set(modules.split()) if modules and not modules.startswith("--") else set()
    todo = list(jobs_for(runs_dir, summary_dir, mods, force, all_runs, jfr))
    if jfr:
        print("profiled runs only -> tests_jfr.csv, never tests.csv")
    if all_runs:
        print("appending average_all_runs and result_all_runs; "
              "avg_time and status cover run_1..run_3")
    print("%d order dirs to consider -> %s" % (len(todo), summary_dir))

    tally = {}
    for width in (int(workers), 8, 4, 2, 1):
        if not todo:
            break
        done, killed = run_pass(todo, width, tally)
        if not killed:
            print("done: %s" % tally)
            return
        # A worker was killed outright. One order dir of module 3320 holds ~10 GB
        # of captured stdout, and reading a single one of its reports costs
        # ~2.5 GB, so a wide pool trips the per-user memory cap this login node
        # enforces (8 GiB). Narrow the pool and carry on from where it stopped.
        todo = todo[done:]
        print("  a worker was killed; %d order dirs left, narrowing the pool"
              % len(todo), flush=True)
    print("still failing with one worker: %d order dirs unsummarized" % len(todo))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: summarize_runs.py <runs_dir> <summary_dir> "
                 "[modules] [workers] [--force] [--all-runs] [--jfr]")
    main(*sys.argv[1:])
