#!/usr/bin/env python3
"""Build one whole-suite arm order from a natural order.

Usage: make_arm.py NATURAL OUT [--exclude a,b,...] [--moves "front:x,y;back:z"]
                   [--present-dir target/test-classes]

Moves keep the listed internal order. --present-dir drops classes whose .class file does
not exist in this checkout (natural orders were captured on another machine/JDK).
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("natural")
    ap.add_argument("out")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--moves", default="")
    ap.add_argument("--present-dir", default="")
    args = ap.parse_args()

    with open(args.natural) as f:
        order = [line.strip() for line in f if line.strip()]

    excluded = {c.strip() for c in args.exclude.split(",") if c.strip()}
    dropped = [c for c in order if c in excluded]
    order = [c for c in order if c not in excluded]

    if args.present_dir:
        missing = [c for c in order
                   if not os.path.isfile(os.path.join(args.present_dir, c.replace(".", "/") + ".class"))]
        for c in missing:
            print(f"make_arm: dropping {c} (no .class under {args.present_dir})", file=sys.stderr)
        order = [c for c in order if c not in set(missing)]

    front, back = [], []
    for directive in filter(None, (d.strip() for d in args.moves.split(";"))):
        where, _, classes = directive.partition(":")
        moved = [c.strip() for c in classes.split(",") if c.strip()]
        for c in moved:
            if c not in order:
                sys.exit(f"make_arm: move target {c} not in filtered natural order")
        if where == "front":
            front += moved
        elif where == "back":
            back += moved
        else:
            sys.exit(f"make_arm: bad move directive {directive!r}")

    moved_set = set(front) | set(back)
    middle = [c for c in order if c not in moved_set]
    result = front + middle + back

    with open(args.out, "w") as f:
        f.write("\n".join(result) + "\n")
    print(f"make_arm: {args.out}: {len(result)} classes"
          f" (excluded {len(dropped)}, moved front={len(front)} back={len(back)})", file=sys.stderr)


if __name__ == "__main__":
    main()
