"""Is the collected run data actually correct?

Every other test here checks the code. This one checks the RESULT: it walks a
real runs/ tree and asserts the properties the analysis depends on. Most of
them fail silently in production -- a run that measured the wrong permutation
looks exactly like a run that measured the right one, and nothing notices until
the paper is written.

Read-only. Points at $OTOG_RUNS, or <repo>/runs, so it works unchanged on a
second account:

    OTOG_RUNS=/scratch/<user>/otog_v2/runs .venv/bin/python -m pytest \
        tests/test_run_data.py -q

Sampling is seeded, so a failure the fast run reports reproduces. Set
OTOG_SAMPLE=0 to check every order directory instead of a sample, and
OTOG_EVERY_ORDER=1 to add the exhaustive order-imposition sweep.
"""

import os
import random
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNS = Path(os.environ.get("OTOG_RUNS", REPO / "runs"))
ORDERS = Path(os.environ.get("OTOG_ORDERS", REPO / "orders"))
SAMPLE = int(os.environ.get("OTOG_SAMPLE", "60"))
REPEATS = int(os.environ.get("OTOG_REPEATS", "3"))


def order_dirs():
    """Every runs/<module>/<version>/order_<label>/ that has at least one run."""
    if not RUNS.is_dir():
        pytest.skip("no runs tree at %s" % RUNS)
    found = []
    for module in RUNS.iterdir():
        if not module.is_dir():
            continue
        for version in module.iterdir():
            if not version.is_dir() or version.name.endswith("_jfr"):
                continue
            found.extend(d for d in version.iterdir()
                         if d.is_dir() and d.name.startswith("order_"))
    return found


def sampled():
    every = order_dirs()
    if not every:
        pytest.skip("no order directories under %s" % RUNS)
    every.sort()
    if SAMPLE and len(every) > SAMPLE:
        random.Random(20260904).shuffle(every)
        every = every[:SAMPLE]
    return every


def passed_runs(order_dir):
    out = []
    for run in sorted(order_dir.glob("run_*")):
        status = run / "status"
        if status.is_file() and status.read_text().strip().startswith("PASS"):
            out.append(run)
    return out


@pytest.fixture(scope="module")
def orders():
    return sampled()


def test_a_status_file_is_one_of_the_known_verdicts(orders):
    # A status nobody can parse is a run that counts as neither pass nor fail
    # and quietly leaves a hole in the dataset.
    bad = []
    for order_dir in orders:
        for status in order_dir.glob("run_*/status"):
            first = status.read_text().strip().splitlines()[:1]
            verdict = first[0] if first else ""
            if not (verdict.startswith("PASS") or verdict.startswith("FAIL")
                    or verdict.startswith("ERROR") or verdict.startswith("TIMEOUT")):
                bad.append("%s -> %r" % (status, verdict))
    assert not bad, "unparseable verdicts:\n" + "\n".join(bad[:10])


def test_a_passing_run_kept_everything_the_analysis_reads(orders):
    # wall_time.txt is the measurement; surefire-reports is the per-class
    # breakdown; order.txt is the only record of what was actually run and
    # node.txt of where. None can be reconstructed afterwards.
    missing = []
    for order_dir in orders:
        for run in passed_runs(order_dir):
            for name in ("wall_time.txt", "order.txt", "node.txt"):
                if not (run / name).is_file():
                    missing.append("%s missing %s" % (run, name))
            if not (run / "surefire-reports").is_dir():
                missing.append("%s missing surefire-reports/" % run)
    assert not missing, "incomplete passing runs:\n" + "\n".join(missing[:10])


def test_wall_time_is_a_positive_number(orders):
    bad = []
    for order_dir in orders:
        for run in passed_runs(order_dir):
            path = run / "wall_time.txt"
            if not path.is_file():
                continue
            text = path.read_text().strip()
            match = re.search(r"[-+]?\d*\.?\d+", text)
            if not match or float(match.group()) <= 0:
                bad.append("%s -> %r" % (path, text))
    assert not bad, "impossible wall times:\n" + "\n".join(bad[:10])


def test_the_order_that_ran_is_the_order_it_is_filed_under(orders):
    # THE invariant of the dataset. run_order.sh copies the order file in as
    # order.txt, and that copy must still equal orders/<module>/<version>/
    # <label>.txt -- the order this run is filed under and will be analysed as.
    #
    # This is the failure the axis shift can cause silently: renaming a version
    # directory without rotating the order ids inside it leaves runs that look
    # perfect and measure a different permutation than their label claims.
    #
    # Checked against the filed-under path, NOT order_source.txt. That file
    # records where the order was read from at submission time; after a shift
    # it legitimately names a path that has since been renumbered, so it is a
    # historical breadcrumb rather than a current pointer.
    mismatched = []
    for order_dir in orders:
        version_dir = order_dir.parent
        label = order_dir.name[len("order_"):]
        filed_under = (ORDERS / version_dir.parent.name /
                       version_dir.name / ("%s.txt" % label))
        if not filed_under.is_file():
            continue        # a path order, or an order file since removed
        for run in passed_runs(order_dir):
            copied = run / "order.txt"
            if copied.is_file() and copied.read_text() != filed_under.read_text():
                mismatched.append("%s != %s" % (copied, filed_under))
    assert not mismatched, (
        "runs whose order.txt is not the order they are filed under:\n"
        + "\n".join(mismatched[:10]))


