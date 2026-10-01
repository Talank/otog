#!/usr/bin/env python3
"""Make code_changes_data.csv, the data behind the paper's code changes table
(Table 3).

    python3 make_code_changes_data.py

Covers the modules in dataset_data.csv, in the same order, so run
make_dataset_data.py first. The v0, v25, v50, v75 and v100 commits come from
../data/versions.csv. The columns are the same as the old
optimal_test_order_paper/data/code_changes_data.csv, for k = 25, 50, 75, 100:

    Commits V0-Vk               commits between v0 and version k
                                (git rev-list --count v0..vk)
    Lines added/deleted V0-Vk   lines added plus lines deleted by each of
                                those commits, summed over the commits
                                (git log --numstat v0..vk; binary files add 0)

Each project is cloned (bare) into repos/ the first time it is needed.
"""

import csv
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
VERSIONS_CSV = os.path.join(HERE, "..", "data", "versions.csv")
MODULES_CSV = os.path.join(HERE, "dataset_data.csv")
REPOS = os.path.join(HERE, "repos")
OUT_CSV = os.path.join(HERE, "code_changes_data.csv")

FUTURE = [25, 50, 75, 100]
FIELDS = (["id", "slug", "module"]
          + ["Commits V0-V%d" % k for k in FUTURE]
          + ["Lines added/deleted V0-V%d" % k for k in FUTURE])


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def repo(slug):
    """Path to a bare clone of the project, cloned the first time it is needed."""
    path = os.path.join(REPOS, slug + ".git")
    if not os.path.isdir(path):
        subprocess.run(["git", "clone", "--bare",
                        "https://github.com/%s.git" % slug, path], check=True)
    return path


def git(slug, *args):
    return subprocess.run(["git", "-C", repo(slug)] + list(args),
                          capture_output=True, text=True, check=True).stdout


def count_commits(slug, v0, vk):
    return int(git(slug, "rev-list", "--count", "%s..%s" % (v0, vk)))


def count_lines(slug, v0, vk):
    numstat = git(slug, "log", "--numstat", "--format=", "%s..%s" % (v0, vk))
    stats = [line.split("\t") for line in numstat.splitlines() if line]
    return sum(int(s[0]) + int(s[1]) for s in stats if s[0] != "-")


def code_changes_row(module, shas):
    slug, v0 = module["slug"], shas[(module["id"], 0)]
    future = [shas[(module["id"], k)] for k in FUTURE]
    return ([module["id"], slug, module["module"]]
            + [count_commits(slug, v0, vk) for vk in future]
            + [count_lines(slug, v0, vk) for vk in future])


def main():
    shas = {(r["module_id"], int(r["version"])): r["sha"]
            for r in read_csv(VERSIONS_CSV)}
    rows = [code_changes_row(m, shas) for m in read_csv(MODULES_CSV)]

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(rows)

    print("wrote %d modules to %s" % (len(rows), OUT_CSV))


if __name__ == "__main__":
    main()
