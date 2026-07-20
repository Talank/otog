#!/usr/bin/env python3
"""Generate the 7 sort-experiment order files from a per-method allocation trace.

Reads a JSONL of {"test": "FQCN#method", "allocBytes": N} rows (from MethodAllocListener,
possibly several rows per method across trace repeats -> summed) and the class order that
defines "initial" (the discovery order, one FQCN per line). Writes 7 order files of
"FQCN#method" lines, classes always kept contiguous (no cross-class interleaving).

Arms:
  initial      as-given class order, methods in discovery order
  mth          initial class order; methods sorted by alloc within each class
  pkg          packages sorted by total alloc; classes/methods keep initial order
  pkg-cls      packages sorted; classes sorted by alloc within a package
  pkg-cls-mth  packages sorted; classes sorted; methods sorted within a class
  cls          global class sort by alloc; methods keep discovery order
  cls-mth      global class sort; methods sorted within a class

Usage: gen_orders.py <alloc.jsonl> <initial_class_order.txt> <method_discovery_order.txt> <out_dir>
"""
import collections
import json
import sys


def main():
    alloc_path, class_order_path, method_order_path, out_dir = sys.argv[1:5]

    alloc = collections.defaultdict(int)
    for line in open(alloc_path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        alloc[r["test"]] += int(r.get("allocBytes", 0))

    # Discovery order of methods (defines "initial"); one "FQCN#method" per line, in run order.
    methods = [l.strip() for l in open(method_order_path) if l.strip()]
    cls_of = lambda m: m.split("#", 1)[0]
    pkg_of = lambda m: cls_of(m).rsplit(".", 1)[0]
    g = lambda m: alloc.get(m, 0)

    # Methods grouped by class, in discovery order.
    by_class = collections.OrderedDict()
    for m in methods:
        by_class.setdefault(cls_of(m), []).append(m)

    # "initial" class order comes from the given class-order file (csto2's suite order),
    # restricted to classes we actually traced.
    initial_classes = [c.strip() for c in open(class_order_path) if c.strip() and c.strip() in by_class]
    # append any traced class missing from the class-order file, in discovery order
    for c in by_class:
        if c not in initial_classes:
            initial_classes.append(c)

    class_total = {c: sum(g(m) for m in by_class[c]) for c in by_class}
    pkg_total = collections.defaultdict(int)
    for c, t in class_total.items():
        pkg_total[c.rsplit(".", 1)[0]] += t
    pkg_initial = list(dict.fromkeys(c.rsplit(".", 1)[0] for c in initial_classes))

    def emit(class_seq, sort_methods):
        out = []
        for c in class_seq:
            ms = by_class[c]
            out += sorted(ms, key=lambda m: -g(m)) if sort_methods else list(ms)
        return out

    def by_pkg(pkg_seq, sort_classes):
        seq = []
        for p in pkg_seq:
            cs = [c for c in initial_classes if c.rsplit(".", 1)[0] == p]
            if sort_classes:
                cs = sorted(cs, key=lambda c: -class_total[c])
            seq += cs
        return seq

    pkgs_sorted = sorted(pkg_initial, key=lambda p: -pkg_total[p])
    classes_sorted = sorted(initial_classes, key=lambda c: -class_total[c])

    arms = {
        "initial":     emit(initial_classes, False),
        "mth":         emit(initial_classes, True),
        "pkg":         emit(by_pkg(pkgs_sorted, False), False),
        "pkg-cls":     emit(by_pkg(pkgs_sorted, True), False),
        "pkg-cls-mth": emit(by_pkg(pkgs_sorted, True), True),
        "cls":         emit(classes_sorted, False),
        "cls-mth":     emit(classes_sorted, True),
    }

    baseline = sorted(arms["initial"])
    for name, order in arms.items():
        assert sorted(order) == baseline, "arm %s lost/gained methods" % name
        with open("%s/%s.order" % (out_dir, name), "w") as f:
            f.write("\n".join(order) + "\n")

    def switches(o):
        return 1 + sum(1 for a, b in zip(o, o[1:]) if cls_of(a) != cls_of(b))
    n_classes = len(by_class)
    for name, order in arms.items():
        assert switches(order) == n_classes, "arm %s interleaves classes" % name
    print("methods=%d classes=%d packages=%d" % (len(methods), n_classes, len(pkg_initial)))
    top = classes_sorted[:3]
    tot = sum(class_total.values()) or 1
    print("top-3 classes by alloc: " + ", ".join(
        "%s %.0f%%" % (c.rsplit(".", 1)[-1], 100.0 * class_total[c] / tot) for c in top))


if __name__ == "__main__":
    main()
