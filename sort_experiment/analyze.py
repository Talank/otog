#!/usr/bin/env python3
"""Analyze sort-experiment timings: paired Wilcoxon signed-rank per arm vs initial.

Input: results.tsv with lines "<round>\t<arm>\t<suite_ms>\t<classes>\t<fails>".
Only rounds with full class coverage and zero failures are used, paired to initial's same round.
"""
import collections
import itertools
import math
import statistics as st
import sys

ARMS = ["initial", "mth", "pkg", "pkg-cls", "pkg-cls-mth", "cls", "cls-mth"]


def wilcoxon_exact(diffs):
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(diffs[i]))
    rank = [0] * n
    for pos, i in enumerate(order):
        rank[i] = pos + 1
    w = min(sum(rank[i] for i in range(n) if diffs[i] > 0),
            sum(rank[i] for i in range(n) if diffs[i] < 0))
    if n <= 20:
        count = sum(1 for s in itertools.product((1, -1), repeat=n)
                    if min(sum(rank[i] for i in range(n) if s[i] > 0),
                           sum(rank[i] for i in range(n) if s[i] < 0)) <= w)
        return count / 2 ** n
    mu = n * (n + 1) / 4.0
    sd = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    return math.erfc(abs((w - mu) / sd) / math.sqrt(2)) if sd else 1.0


def main():
    rows = collections.defaultdict(dict)  # round -> arm -> ms  (green, full-coverage only)
    full = 0
    for line in open(sys.argv[1]):
        p = line.split()
        if len(p) < 5:
            continue
        rnd, arm, ms, classes, fails = int(p[0]), p[1], float(p[2]), int(p[3]), int(p[4])
        full = max(full, classes)
    for line in open(sys.argv[1]):
        p = line.split()
        if len(p) < 5:
            continue
        rnd, arm, ms, classes, fails = int(p[0]), p[1], float(p[2]), int(p[3]), int(p[4])
        if fails == 0 and classes == full:
            rows[rnd][arm] = ms

    R = sorted(rows)
    base = {r: rows[r]["initial"] for r in R if "initial" in rows[r]}
    b = list(base.values())
    if b:
        print("initial: median %.0fms  min %.0f  max %.0f  round-noise %.1f%%"
              % (st.median(b), min(b), max(b), (max(b) - min(b)) / st.median(b) * 100))
    print("%-13s %5s %10s %9s %8s %7s" % ("arm", "n", "median_ms", "vs_init", "p", "wins"))
    result = []
    for arm in ARMS:
        pairs = [(base[r], rows[r][arm]) for r in R if arm in rows[r] and r in base]
        if not pairs:
            continue
        med = st.median([y for _, y in pairs])
        pct = st.median([(a - c) / a * 100 for a, c in pairs])
        p = wilcoxon_exact([c - a for a, c in pairs]) if arm != "initial" else float("nan")
        wins = sum(1 for a, c in pairs if c < a)
        result.append((arm, len(pairs), med, pct, p, wins))
    for arm, n, med, pct, p, wins in result:
        ps = "" if arm == "initial" else "%.4f" % p
        print("%-13s %5d %10.0f %+8.2f%% %8s %5d/%d" % (arm, n, med, pct, ps, wins, n))


if __name__ == "__main__":
    main()
