#!/usr/bin/env python3
"""master.csv -> the summary tables.

    python3 analysis/summarize_master.py [master_csv] [out_dir]

Defaults to ./master.csv and the directory it sits in. Writes:

    summary_table.csv            mean saving %, dataset x approach -- the headline
    summary_table_median.csv     the same with a median over modules
    summary_table_coverage.csv   how many cells each figure rests on
    summary_table_no_v0.csv      the headline over v10..v100 only
    summary_table_matched.csv    only the modules every approach covers
    summary_by_module/module_<M>.csv   the headline for one module
    summary_by_module_all.csv    those 16 tables stacked
    summary_by_module_spread.csv per approach, how far the per-module numbers move
    summary_spread.csv           per approach: cells, mean, median, worst, best
    vs_naive_by_module.csv       saving against naive, per approach-dataset-module
    vs_naive_counts.csv          in how many modules the approach beats naive, k/n
    vs_naive_counts_numerator.csv     the same k, as plain numbers

THE SAVING, per (module, version) cell:

    saving % = 100 * (b - a) / b     b = random_average, a = the approach order

+ is faster than the reference, - is slower, in every table this writes. The
reference is random_average in the summary_* tables and the naive of the same
history budget in the vs_naive_* ones.

THE CELL FIGURE is a TWO-STAGE average of those savings -- average over modules
within a version, then average over versions:

    mean_v( mean_m( saving(m, v) ) )

not one flat mean over all 176 cells. The two agree only when every version
carries the same modules; in two stages each version counts once however many
modules landed in it.

BOTH MEAN AND MEDIAN are reported because they disagree sharply. A few cells run
several times the random average on the same passing tests, and one such cell
drags a column down by tens of percent. The robust view keeps the outer stage a
mean over versions and takes a median over modules inside it, so one ruinous
module cannot speak for the version.

COVERAGE IS NOT OPTIONAL. jfrsort has no order for 6 of the 16 modules, so its
column averages 110 cells where naive averages 176: the two are not measured on
the same subjects. summary_table_matched.csv drops to the modules everything
covers, and is the one to read when RANKING approaches.
"""

import os
import sys

import pandas as pd

BASELINE = "random_average"

# Named for the history budget the order was allowed, listed as the paper lists
# them. "coldstart" had no history and saw only v0's own 100 random orders.
DATASETS = ["minus100", "minus75", "minus50", "minus25", "coldstart"]

# approach -> dataset -> column in master.csv.
#
# The naive columns count VERSIONS (naive_50 = best of the 50 most recent past
# versions) and the approach columns count OFFSETS (warm_49 = learned from
# v-1..v-49), so naive_50 pairs with *_49. Both windows are cumulative, so the
# two really do mean the same span of history. Pairing them by the number in the
# name instead compares a 25-version budget with a 50-version one.
APPROACHES = {
    name: {"minus25": p + "_24", "minus50": p + "_49", "minus75": p + "_74",
           "minus100": p + "_99", "coldstart": p + "_v0_99"}
    for name, p in [("Naive", "naive"), ("JFRSort", "jfr"),
                    ("WarmSort", "warm"), ("Agentic", "ag")]
}
APPROACHES["Naive"]["minus25"] = "naive_25"
APPROACHES["Naive"]["minus50"] = "naive_50"
APPROACHES["Naive"]["minus75"] = "naive_75"
APPROACHES["Naive"]["minus100"] = "naive_100"

# v0 is in-sample for the coldstart column -- those orders were chosen by
# searching v0's own random orders, so a coldstart saving at v0 is the search's
# training score, not a prediction. The future versions are the honest read.
FUTURE = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def load(path):
    """master.csv as a frame. "NA" becomes NaN, which is how a cell is skipped."""
    d = pd.read_csv(path)
    d["module"] = d["module"].astype(int)
    d["version"] = d["version"].astype(int)
    return d


def to_long(d):
    """One row per (module, version, approach, dataset) that has a runtime."""
    rows = []
    for approach, by_dataset in APPROACHES.items():
        for dataset, col in by_dataset.items():
            if col not in d.columns:
                continue
            part = d[["module", "version", BASELINE, col]].dropna()
            for _, r in part.iterrows():
                if r[BASELINE] <= 0:
                    continue
                rows.append({
                    "module": int(r["module"]), "version": int(r["version"]),
                    "approach": approach, "dataset": dataset,
                    "runtime": r[col], "baseline": r[BASELINE],
                    # + faster than the baseline, - slower. Never the reverse.
                    "improvement": 100.0 * (r[BASELINE] - r[col]) / r[BASELINE],
                })
    return pd.DataFrame(rows)


def two_stage(long, inner="mean", versions=None):
    """mean over versions of (`inner` over modules) of the per-cell saving."""
    d = long if versions is None else long[long["version"].isin(versions)]
    per_version = d.groupby(["approach", "dataset", "version"])["improvement"].agg(inner)
    table = per_version.groupby(["approach", "dataset"]).mean().unstack("approach")
    return table.reindex(index=DATASETS, columns=list(APPROACHES)).round(2)


def coverage(long, versions=None):
    """How many (module, version) cells each figure averages over."""
    d = long if versions is None else long[long["version"].isin(versions)]
    table = d.pivot_table(index="dataset", columns="approach",
                          values="improvement", aggfunc="count")
    return table.reindex(index=DATASETS, columns=list(APPROACHES)).fillna(0).astype(int)


