#!/usr/bin/env python3
"""Create front/back test orders without perturbing the non-target classes."""

from __future__ import annotations

import argparse
from pathlib import Path


def read_order(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--test", action="append", required=True, dest="tests")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="remove a known non-runnable class from both generated arms",
    )
    args = parser.parse_args()

    base = read_order(args.base)
    missing = [test for test in args.tests if test not in base]
    if missing:
        raise SystemExit(f"target classes missing from base order: {missing}")
    if len(set(base)) != len(base):
        raise SystemExit("base order contains duplicate classes")

    unknown_exclusions = [test for test in args.exclude if test not in base]
    if unknown_exclusions:
        raise SystemExit(f"excluded classes missing from base order: {unknown_exclusions}")
    excluded = set(args.exclude)
    targets = [test for test in dict.fromkeys(args.tests) if test not in excluded]
    remainder = [
        test for test in base if test not in set(targets) and test not in excluded
    ]
    arms = {
        "front": targets + remainder,
        "back": remainder + targets,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    for arm, order in arms.items():
        destination = args.out / f"{args.name}-{arm}.order"
        destination.write_text("\n".join(order) + "\n", encoding="utf-8")
        print(f"{arm}: {len(order)} classes -> {destination}")


if __name__ == "__main__":
    main()
