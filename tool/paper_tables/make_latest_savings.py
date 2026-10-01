#!/usr/bin/env python3
"""Make latest_version_savings.csv: each approach's runtime saving at the
latest version of each module.

    python3 make_latest_savings.py

Reads the version "latest" rows of ../data/master.csv for the modules in
make_dataset_data.MODULES. The saving and the Commit rows are the same as in
make_overall_eval_data.py (Table 4):

    saving % = 100 * (random_average - approach) / random_average

One row per Commit row and module, then an "average" row per Commit row: the
mean over the modules that have a value. NA means that approach has no order
for that module and Commit row.
"""

import csv
import os

from make_dataset_data import MODULES
from make_overall_eval_data import (APPROACHES, COMMITS, fmt, module_rows,
                                    saving, version_saving)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "latest_version_savings.csv")


def main():
    rows = module_rows()
    latest = {r["module"]: r for r in rows if r["version"] == "latest"}
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["commit", "module"] + list(APPROACHES))
        for c in COMMITS:
            for m in MODULES:
                writer.writerow([c, m] + [fmt(saving(latest[str(m)], APPROACHES[a][c]))
                                          for a in APPROACHES])
            writer.writerow([c, "average"] + [fmt(version_saving(rows, APPROACHES[a][c], "latest"))
                                              for a in APPROACHES])
    print("wrote %s" % OUT_CSV)


if __name__ == "__main__":
    main()
