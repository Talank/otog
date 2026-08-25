#!/usr/bin/env python3
"""Paired analysis of a mechanisms results.csv: Wilcoxon signed-rank test per experiment.

Usage: wilcoxon.py results.csv [--partial]

Pairs fast/slow arms by round within each (config, experiment). Only rounds where BOTH
arms are green enter the test. Differences are slow_total - fast_total, so a positive
median supports the mechanism's predicted direction. The test is the exact two-sided
signed-rank test (all 2^n sign assignments over mid-ranks of |d|, zero differences
dropped) -- no scipy needed, n is at most the round count (10).
"""
import csv
import sys
from itertools import product


def exact_wilcoxon(diffs):
    d = [x for x in diffs if x != 0.0]
    n = len(d)
    if n == 0:
        return None, None, 0
    magnitudes = sorted((abs(x), i) for i, x in enumerate(d))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and magnitudes[j + 1][0] == magnitudes[i][0]:
            j += 1
        mid = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[magnitudes[k][1]] = mid
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks, d) if x > 0)
    total = 0
    as_extreme = 0
    center = sum(ranks) / 2.0
    obs_dev = abs(w_plus - center)
    for signs in product((0, 1), repeat=n):
        w = sum(r for r, s in zip(ranks, signs) if s)
        total += 1
        if abs(w - center) >= obs_dev - 1e-9:
            as_extreme += 1
    return w_plus, as_extreme / total, n


def median(xs):
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def main():
    path = sys.argv[1]
    partial = "--partial" in sys.argv
    rows = list(csv.DictReader(open(path)))
    experiments = {}
    for r in rows:
        experiments.setdefault((r["config"], r["experiment"]), []).append(r)

    for (config, experiment), rs in sorted(experiments.items()):
        by_round = {}
        for r in rs:
            by_round.setdefault(r["round"], {})[r["arm"]] = r
        pairs, red = [], 0
        for rnd in sorted(by_round, key=int):
            arms = by_round[rnd]
            if "fast" not in arms or "slow" not in arms:
                continue
            if arms["fast"]["green"] != "1" or arms["slow"]["green"] != "1":
                red += 1
                continue
            pairs.append((float(arms["slow"]["total_s"]), float(arms["fast"]["total_s"])))

        header = f"=== {config} / {experiment} ==="
        print(header)
        if not pairs:
            print(f"  no green pairs ({red} red rounds)\n")
            continue
        diffs = [s - f for s, f in pairs]
        slow_med, fast_med = median([s for s, _ in pairs]), median([f for _, f in pairs])
        wins = sum(1 for d in diffs if d > 0)
        w, p, n = exact_wilcoxon(diffs)
        pct = 100.0 * (slow_med - fast_med) / slow_med if slow_med else 0.0
        print(f"  green pairs: {len(pairs)} (red rounds dropped: {red})")
        print(f"  median total: fast={fast_med:.3f}s slow={slow_med:.3f}s"
              f" (fast is {pct:.2f}% lower)")
        print(f"  paired diff slow-fast: median={median(diffs):.3f}s"
              f" mean={sum(diffs)/len(diffs):.3f}s fast wins {wins}/{len(diffs)}")
        if n:
            print(f"  Wilcoxon signed-rank (exact, two-sided): W+={w:.1f} n={n} p={p:.5f}")
        else:
            print("  Wilcoxon: all differences zero")
        if partial and len(pairs) < 10:
            print("  [partial -- experiment still running]")
        print()


if __name__ == "__main__":
    main()
