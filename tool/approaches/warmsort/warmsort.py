#!/usr/bin/env python3
#
# usage: python3 approaches/warmsort/warmsort.py <summary_dir> <module> <spec> <out_file> [reference_order]
#   spec = v0_99 | past_24 | past_49 | past_74 | past_99
#
# Estimate each test's own cost and how much slower it runs early, then build
# the order those estimates imply. The figures behind every constant are in
# approach_note.pdf.
#
# Input is summary_merged_runs, from the "times" column of each order's
# tests.csv: run_1..run_3 only, so the order does not move when a later
# repetition lands.

import csv
import os
import sys
import numpy as np

BINS = np.array([0.0, 0.02, 0.08, 0.30, 1.0001])
MIN_SEC = 0.002
PASSES = 40

def dataset_versions(spec):
    if spec == "v0_99":
        return [(0, list(range(1, 100)))]
    n = int(spec.split("_")[1])
    return [(-k, [k]) for k in range(1, n + 1)]

def read_order(path):
    """[(test, [seconds per repetition])] in execution order, run_1..run_3."""
    seq = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            vals = [float(x) for x in row["times"].split(";") if x]
            if vals:
                seq.append((row["test"], vals))
    return seq


def load(summary_dir, module, spec):
    """runs: [[(test, seconds)]], and the input order each run came from."""
    runs, tags = [], []
    for version, orders in dataset_versions(spec):
        vd = os.path.join(summary_dir, str(module), str(version))
        for k in orders:
            p = os.path.join(vd, "order_%d" % k, "tests.csv")
            if not os.path.isfile(p):
                continue
            seq = read_order(p)
            if len(seq) < 5:
                continue
            for r in range(max(len(v) for _, v in seq)):
                one = [(t, v[r]) for t, v in seq if r < len(v)]
                if len(one) >= 5:
                    runs.append(one)
                    tags.append((version, k))
    return runs, tags

def paces(runs, rough):
    out = []
    for one in runs:
        exp = sum(rough.get(t, 0.0) for t, _ in one)
        obs = sum(s for _, s in one)
        p = (obs / exp) if exp > 0 else 1.0
        out.append(p if p > 0 else 1.0)
    return np.array(out)

def test_costs(runs):
    rough = {}
    for one in runs:
        for t, s in one:
            rough.setdefault(t, []).append(s)
    rough = {t: float(np.median(v)) for t, v in rough.items()}
    pc = paces(runs, rough)
    acc = {}
    for one, p in zip(runs, pc):
        for t, s in one:
            acc.setdefault(t, []).append(s / p)
    return {t: float(np.median(v)) for t, v in acc.items()}, rough, pc

def profile(runs, pc, a, tests_of_interest=None):
    """per-test multiplier by position bin, plus the seconds behind each cell."""
    nb = len(BINS) - 1
    num, den = {}, {}
    gnum, gden = np.zeros(nb), np.zeros(nb)
    for one, p in zip(runs, pc):
        n = len(one) - 1
        if n <= 0:
            continue
        for i, (t, s) in enumerate(one):
            ai = a.get(t, 0.0)
            if ai <= MIN_SEC:
                continue
            b = int(np.clip(np.searchsorted(BINS, i / n, side="right") - 1, 0, nb - 1))
            r = (s / p) / ai
            gnum[b] += r * ai
            gden[b] += ai
            if tests_of_interest is None or t in tests_of_interest:
                if t not in num:
                    num[t] = np.zeros(nb)
                    den[t] = np.zeros(nb)
                num[t][b] += r
                den[t][b] += 1.0
    g = np.where(gden > 0, gnum / np.maximum(gden, 1e-12), 1.0)
    return num, den, g

def split_half_weight(x_a, x_b):
    """How much of a fitted shape reproduces on the other half of the runs."""
    da, db = np.asarray(x_a) - 1.0, np.asarray(x_b) - 1.0
    if da.std() <= 0 or db.std() <= 0:
        return 0.0
    r = float(np.corrcoef(da, db)[0, 1])
    return max(0.0, min(1.0, r))

def fit(runs, pc, a):
    """w[test] -- a shrunk multiplier per position bin, and the module curve."""
    heavy = {t for t, v in a.items() if v > MIN_SEC}
    num, den, g = profile(runs, pc, a, heavy)
    ha = list(range(0, len(runs), 2))
    hb = list(range(1, len(runs), 2))
    _, _, gA = profile([runs[i] for i in ha], pc[ha], a, set())
    _, _, gB = profile([runs[i] for i in hb], pc[hb], a, set())
    lam_g = split_half_weight(gA, gB)
    g = 1.0 + lam_g * (g - 1.0)

    numA, denA, _ = profile([runs[i] for i in ha], pc[ha], a, heavy)
    numB, denB, _ = profile([runs[i] for i in hb], pc[hb], a, heavy)

    w = {}
    for t in heavy:
        if t not in num or den[t].min() < 3:
            w[t] = g
            continue
        m = num[t] / np.maximum(den[t], 1e-9)
        if t in numA and t in numB and denA[t].min() >= 2 and denB[t].min() >= 2:
            mA = numA[t] / np.maximum(denA[t], 1e-9)
            mB = numB[t] / np.maximum(denB[t], 1e-9)
            lam = split_half_weight(mA, mB)
        else:
            lam = 0.0
        w[t] = g + lam * (m - g)
    return w, g, lam_g

