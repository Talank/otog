#!/usr/bin/env python3
#
# usage: python3 scripts/surefire_times.py <run_dir | order_dir>
#
# The one place surefire reports are read. Test runtime always comes from here,
# never from a summary csv. A csv is a rendering of this data, not a source: the
# old one joined report names onto the requested order by exact string, and
# JUnit 5 records a parameterised method as "method(TestInfo)" (plus "[1]",
# "[2]" per permutation), which that join missed -- in module 20 it missed 182
# of 252 entries and left 98% of the measured time at fabricated positions.
#
#   per_test(run_dir)       {"class#method": (seconds, status)} as surefire named them
#   total(run_dir)          the suite's surefire seconds -- the runtime metric
#   in_order(run_dir)       [(test, seconds, status)] in the order asked for
#   order_profile(dir)      the same across an order's plain repetitions
#
# Timings come from plain runs only. jfr_run_* are never read for runtime: the
# recording inflates what it measures, so those seconds are not comparable.
#
# A test the order asked for that the build never ran is absent, not zero: an
# order file is the order requested, not a log of what executed.

import os
import sys
import xml.etree.ElementTree as ET

RANK = {"PASS": 0, "SKIP": 1, "FAIL": 2}


def base(name):
    """'m(TestInfo)[1]' -> 'm'. The name an order file would use."""
    for cut in ("(", "["):
        i = name.find(cut)
        if i > 0:
            name = name[:i]
    return name


def worse(a, b):
    return a if RANK[a] >= RANK[b] else b


def cases(path):
    """(classname, method, time, status) per testcase, in bounded memory.

    iterparse, not parse: a surefire report can be gigabytes of captured stdout
    -- module 3320 writes a 1.9 GB TEST-TestSuite.xml for 505 tests -- and
    building the whole tree for one of those needs far more memory than this
    login node allows a user (8 GiB), which is what killed the first rebuild.
    Each system-out/system-err is released the moment it closes and each
    testcase the moment it is read, so peak memory is one test's captured
    output rather than the whole file.
    """
    status = "PASS"
    try:
        for _, elem in ET.iterparse(path, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag in ("system-out", "system-err", "properties"):
                elem.clear()            # the bytes we never want
            elif tag in ("failure", "error"):
                status = "FAIL"
            elif tag == "skipped":
                if status == "PASS":    # a failure already seen outranks it
                    status = "SKIP"
            elif tag == "testcase":
                yield (elem.get("classname") or "", elem.get("name") or "",
                       elem.get("time"), status)
                status = "PASS"
                elem.clear()
    except (ET.ParseError, OSError):
        return


def per_test(run_dir):
    """{class#method: (seconds, status)} from one run's surefire reports.

    A class-level record -- surefire writes one with no method name when a whole
    class is skipped, or errors before any method runs -- is kept under the class
    alone. It is NOT copied onto each method: a class with 20 methods and one
    5 s class record cost 5 s, not 100 s.
    """
    out = {}
    d = os.path.join(run_dir, "surefire-reports")
    try:
        entries = os.listdir(d)
    except OSError:
        return out
    for name in entries:
        if not (name.startswith("TEST-") and name.endswith(".xml")):
            continue
        for cls, meth, t, status in cases(os.path.join(d, name)):
            if not cls:
                continue
            try:
                secs = float((t or "0").replace(",", ""))
            except ValueError:
                secs = 0.0
            key = "%s#%s" % (cls, meth) if meth else cls
            prev = out.get(key)
            # a rerun of the same test in one report: keep the worse status
            if prev is None or RANK[status] > RANK[prev[1]]:
                out[key] = (secs, status)
    return out


def total(run_dir):
    """The suite's surefire seconds. Every record counts exactly once."""
    return sum(s for s, _ in per_test(run_dir).values())


def order_file(run_dir):
    """The tests this run was asked to run, in order. order_effective.txt is what
    remained once hanging tests were dropped; order.txt is what was asked for."""
    for name in ("order_effective.txt", "order.txt"):
        try:
            with open(os.path.join(run_dir, name)) as f:
                tests = [l.strip() for l in f if l.strip()]
            if tests:
                return tests
        except OSError:
            continue
    return []


def in_order(run_dir):
    """[(test, seconds, status)] in execution order, and what the order never named.

    Records match the order on the parameter-stripped name, so 'm(TestInfo)[1]'
    and '[2]' both land on the entry that asked for 'm', their seconds summed and
    the worse status kept -- an order file permutes them as one unit. Class-level
    records carry no method, so they match nothing and stay unplaced; total()
    still counts them, because it asks what the suite cost, not what ran where.
    """
    times = per_test(run_dir)
    order = order_file(run_dir)
    index = {}
    for t in order:
        cls, _, meth = t.partition("#")
        index.setdefault((cls, base(meth)), t)
    slot, unplaced = {}, {}
    for key, (secs, status) in times.items():
        cls, _, meth = key.partition("#")
        t = index.get((cls, base(meth)))
        if t is None:
            unplaced[key] = (secs, status)
            continue
        prev = slot.get(t)
        slot[t] = (secs, status) if prev is None else (prev[0] + secs, worse(prev[1], status))
    return [(t, slot[t][0], slot[t][1]) for t in order if t in slot], unplaced


def run_dirs(order_dir):
    """The plain repetitions of one order: run_1, run_2, ... in order.

    jfr_run_* are deliberately never returned. JFR recording inflates the very
    thing being measured, so a profiled run's surefire times are not comparable
    with a plain one's and must not be mixed into a timing average. Recordings
    are still read as recordings -- by the approaches that want .jfr events --
    just never as runtime. An order with only profiled runs therefore has no
    runtime here, which is correct rather than missing.
    """
    try:
        names = os.listdir(order_dir)
    except OSError:
        return []
    return sorted((n for n in names if n.startswith("run_")),
                  key=lambda n: (len(n), n))


def order_profile(order_dir):
    """[(test, [seconds per rep], [status per rep])] in execution order.

    Repetitions stay separate -- 3, 4, 5 or however many have been run -- so a
    held-out one is available for honest validation. A test missing from one
    repetition's reports is missing from its lists, not zero. Plain runs only.
    This is the loader every approach and analysis uses.
    """
    seq, secs, states = [], {}, {}
    for name in run_dirs(order_dir):
        placed, _ = in_order(os.path.join(order_dir, name))
        for t, s, st in placed:
            if t not in secs:
                secs[t], states[t] = [], []
                seq.append(t)
            secs[t].append(s)
            states[t].append(st)
    return [(t, secs[t], states[t]) for t in seq]


def main(path):
    """Report one run dir, or one order dir if that is what was given."""
    if os.path.isdir(os.path.join(path, "surefire-reports")):
        placed, unplaced = in_order(path)
        print("surefire records : %d" % len(per_test(path)))
        print("total seconds    : %.3f" % total(path))
        print("placed in order  : %d" % len(placed))
        print("not in the order : %d" % len(unplaced))
        return
    seq = order_profile(path)
    runs = run_dirs(path)
    print("plain reps       : %d" % len(runs))
    print("tests placed     : %d" % len(seq))
    for name in runs:
        print("  %-10s %.3f s" % (name, total(os.path.join(path, name))))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: surefire_times.py <run_dir | order_dir>")
    main(sys.argv[1])
