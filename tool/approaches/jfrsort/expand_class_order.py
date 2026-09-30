#!/usr/bin/env python3
#
# usage: python3 approaches/jfrsort/expand_class_order.py <class_order> <reference_order> <out_file>
# e.g.   python3 approaches/jfrsort/expand_class_order.py order-alloc-sort.txt orders/29/0/1.txt /tmp/jfrsort.txt
#
# jfrsort sorts test CLASSES; the campaign runs class#method. This expands one
# into the other: the classes in jfrsort's order, each followed by its own
# methods, exactly the no-interleaving shape the 100 random orders have.
#
# jfrsort only ranks classes that emitted events, so a class the recordings
# never saw is missing from its output. Those are appended in the reference
# order rather than dropped -- the installed order has to be the version's
# whole test set or adapt_to_target refuses it.
#
# in : <class_order>     one fully qualified class per line, jfrsort's output
#      <reference_order> the version's measured order, class#method per line
# out: <out_file>, exactly the reference order's tests, reordered

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts"))
from generate_random_test_order import get_classes_methods


def main(class_order_file, reference_file, out_file):
    ranked = [c.strip() for c in open(class_order_file) if c.strip()]
    reference = [t.strip() for t in open(reference_file) if t.strip()]

    classes_order, tests_in_classes = get_classes_methods(reference)

    # jfrsort's classes first, in its order; then whatever it never saw.
    seen = set()
    final_classes = []
    for c in ranked:
        if c in tests_in_classes and c not in seen:
            final_classes.append(c)
            seen.add(c)
    unranked = [c for c in classes_order if c not in seen]
    final_classes += unranked

    out = []
    for c in final_classes:
        out += ["%s#%s" % (c, m) for m in tests_in_classes[c]]

    if sorted(out) != sorted(reference):
        sys.exit("ERROR: expansion is not the reference test set (%d vs %d)"
                 % (len(out), len(reference)))

    with open(out_file, "w") as f:
        f.write("\n".join(out) + "\n")
    print("  expanded %d classes (%d ranked by jfrsort, %d unranked appended) -> %d tests"
          % (len(final_classes), len(final_classes) - len(unranked), len(unranked), len(out)))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: expand_class_order.py <class_order> <reference_order> <out_file>")
    main(*sys.argv[1:4])