def classes_from(reference):
    order, members = [], {}
    for t in reference:
        k = t.split("#", 1)[0]
        if k not in members:
            members[k] = []
            order.append(k)
        members[k].append(t)
    return order, members

def modelled_total(seq, a, w, g):
    n = len(seq) - 1
    if n <= 0:
        return 0.0
    nb = len(BINS) - 1
    u = np.arange(len(seq)) / n
    b = np.clip(np.searchsorted(BINS, u, side="right") - 1, 0, nb - 1)
    fill = float(np.median([v for v in a.values()])) if a else 0.0
    tot = 0.0
    for i, t in enumerate(seq):
        ai = a.get(t, fill)
        if ai <= 0:
            continue
        tot += ai * w.get(t, g)[b[i]]
    return float(tot)

def seed_order(runs, tags, rough, pc, reference):
    """The input order with the lowest pace: fewest seconds for the work it held."""
    by_order = {}
    for (ver, k), p in zip(tags, pc):
        by_order.setdefault((ver, k), []).append(p)
    if not by_order:
        return list(reference)
    best = min(by_order, key=lambda key: float(np.median(by_order[key])))
    for one, tag in zip(runs, tags):
        if tag == best:
            return [t for t, _ in one]
    return list(reference)

def build(reference, seed, a, w, g):
    cls_order, members = classes_from(reference)
    seed_cls, _ = classes_from([t for t in seed if t in set(reference)])
    cur = [k for k in seed_cls if k in members]
    cur += [k for k in cls_order if k not in set(cur)]

    def flat(order):
        return [t for k in order for t in members[k]]

    best = modelled_total(flat(cur), a, w, g)
    n = len(cur)
    for _ in range(PASSES):
        improved = False
        for i in range(n):
            blk = cur[i]
            rest = cur[:i] + cur[i + 1:]
            cands = sorted(set([0, len(rest)] + [int(len(rest) * f) for f in
                                                 (0.1, 0.25, 0.5, 0.75, 0.9)]))
            for j in cands:
                if j == i:
                    continue
                trial = rest[:j] + [blk] + rest[j:]
                val = modelled_total(flat(trial), a, w, g)
                if val < best - 1e-9:
                    cur, best, improved = trial, val, True
                    break
            if improved:
                break
        if not improved:
            break
    return flat(cur), best

def main(summary_dir, module, spec, out_file, reference_file=None):
    runs, tags = load(summary_dir, module, spec)
    if len(runs) < 6:
        sys.exit("warmsort: only %d usable runs for module %s %s" % (len(runs), module, spec))
    a, rough, pc = test_costs(runs)
    w, g, lam_g = fit(runs, pc, a)

    if reference_file and os.path.isfile(reference_file):
        reference = [l.strip() for l in open(reference_file) if l.strip()]
    else:
        reference = [t for t, _ in runs[0]]
    known = set(reference)
    a = {t: v for t, v in a.items() if t in known}

    seed = seed_order(runs, tags, rough, pc, reference)
    order, pred = build(reference, seed, a, w, g)
    if sorted(order) != sorted(reference):
        sys.exit("warmsort: built order is not the reference test set (%d vs %d)"
                 % (len(order), len(reference)))

    base = modelled_total(seed, a, w, g)
    mean_rand = np.mean([modelled_total([t for t, _ in one], a, w, g) for one in runs[:30]])
    print("  runs=%d tests=%d classes=%d lambda_curve=%.2f curve=%s"
          % (len(runs), len(reference), len(set(t.split('#')[0] for t in reference)),
             lam_g, " ".join("%.3f" % x for x in g)))
    print("  modelled: mean input %.2fs | seed %.2fs | warmsort %.2fs  (%+.2f%% vs seed, %+.2f%% vs mean)"
          % (mean_rand, base, pred,
             100 * (pred - base) / base if base else 0.0,
             100 * (pred - mean_rand) / mean_rand if mean_rand else 0.0))
    with open(out_file, "w") as f:
        f.write("\n".join(order) + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: warmsort.py <summary_dir> <module> <spec> <out_file> [reference_order]")
    main(*sys.argv[1:6])
