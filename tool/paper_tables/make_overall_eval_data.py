#!/usr/bin/env python3
"""Make overall_eval_data.csv, the data behind the paper's results table
(Table 4).

    python3 make_overall_eval_data.py

For each approach and each "Commit" row, the average runtime saving over the
modules in make_dataset_data.MODULES and the 10 future versions v10..v100,
from ../data/master.csv. Per module and version:

    saving % = 100 * (random_average - approach) / random_average

so + is faster than the random orders and - is slower. The average is taken
over modules within a version, then over versions (the same as one mean over
all cells when none is missing). Rows follow the old
optimal_test_order_paper/data/overall_eval_data.csv: -100, -75, -50 and -25
are the history the order learned from, 0 is cold start (v0's own random
orders). Agent has no -50 or -100 order, so those cells are NA.
"""

import csv
import os

from make_dataset_data import MASTER_CSV, MODULES, read_csv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "overall_eval_data.csv")

FUTURE = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
COMMITS = [-100, -75, -50, -25, 0]

# approach -> Commit row -> master.csv column. naive counts versions
# (naive_50 = best of v-1..v-50) and the others count offsets (jfr_49 =
# learned from v-1..v-49), so both cover the same history in a row.
APPROACHES = {
    "naive":    {-100: "naive_100", -75: "naive_75", -50: "naive_50",
                 -25: "naive_25", 0: "naive_v0_99"},
    "jfrsort":  {-100: "jfr_99", -75: "jfr_74", -50: "jfr_49",
                 -25: "jfr_24", 0: "jfr_v0_99"},
    "agent":    {-100: "ag_99", -75: "ag_74", -50: "ag_49",
                 -25: "ag_24", 0: "ag_v0_99"},
    "warmsort": {-100: "warm_99", -75: "warm_74", -50: "warm_49",
                 -25: "warm_24", 0: "warm_v0_99"},
}


def module_rows():
    return [r for r in read_csv(MASTER_CSV) if int(r["module"]) in MODULES]


def mean(values):
    """Mean of the values that are not None; None if there are none."""
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def saving(row, column):
    """Saving % of one module-version cell, None if the order never ran."""
    if row[column] == "NA":
        return None
    random_average = float(row["random_average"])
    return 100 * (random_average - float(row[column])) / random_average


def version_saving(rows, column, version):
    """Mean saving over the modules at one version."""
    return mean(saving(r, column) for r in rows if int(r["version"]) == version)


def overall_saving(rows, column):
    """Mean over the future versions of the per-version saving."""
    return mean(version_saving(rows, column, v) for v in FUTURE)


def fmt(value):
    return "NA" if value is None else "%.2f" % value


def main():
    rows = module_rows()
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["approach_suffix"] + [a + "_avg" for a in APPROACHES])
        for c in COMMITS:
            writer.writerow([c] + [fmt(overall_saving(rows, APPROACHES[a][c]))
                                   for a in APPROACHES])
    print("wrote %s" % OUT_CSV)


if __name__ == "__main__":
    main()
