#!/usr/bin/env python3
"""Did surefire actually run the tests in the order the order file asked for?

This is the assumption the whole experiment rests on, and it is not
self-evident: the order-imposing surefire fork only controls what the provider
in use lets it control. Run this against a finished run directory whenever the
fork, its cherry-picked PRs, or the JUnit version of a module changes.

Compares, for one run directory:
  - CLASS order: the "Running <class>" lines of mvn.log, in the order maven
    printed them, against the class order implied by the order file.
  - METHOD order: the <testcase> sequence inside each TEST-*.xml (surefire
    writes them in execution order) against that class's methods in the order
    file. This is the half PR #15 exists for: before it, the JUnit 5 provider
    let the Jupiter engine pick method order.

Two caveats are expected, not bugs:
  - Maven's "Running <class>" line names the OUTER class for JUnit 5 @Nested
    classes, so class order is compared at outer-class granularity.
  - A class's tests always run contiguously (PR #15's caveat #1), so an order
    file that re-enters a class it already left cannot be honored exactly.
    Those re-entries are collapsed before comparing.

usage: check_order_imposed.py <order_file> <run_dir>
   e.g. python3 scripts/check_order_imposed.py \
            orders/1685/10/1.txt runs/1685/10/order_1/run_1
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

order_file, run_dir = Path(sys.argv[1]), Path(sys.argv[2])

# --- what was asked for -----------------------------------------------------
wanted = []            # [(class, method)] in order
for line in order_file.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    cls, _, meth = line.partition('#')
    wanted.append((cls, meth))

wanted_classes = []
for cls, _ in wanted:
    if not wanted_classes or wanted_classes[-1] != cls:
        wanted_classes.append(cls)

wanted_methods = {}
for cls, meth in wanted:
    wanted_methods.setdefault(cls, []).append(meth)

# --- what actually ran ------------------------------------------------------
mvn_log = (run_dir / 'mvn.log').read_text(errors='replace')
ran_classes = re.findall(r'^\[INFO\] Running (\S+)$', mvn_log, re.M)
# Maven reports the OUTER class for JUnit 5 @Nested classes, while the order
# file names the nested class. Compare at outer-class granularity, collapsing
# runs of the same outer class.
def outer(c):
    return c.split('$', 1)[0]

ran_outer = []
for c in ran_classes:
    o = outer(c)
    if not ran_outer or ran_outer[-1] != o:
        ran_outer.append(o)

ran_methods = {}
for xml in sorted((run_dir / 'surefire-reports').glob('TEST-*.xml')):
    try:
        root = ET.parse(xml).getroot()
    except ET.ParseError as e:
        print(f'  !! unparseable {xml.name}: {e}')
        continue
    for tc in root.iter('testcase'):
        cls = tc.get('classname')
        # Surefire writes parameterized names as "m(String, int)[1]" and
        # display names in brackets; the order file has the bare method name.
        name = (tc.get('name') or '').split('[')[0].split('(')[0].strip()
        ran_methods.setdefault(cls, []).append(name)

# --- compare ----------------------------------------------------------------
print(f'order file : {order_file}  ({len(wanted)} entries, {len(wanted_classes)} classes)')
print(f'run dir    : {run_dir}')
print(f'ran        : {len(ran_classes)} classes, {sum(len(v) for v in ran_methods.values())} test cases')
print()

# Classes: compare the order file's class sequence, restricted to what ran.
wanted_outer = []
for c in wanted_classes:
    o = outer(c)
    if not wanted_outer or wanted_outer[-1] != o:
        wanted_outer.append(o)

# A class's tests always run contiguously, so an order file that leaves a class
# and comes back to it cannot be honored exactly. Collapse those re-entries to
# their first occurrence -- that is the best any run could do -- and report how
# many there were.
seen, expected_seq = set(), []
reentries = 0
for c in wanted_outer:
    if c in seen:
        reentries += 1
        continue
    seen.add(c)
    if c in set(ran_outer):
        expected_seq.append(c)

class_order_ok = expected_seq == ran_outer
if class_order_ok:
    print(f'✅ CLASS order matches ({len(ran_outer)} outer classes)')
else:
    print(f'❌ CLASS order differs ({len(expected_seq)} expected vs {len(ran_outer)} ran)')

    # HOW it differs matters more than THAT it differs. Rank each class that
    # ran by its position in the requested order and count descents: a run that
    # honoured the order has none, and one descent means the requested order
    # arrived cut into two contiguous blocks -- the signature of the JUnit
    # Platform executing engine by engine, which no surefire fork can
    # interleave. Many descents means the order was genuinely scrambled.
    pos = {c: i for i, c in enumerate(expected_seq)}
    ranks = [pos[c] for c in ran_outer if c in pos]
    if ranks:
        descents = sum(1 for i in range(1, len(ranks)) if ranks[i] < ranks[i - 1])
        blocks, cur = [], 1
        for i in range(1, len(ranks)):
            if ranks[i] > ranks[i - 1]:
                cur += 1
            else:
                blocks.append(cur)
                cur = 1
        blocks.append(cur)
        blocks.sort(reverse=True)
        print(f'   structure : {descents} descent(s), '
              f'largest ordered blocks {blocks[:4]}')
        if descents == 0:
            print('   -> the requested order, in order')
        elif descents <= 2:
            print('   -> the requested order cut into contiguous blocks '
                  '(engine-by-engine execution), not scrambled')
    for i, (e, a) in enumerate(zip(expected_seq, ran_outer)):
        if e != a:
            print(f'   first difference at position {i}: expected {e}, ran {a}')
            break

if reentries:
    print(f'   ({reentries} class re-entries in the order file collapsed -- '
          f'a class cannot be split across the run)')

only_ran = [c for c in set(ran_outer) if c not in set(wanted_outer)]
never_ran = [c for c in set(wanted_outer) if c not in set(ran_outer)]
if only_ran:
    print(f'   ⚠️  {len(only_ran)} class(es) ran that the order file does not name: {only_ran[:3]}')
if never_ran:
    print(f'   ⚠️  {len(never_ran)} class(es) in the order file never ran: {never_ran[:3]}')

# Methods: only classes with more than one method in the order file can tell
# us anything -- a single-method class is trivially in order.
checked = matched = 0
mismatches = []
for cls, methods in wanted_methods.items():
    actual = ran_methods.get(cls)
    if not actual or len(methods) < 2:
        continue
    expected = [m for m in methods if m in set(actual)]
    # Keep only the first occurrence of each (parameterized tests repeat).
    seen, actual_first = set(), []
    for m in actual:
        if m not in seen:
            seen.add(m)
            actual_first.append(m)
    checked += 1
    if expected == actual_first:
        matched += 1
    else:
        mismatches.append((cls, expected, actual_first))

print()
if checked == 0:
    print('⚠️  no multi-method class to check method order with')
elif matched == checked:
    print(f'✅ METHOD order matches in all {checked} multi-method classes')
else:
    print(f'❌ METHOD order differs in {checked - matched} of {checked} multi-method classes')
    for cls, exp, act in mismatches[:3]:
        print(f'   {cls}')
        print(f'     expected: {exp[:6]}')
        print(f'     ran     : {act[:6]}')

# The exit code is the verdict. A run that printed ❌ and exited 0 could not be
# gated on by a test or a CI job, which is the whole point of this check:
#   0 = the order was imposed
#   1 = it was not
#   2 = it could not be judged (nothing ran, or no method evidence at all)
if not ran_outer:
    print('\n❌ nothing ran: no "Running <class>" lines in mvn.log')
    sys.exit(2)
if checked == 0 and not class_order_ok:
    sys.exit(1)
sys.exit(0 if class_order_ok and matched == checked else 1)