def matched(long, inner="median"):
    """The same table over the modules every approach covers, and which those are."""
    per = long.groupby(["approach", "module"]).size().unstack(fill_value=0)
    common = sorted(m for m in per.columns if (per[m] > 0).all())
    return two_stage(long[long["module"].isin(common)], inner), common


def per_module(long, module, inner="mean"):
    """dataset x approach for one module: the mean over that module's versions."""
    d = long[long["module"] == module]
    table = (d.groupby(["approach", "dataset", "version"])["improvement"].agg(inner)
              .groupby(["approach", "dataset"]).mean().unstack("approach"))
    return table.reindex(index=DATASETS, columns=list(APPROACHES)).round(2)


def vs_naive(long, versions=FUTURE):
    """Per (approach, dataset, module): the mean saving against naive, in %.

    A harder bar than random, and the honest one: naive is not a strategy you
    need a profiler, a solver or a model to run -- it is "keep using the order
    that was fastest last time". The baseline is the naive with the SAME history
    budget, so neither side sees history the other did not.
    """
    d = long[long["version"].isin(versions)]
    base = (d[d["approach"] == "Naive"][["module", "version", "dataset", "runtime"]]
            .rename(columns={"runtime": "naive"}))
    other = d[d["approach"] != "Naive"].merge(base, on=["module", "version", "dataset"])
    # same sign convention as improvement: + faster than naive, - slower
    other["gain"] = 100.0 * (other["naive"] - other["runtime"]) / other["naive"]
    return (other.groupby(["approach", "dataset", "module"])
                 .agg(gain=("gain", "mean"), versions=("gain", "size"),
                      approach_s=("runtime", "mean"), naive_s=("naive", "mean"))
                 .reset_index())


def beat_counts(per):
    """k/n per cell: k modules with a positive mean saving, n runnable ones.

    One module, one vote -- a module's 11 versions are near-copies of each other,
    not 11 independent trials. n differs by approach because it is the modules
    the approach can actually run on.
    """
    grouped = per.groupby(["approach", "dataset"])
    k = grouped["gain"].apply(lambda s: int((s > 0).sum()))
    n = grouped["gain"].size()
    columns = [a for a in APPROACHES if a != "Naive"]
    text = (k.astype(str) + "/" + n.astype(str)).unstack("approach")
    return (text.reindex(index=DATASETS, columns=columns).fillna("--"),
            k.unstack("approach").reindex(index=DATASETS, columns=columns))


def main():
    master_csv = sys.argv[1] if len(sys.argv) > 1 else "master.csv"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else (os.path.dirname(master_csv) or ".")
    if not os.path.isfile(master_csv):
        sys.exit("no %s -- run analysis/build_master.py first" % master_csv)
    out = lambda name: os.path.join(out_dir, name)
    os.makedirs(out("summary_by_module"), exist_ok=True)

    master = load(master_csv)
    long = to_long(master)
    print("master.csv: %d rows, %d columns" % master.shape)
    print("long form : %d cells with a runtime\n" % len(long))

    mean_t = two_stage(long, "mean")
    mean_t.to_csv(out("summary_table.csv"))
    two_stage(long, "median").to_csv(out("summary_table_median.csv"))
    coverage(long).to_csv(out("summary_table_coverage.csv"))
    two_stage(long, "mean", FUTURE).to_csv(out("summary_table_no_v0.csv"))
    matched_t, common = matched(long)
    matched_t.to_csv(out("summary_table_matched.csv"))

    print("SAVING vs an average random order, %  (higher is faster)")
    print(mean_t.to_string())
    print("\ncells each figure rests on")
    print(coverage(long).to_string())
    print("\nmodules every approach covers: %d of %d" % (len(common), master["module"].nunique()))

    stacked = []
    for module in sorted(master["module"].unique()):
        table = per_module(long, module)
        table.to_csv(out("summary_by_module/module_%d.csv" % module))
        row = table.copy()
        row.insert(0, "module", module)
        stacked.append(row.reset_index())
    all_modules = pd.concat(stacked, ignore_index=True)
    all_modules.to_csv(out("summary_by_module_all.csv"), index=False)

    spread = (all_modules.melt(id_vars=["module", "dataset"], var_name="approach",
                               value_name="saving").dropna()
              .groupby("approach")["saving"]
              .agg(["count", "mean", "min", "max", "std"]).round(2))
    spread.columns = ["cells", "mean", "worst module-dataset",
                      "best module-dataset", "sd"]
    spread.to_csv(out("summary_by_module_spread.csv"))
    print("\nspread of the per-module numbers, by approach")
    print(spread.to_string())

    overall = long.groupby("approach")["improvement"].describe()[
        ["count", "mean", "50%", "min", "max"]].round(2)
    overall.columns = ["cells", "mean", "median", "worst", "best"]
    overall.to_csv(out("summary_spread.csv"))

    per = vs_naive(long)
    per.round(2).to_csv(out("vs_naive_by_module.csv"), index=False)
    counts, numerator = beat_counts(per)
    counts.to_csv(out("vs_naive_counts.csv"))
    numerator.fillna(0).astype(int).to_csv(out("vs_naive_counts_numerator.csv"))
    print("\nmodules where the approach beats NAIVE, averaged over v10..v100")
    print(counts.to_string())

    print("\nwrote the tables to %s" % os.path.abspath(out_dir))


if __name__ == "__main__":
    main()
