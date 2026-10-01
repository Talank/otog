#!/usr/bin/env python3
"""Make dataset_data.csv, the data behind the paper's dataset table (Table 2).

    python3 make_dataset_data.py

Reads ../data/versions.csv, ../data/master.csv and v0_orders/, and writes
dataset_data.csv next to this script with the same columns as the old
optimal_test_order_paper/data/dataset_data.csv:

    id             module id, as in versions.csv
    slug           project
    module         module
    total_classes  test classes in the module's v0 order
    total_ci_time  random_average at version 0 in master.csv, in seconds,
                   unrounded (the paper's defs script rounds it)

Only the modules in MODULES are included. Rows are sorted by slug, then
module; the paper numbers the modules M1, M2, ... in row order.

v0_orders/<id>.txt is summary_merged_runs/<id>/0/order_1/order.txt, one test
per line as Class#method. All 100 random orders at v0 hold the same classes,
so any one of them gives the count.
"""

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VERSIONS_CSV = os.path.join(HERE, "..", "data", "versions.csv")
MASTER_CSV = os.path.join(HERE, "..", "data", "master.csv")
V0_ORDERS = os.path.join(HERE, "v0_orders")
OUT_CSV = os.path.join(HERE, "dataset_data.csv")

# The 10 modules in the paper. The other 6 in master.csv have no jfrsort results.
MODULES = [20, 29, 33, 1117, 1122, 1683, 1685, 1778, 2088, 3613]
FIELDS = ["id", "slug", "module", "total_classes", "total_ci_time"]


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def at_v0(rows, key):
    """{module id: its version 0 row}"""
    return {r[key]: r for r in rows if r["version"] == "0"}


def count_test_classes(module_id):
    with open(os.path.join(V0_ORDERS, module_id + ".txt")) as f:
        return len({line.split("#")[0] for line in f if line.strip()})


def dataset_row(version, master):
    return {"id": version["module_id"],
            "slug": version["slug"],
            "module": version["module"],
            "total_classes": count_test_classes(version["module_id"]),
            "total_ci_time": master["random_average"]}


def main():
    versions = at_v0(read_csv(VERSIONS_CSV), "module_id")
    master = at_v0(read_csv(MASTER_CSV), "module")

    rows = sorted((dataset_row(versions[str(m)], master[str(m)]) for m in MODULES),
                  key=lambda r: (r["slug"].lower(), r["module"].lower()))

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print("wrote %d modules to %s" % (len(rows), OUT_CSV))


if __name__ == "__main__":
    main()