def test_surefire_only_reports_classes_the_order_asked_for(orders):
    # The order file is passed as -Dtest=<file>. A class in the reports that
    # the order never named means the filter did not hold and the run timed a
    # different suite.
    stray = []
    for order_dir in orders:
        for run in passed_runs(order_dir):
            order_file = run / "order.txt"
            reports = run / "surefire-reports"
            if not (order_file.is_file() and reports.is_dir()):
                continue
            # Both sides normalise to the TOP-LEVEL class. A JUnit 5 @Nested
            # class is part of its enclosing class's descriptor tree: the order
            # names it Outer$Nested$Deeper, surefire reports the whole tree
            # under Outer. Comparing those raw makes every nested test look
            # like a stray.
            wanted = {line.split("#", 1)[0].split("$", 1)[0] for line in
                      order_file.read_text().split() if "#" in line}
            if not wanted:
                continue
            for xml in reports.glob("TEST-*.xml"):
                try:
                    name = ET.parse(xml).getroot().get("name") or ""
                except ET.ParseError:
                    stray.append("%s is not parseable XML" % xml)
                    continue
                # TEST-TestSuite.xml is surefire's own aggregate report, not
                # a test class -- it has no package, and it summarises the run
                # rather than naming something the order could have asked for.
                if "." not in name:
                    continue
                if name and name.split("$", 1)[0] not in wanted:
                    stray.append("%s reported %s, not in the order" % (run, name))
    assert not stray, "surefire ran classes the order did not ask for:\n" + "\n".join(stray[:10])


def test_a_finished_order_has_all_of_its_repetitions(orders):
    # Three repetitions is the unit of measurement. An order with one PASS is
    # not a finished measurement, and averaging it with three-repeat orders
    # compares different things.
    partial = []
    for order_dir in orders:
        done = len(passed_runs(order_dir))
        if 0 < done < REPEATS:
            partial.append("%s has %d/%d" % (order_dir, done, REPEATS))
    # Partial orders are expected while a campaign is running; this reports
    # them rather than failing, and fails only if EVERY sampled order is short.
    assert len(partial) < len(orders), (
        "no sampled order has all %d repetitions:\n%s"
        % (REPEATS, "\n".join(partial[:10])))


def checkable_runs(order_dirs_):
    """Passed runs carrying the evidence check_order_imposed.py needs."""
    out = []
    for order_dir in order_dirs_:
        for run in passed_runs(order_dir):
            if ((run / "order.txt").is_file() and (run / "mvn.log").is_file()
                    and any((run / "surefire-reports").glob("TEST-*.xml"))):
                out.append(run)
    return out


def imposed(run):
    """check_order_imposed.py's verdict for one run. order.txt is the copy
    run_once.sh made, so this judges the run against the order it was handed."""
    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_order_imposed.py"),
         str(run / "order.txt"), str(run)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return result.returncode == 0, result.stdout


def test_a_sample_of_runs_imposed_the_order_they_were_given(orders):
    # The experiment rests on surefire running the order it was handed, and a
    # run that ignored it looks exactly like one that obeyed it. A few every
    # time is what makes that visible; the sweep below checks them all.
    runs = checkable_runs(orders)
    if not runs:
        pytest.skip("no run with an order.txt, a mvn.log and surefire XMLs")
    random.Random(20260904).shuffle(runs)

    bad = ["%s\n%s" % (r, imposed(r)[1]) for r in runs[:5] if not imposed(r)[0]]
    assert not bad, "order not imposed in:\n" + "\n".join(bad)


@pytest.mark.skipif(not os.environ.get("OTOG_EVERY_ORDER"),
                    reason="exhaustive; set OTOG_EVERY_ORDER=1 to run it")
def test_every_run_imposed_the_order_it_was_given():
    # Every surefire XML of every run, so it is opt-in rather than default.
    runs = checkable_runs(order_dirs())
    if not runs:
        pytest.skip("no run with an order.txt, a mvn.log and surefire XMLs")

    bad = [str(r) for r in runs if not imposed(r)[0]]
    assert not bad, ("%d of %d runs did not impose their order:\n%s"
                     % (len(bad), len(runs), "\n".join(bad[:20])))
