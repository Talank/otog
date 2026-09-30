#!/usr/bin/env python3
#
# usage: python3 analysis/jfr_overhead.py <summary_dir> [out_csv]
#   e.g. python3 analysis/jfr_overhead.py summary_merged_runs /tmp/jfr_overhead.csv
#
# What the JFR recording costs, from the order dirs holding both a plain and a
# profiled summary. Profiled repetitions were only collected at v0 and the
# historical versions, so those are the only rows.
#
# Both files' avg_time covers three repetitions -- run_1..run_3 in tests.csv,
# jfr_run_1..jfr_run_3 in tests_jfr.csv -- so the two totals are comparable.
# Summed over the tests that passed in both, because a test missing from one
# side would otherwise read as a speedup.
#
# out: <out_csv>, one row per order, and a per-module summary on stdout.
#      overhead is positive when the profiled run took longer.

import csv
import os
import sys


def read_times(path):
    """{test: seconds} for the tests that passed, from avg_time."""
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] == "PASS":
                out[row["test"]] = float(row["avg_time"])
    return out


def pairs(summary_dir):
    """(module, version, order, plain_seconds, jfr_seconds, tests) per order dir."""
    for module in sorted(os.listdir(summary_dir)):
        mdir = os.path.join(summary_dir, module)
        if not os.path.isdir(mdir):
            continue
        for version in sorted(os.listdir(mdir)):
            vdir = os.path.join(mdir, version)
            if not os.path.isdir(vdir):
                continue
            for order in sorted(os.listdir(vdir)):
                odir = os.path.join(vdir, order)
                plain = os.path.join(odir, "tests.csv")
                jfr = os.path.join(odir, "tests_jfr.csv")
                if not (os.path.isfile(plain) and os.path.isfile(jfr)):
                    continue
                p, j = read_times(plain), read_times(jfr)
                common = set(p) & set(j)
                if not common:
                    continue
                yield (module, version, order[len("order_"):],
                       sum(p[t] for t in common), sum(j[t] for t in common),
                       len(common))


def median(values):
    s = sorted(values)
    n = len(s)
    if not n:
        return float("nan")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def main():
    if not 2 <= len(sys.argv) <= 3:
        sys.exit("usage: jfr_overhead.py <summary_dir> [out_csv]")
    summary_dir = sys.argv[1]
    out_csv = sys.argv[2] if len(sys.argv) == 3 else None

    rows, by_module = [], {}
    for module, version, order, plain, jfr, tests in pairs(summary_dir):
        if plain <= 0:
            continue
        pct = 100.0 * (jfr - plain) / plain
        rows.append((module, version, order, tests, plain, jfr, pct))
        by_module.setdefault(module, []).append(pct)

    if not rows:
        sys.exit("no order dir holds both tests.csv and tests_jfr.csv under %s"
                 % summary_dir)

    if out_csv:
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["module", "version", "order", "tests",
                        "plain_s", "jfr_s", "overhead_pct"])
            for module, version, order, tests, plain, jfr, pct in rows:
                w.writerow([module, version, order, tests,
                            "%.3f" % plain, "%.3f" % jfr, "%.2f" % pct])
        print("wrote %s" % out_csv)

    print("\nJFR overhead, % slower than the same order unprofiled")
    print("%-8s %6s %8s %8s %8s %8s" % ("module", "orders", "median", "mean", "min", "max"))
    for module in sorted(by_module, key=lambda m: median(by_module[m])):
        v = by_module[module]
        print("%-8s %6d %7.1f%% %7.1f%% %7.1f%% %7.1f%%"
              % (module, len(v), median(v), sum(v) / len(v), min(v), max(v)))
    every = [r[6] for r in rows]
    print("%-8s %6d %7.1f%% %7.1f%% %7.1f%% %7.1f%%"
          % ("ALL", len(every), median(every), sum(every) / len(every),
             min(every), max(every)))


if __name__ == "__main__":
    main()
