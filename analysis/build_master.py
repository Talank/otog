#!/usr/bin/env python3
"""summary_merged_runs/ -> master.csv: one row per module-version, one column
per order that ran there.

    python3 analysis/build_master.py [summary_dir] [out_csv] [modules] [--all-runs]

    modules        a subset to do, e.g. "20 29"; every module by default
    --all-runs     average over EVERY repetition instead of the first three

    OTOG_SUMMARY   the summarized run tree, if not given as an argument
                   (default: ./summary_merged_runs)

The input is what tool/scripts/summarize_runs.py writes:

    <summary_dir>/<module>/<version>/order_<name>/tests.csv

one row per test with the seconds it took, read from the surefire reports. That
is the only source of a runtime anywhere in this campaign -- wall time swings
with machine load by a factor of 25 and would rank the machine, not the order.

Every cell is measured over that cell's COMMON TEST SET: the tests that passed
in every repetition of all 100 random orders at that module-version. Two orders
of the same version can run different numbers of tests, and an order is not
faster for having skipped one, so the totals are only comparable on the tests
they all share.

    runtime(order) = sum of avg_time over the common tests

The last column, random_times, is those hundred runtimes themselves, ";"-joined
and in order, so random_average can be checked and the spread of the reference
looked at rather than taken on trust. Position i is order_i and a missing order
is "NA", so the field always holds a hundred entries. Full precision, not
rounded, so the mean of the non-NA entries reproduces random_average exactly.

WHICH REPETITIONS. tests.csv carries two averages: avg_time over run_1..run_3,
and average_all_runs over every repetition that exists. This reads avg_time, so
the figure does not move when a 4th or 5th repetition is added later -- which is
the whole reason summarize_runs.py keeps the two apart. Pass --all-runs to use
every repetition instead; the two disagree by tens of percent in a cell whose
extra repetition was unusual, so a table must be built from one or the other,
never a mixture.

NAIVE is the baseline an approach has to beat: keep using the order that was
fastest in the past. Four history budgets, cumulative, each seeded with the
previous one's best so the windows really do nest:

    naive_25    fastest of the orders run at v-1 .. v-25
    naive_50    ... v-1 .. v-50
    naive_75    ... v-1 .. v-75
    naive_100   ... v-1 .. v-100
    naive_v0_99 fastest of v0's own 100 random orders (no history at all)

A naive column holds the runtime, AT THIS VERSION, of the order that budget
picked -- not the runtime it had in the past. Orders keep their name across
versions, so the order chosen at v-25 is order_25 here too.

A missing tests.csv becomes "NA" rather than 0 and rather than failing the row.
Three things legitimately produce one: jfrsort has no order for 6 of the 16
modules, agentic has no history session for module 3320, and a handful of order
dirs hold runs that died before surefire wrote any report. Both are "not measured", and only the column that is missing says
NA -- an earlier version let one absent file turn the whole row into NA and
threw away five approaches that were present.
"""

import csv
import os
import sys

import pandas as pd

MODULES = [20, 29, 33, 1117, 1122, 1216, 1305, 1497,
           1683, 1685, 1694, 1778, 2088, 3320, 3323, 3613]
VERSIONS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# column prefix -> the order name in the run tree
APPROACHES = [("jfr", "jfrsort"), ("warm", "warmsort"), ("ag", "agentic")]

# column suffix -> the input set the order learned from
SPECS = [("24", "past_24"), ("49", "past_49"), ("74", "past_74"),
         ("99", "past_99"), ("v0_99", "v0_99")]

# The history budgets, as (column, first version, last version). Cumulative:
# each band starts from the band before it, so naive_50 is the best of v-1..v-50
# and not the best of v-26..v-50 alone.
BANDS = [("naive_25", -25, -1), ("naive_50", -50, -26),
         ("naive_75", -75, -51), ("naive_100", -100, -76)]

COLUMNS = (["random_average"]
           + [b[0] for b in BANDS] + ["naive_v0_99"]
           + ["%s_%s" % (a, s) for a, _ in APPROACHES for s, _ in SPECS]
           + ["random_times"])


def read_tests(path):
    """One order's tests.csv, or None when that order produced none."""
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def all_passed(tests):
    """The rows whose every recorded repetition passed.

    Checked against the statuses themselves rather than against
    ';'.join(['PASS'] * runs): once repetitions 4 and 5 exist, runs counts every
    repetition while statuses covers the first three, so comparing the two
    matches nothing and every runtime comes out 0.
    """
    states = tests["statuses"].fillna("")
    keep = states.apply(lambda v: v != "" and set(v.split(";")) == {"PASS"})
    return tests[keep].reset_index(drop=True)


