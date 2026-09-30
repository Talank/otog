#!/usr/bin/env python3
#
# usage: python3 approaches/common/install_order.py <module> <order_file> <name> [tool_dir]
#   e.g. python3 approaches/common/install_order.py 20 /tmp/past_99.txt warmsort_past_99
#
# Install a generated order at v0, then adapt it forward to every future
# version, exactly as the 100 random orders were.
#
# in : <order_file>, holding exactly v0's test set
#      orders/<module>/<version>/1.txt for each future version's test list
# out: orders/<module>/0/<name>.txt and one per future version
#
# The name says which approach and which input made the order, so
# orders/<module>/ stays readable: 1..100 are random, everything else is named.
# A purely numeric name is refused.

import os
import re
import sys
import time

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from order_adapter import compute_added_deleted_tests, remove_deleted_tests, add_added_tests

NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]*$')


def read_tests(path):
    return [t for t in open(path).read().split() if t]


def future_versions(tool_dir, module):
    """The positive versions that have an order tree to adapt into."""
    root = os.path.join(tool_dir, "orders", module)
    out = []
    for name in os.listdir(root):
        try:
            v = int(name)
        except ValueError:
            continue
        if v > 0 and os.path.isdir(os.path.join(root, name)):
            out.append(v)
    return sorted(out)


def tests_at(tool_dir, module, version):
    """A version's test set, taken from an order already adapted to it."""
    here = os.path.join(tool_dir, "orders", module, str(version))
    for name in sorted(os.listdir(here)):
        if name.endswith(".txt"):
            return read_tests(os.path.join(here, name))
    sys.exit("error: no order file in %s" % here)


def adapt(order, wanted):
    """Same rule as scripts/order_adapter.py: drop what is gone, append what is new."""
    added, deleted = compute_added_deleted_tests(order, wanted)
    return add_added_tests(remove_deleted_tests(order, deleted), added), len(added), len(deleted)


def write_order(path, order):
    if os.path.exists(path):
        sys.exit("error: %s already exists -- generated orders are never overwritten" % path)
    with open(path, "w") as f:
        f.write("\n".join(order) + "\n")


def main():
    if not 4 <= len(sys.argv) <= 5:
        sys.exit("usage: install_order.py <module> <order_file> <name> [tool_dir]")
    module, order_file, name = sys.argv[1:4]
    tool_dir = sys.argv[4] if len(sys.argv) == 5 else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not NAME.match(name):
        sys.exit("error: '%s' is not a usable name -- start with a letter, then "
                 "letters, digits, _ . or -" % name)

    started = time.perf_counter()
    order = read_tests(order_file)

    # Adapting forward from anything but a v0 order gives every later version a
    # test set that is not the campaign's.
    v0 = tests_at(tool_dir, module, 0)
    if set(order) != set(v0):
        sys.exit("error: %s does not hold v0's test set (%d tests vs %d, %d differ)"
                 % (order_file, len(order), len(v0), len(set(order) ^ set(v0))))

    write_order(os.path.join(tool_dir, "orders", module, "0", "%s.txt" % name), order)

    versions = future_versions(tool_dir, module)
    moved = 0
    for version in versions:
        forward, added, deleted = adapt(order, tests_at(tool_dir, module, version))
        write_order(os.path.join(tool_dir, "orders", module, str(version), "%s.txt" % name),
                    forward)
        if added or deleted:
            moved += 1

    print("installed %s.txt: v0 (%d tests) and %d future version(s), %d of which "
          "needed a different test set" % (name, len(order), len(versions), moved))
    print("installed in %.3fs" % (time.perf_counter() - started))


if __name__ == "__main__":
    main()
