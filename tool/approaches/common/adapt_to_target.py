#!/usr/bin/env python3
#
# usage: python3 approaches/common/adapt_to_target.py <order_file> <module> <target_version> <out_file> [tool_dir]
# e.g.   python3 approaches/common/adapt_to_target.py /tmp/warmsort_past_24.txt 1685 0 /tmp/warmsort_past_24_v0.txt
#
# An order learned from past versions holds those versions' tests, which are
# not the target version's: 1685 ran 275 tests at v-17 and 2209 at v0. This
# drops what the target no longer has and appends what it added, keeping the
# learned relative order -- the same adaptation the campaign's own orders got.
#
# in : <order_file>, and orders/<module>/<target_version>/ for the target's tests
# out: <out_file>, holding exactly the target version's tests

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from order_adapter import adapt_order


def target_list(tool_dir, module, version):
    """Any measured order at the target version lists exactly its tests."""
    d = os.path.join(tool_dir, "orders", str(module), str(version))
    for name in sorted(os.listdir(d)):
        if name.endswith(".txt") and name[:-4].isdigit():
            return os.path.join(d, name)
    sys.exit("no measured order at %s to take the test set from" % d)


def main(order_file, module, target_version, out_file, tool_dir=None):
    tool_dir = os.path.abspath(tool_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".."))

    target = target_list(tool_dir, module, target_version)
    adapt_order(order_file, target, os.path.abspath(out_file))

    got = open(out_file).read().split()
    want = open(target).read().split()
    if sorted(got) != sorted(want):
        sys.exit("  ERROR: adapted order is not v%s's test set (%d vs %d)"
                 % (target_version, len(got), len(want)))
    print("  adapted to v%s: %d tests" % (target_version, len(got)))


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: adapt_to_target.py <order_file> <module> <target_version> <out_file> [tool_dir]")
    main(*sys.argv[1:6])