def common_tests(summary_dir, module, version):
    """Tests that passed in every repetition of all 100 random orders here."""
    shared = None
    for order in range(1, 101):
        tests = read_tests("%s/%s/%s/order_%d/tests.csv"
                           % (summary_dir, module, version, order))
        if tests is None:
            continue
        passed = set(all_passed(tests)["test"])
        shared = passed if shared is None else shared & passed
    return shared or set()


def runtime(summary_dir, module, version, order_name, tests_wanted, column="avg_time"):
    """Seconds one order spent on the common tests, "NA" if it never ran."""
    tests = read_tests("%s/%s/%s/%s/tests.csv"
                       % (summary_dir, module, version, order_name))
    if tests is None:
        return "NA"
    if column not in tests.columns:            # a tree summarized before --all-runs
        column = "avg_time"
    return tests[tests["test"].isin(tests_wanted)][column].sum()


def historical_naives(summary_dir, module, column="avg_time"):
    """{column: order name} -- the fastest past order within each budget.

    The order run at version -k is order_k, which is also what it is called at
    every other version, so the name is all that has to be carried forward.
    """
    picked, best, fastest = {}, None, float("inf")
    for column, first, last in BANDS:
        for version in range(first, last + 1):
            tests = read_tests("%s/%s/%d/order_%d/tests.csv"
                               % (summary_dir, module, version, -version))
            if tests is None:
                continue
            col = column if column in tests.columns else "avg_time"
            total = all_passed(tests)[col].sum()
            if total < fastest:
                fastest, best = total, "order_%d" % -version
        picked[column] = best
    return picked


def v0_naive(summary_dir, module, column="avg_time"):
    """The fastest of v0's own 100 random orders, on v0's common tests."""
    wanted = common_tests(summary_dir, module, 0)
    best, fastest = None, float("inf")
    for order in range(1, 101):
        name = "order_%d" % order
        total = runtime(summary_dir, module, 0, name, wanted, column)
        if total != "NA" and total < fastest:
            fastest, best = total, name
    return best


def row_for(summary_dir, module, version, naives, column="avg_time"):
    """One master.csv row: the random average, the naives, every approach."""
    wanted = common_tests(summary_dir, module, version)
    randoms, by_name, every = [], {}, []
    for order in range(1, 101):
        name = "order_%d" % order
        total = runtime(summary_dir, module, version, name, wanted, column)
        # position i is order_i, always, so a cell short of a hundred stays
        # readable rather than silently shifting every later order left
        # float(), then repr: the sum is a numpy scalar and repr would write
        # it as np.float64(...). repr of the plain float is the shortest text
        # that reads back as the same number.
        every.append("NA" if total == "NA" else repr(float(total)))
        if total == "NA":
            continue
        randoms.append(total)
        by_name[name] = total

    out = {"random_average": sum(randoms) / len(randoms) if randoms else "NA",
           "random_times": ";".join(every)}
    for column, name in naives.items():
        out[column] = by_name.get(name, "NA") if name else "NA"
    for prefix, approach in APPROACHES:
        for suffix, spec in SPECS:
            out["%s_%s" % (prefix, suffix)] = runtime(
                summary_dir, module, version, "order_%s_%s" % (approach, spec),
                wanted, column)
    return out, len(wanted)


def main():
    args = [a for a in sys.argv[1:] if a != "--all-runs"]
    column = "average_all_runs" if "--all-runs" in sys.argv else "avg_time"
    sys.argv = [sys.argv[0]] + args
    summary_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "OTOG_SUMMARY", os.path.join(os.getcwd(), "summary_merged_runs"))
    out_csv = sys.argv[2] if len(sys.argv) > 2 else "master.csv"
    modules = [int(m) for m in sys.argv[3].split()] if len(sys.argv) > 3 else MODULES
    if not os.path.isdir(summary_dir):
        sys.exit("no summarized runs at %s -- run tool/scripts/summarize_runs.py "
                 "first, or pass the directory as the first argument" % summary_dir)

    with open(out_csv, "w", newline="") as fh:
        csv.writer(fh).writerow(["module", "version"] + COLUMNS)

    for module in modules:
        naives = historical_naives(summary_dir, module, column)
        naives["naive_v0_99"] = v0_naive(summary_dir, module, column)
        print("module %s: naive picks %s" % (module, naives))
        for version in VERSIONS:
            try:
                values, n_tests = row_for(summary_dir, module, version, naives, column)
                row = [values[c] for c in COLUMNS]
            except Exception as err:            # one bad cell must not stop the sweep
                print("  v%-4s FAILED: %s" % (version, err))
                row, n_tests = ["NA"] * len(COLUMNS), 0
            with open(out_csv, "a", newline="") as fh:
                csv.writer(fh).writerow([module, version] + row)
            print("  v%-4s %d common tests" % (version, n_tests))

    print("\nwrote %s, runtimes from %s" % (out_csv, column))


if __name__ == "__main__":
    main()
