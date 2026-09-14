"""A test that hangs holds a node until the wall clock kills it, and the run
writes no status at all. data/hanging_tests.csv drops those -- from the ORDER,
at run time, because an order run never reads test_list.txt."""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

HEADER = "slug,module,versions,test,status,evidence\n"
ORDER = ["pkg.A#one", "pkg.A#two", "pkg.B#hangs", "pkg.C#three"]


def filter_order(tool, rows, order=ORDER, version="-78"):
    """Run remove_known_hanging_tests over one order and report what survived."""
    (tool.path / "data" / "hanging_tests.csv").write_text(HEADER + "".join(rows))
    (tool.path / "order.txt").write_text("\n".join(order) + "\n")
    (tool.path / "out").mkdir(exist_ok=True)

    out = tool.call(
        'source "$tool_dir/container/runtime.sh"\n'
        'hanging_tests_csv="$tool_dir/data/hanging_tests.csv"\n'
        'remove_known_hanging_tests "$tool_dir/order.txt" own/repo mod %s "$tool_dir/out"'
        ' > /dev/null 2>&1 || echo REFUSED\n'
        'cat "$effective_order_file"' % version)
    removed = (tool.path / "out" / "removed_tests.txt").read_text().split()
    return out.stdout.split(), removed, out


def test_an_active_row_drops_the_test_and_records_it(tool):
    kept, removed, _ = filter_order(
        tool, ["own/repo,mod,-78,pkg.B#hangs,active,jstack sat in it for 7h\n"])
    assert kept == ["pkg.A#one", "pkg.A#two", "pkg.C#three"]
    assert removed == ["pkg.B#hangs"]


def test_an_observed_row_changes_nothing(tool):
    # A row starts as observed: recorded with its evidence, changing no test
    # set. Activating one changes what the module measures.
    kept, removed, _ = filter_order(
        tool, ["own/repo,mod,-78,pkg.B#hangs,observed,2 runs hit the wall\n"])
    assert kept == ORDER
    assert removed == []


def test_a_row_only_reaches_the_versions_it_names(tool):
    # Removing from some versions and not others is allowed -- each version
    # stays internally consistent. That is the invariant, not uniformity.
    row = ["own/repo,mod,-78 -79,pkg.B#hangs,active,jstack\n"]
    assert filter_order(tool, row, version="-79")[1] == ["pkg.B#hangs"]
    assert filter_order(tool, row, version="-80")[1] == []


def test_a_star_reaches_every_version(tool):
    row = ["own/repo,mod,*,pkg.B#hangs,active,hangs everywhere\n"]
    assert filter_order(tool, row, version="12")[1] == ["pkg.B#hangs"]
    assert filter_order(tool, row, version="-3")[1] == ["pkg.B#hangs"]


def test_a_bare_class_drops_every_method_of_it(tool):
    # A TestNG module logs one "Running TestSuite" line for a whole run, so the
    # class is often all the evidence can name.
    kept, removed, _ = filter_order(
        tool, ["own/repo,mod,-78,pkg.A,active,suite log names only the class\n"])
    assert kept == ["pkg.B#hangs", "pkg.C#three"]
    assert removed == ["pkg.A#one", "pkg.A#two"]


def test_every_run_records_what_was_removed_even_when_nothing_was(tool):
    # The test set a run used has to be a fact on disk, not something
    # re-derived later from a csv that has moved on since.
    filter_order(tool, [])
    assert (tool.path / "out" / "removed_tests.txt").is_file()


def test_removing_the_whole_order_is_refused(tool):
    # An empty -Dtest= runs the entire suite, which would be a silent swap of
    # the thing being measured.
    _, _, out = filter_order(
        tool, ["own/repo,mod,-78,pkg.A,active,x\n"
               "own/repo,mod,-78,pkg.B,active,x\n"
               "own/repo,mod,-78,pkg.C,active,x\n"])
    assert "REFUSED" in out.stdout


def test_the_order_as_handed_over_is_kept_beside_what_ran(tool):
    # order.txt is compared against the order it is filed under, so it must
    # stay the full order; order_effective.txt is what actually ran.
    filter_order(tool, ["own/repo,mod,-78,pkg.B#hangs,active,jstack\n"])
    assert (tool.path / "order.txt").read_text().split() == ORDER
    assert (tool.path / "out" / "order_effective.txt").is_file()


# --- the wiring ------------------------------------------------------------

def test_the_registry_is_applied_to_every_order_run():
    # Defined but never called would look completely healthy.
    entry = (REPO / "container" / "entrypoint.sh").read_text()
    assert 'remove_known_hanging_tests "$order_file" "$slug" "$module" "$version" "$out_dir"' in entry
    assert '-Dtest="$effective_order_file"' in entry, "the run used the unfiltered order"


def test_a_hand_started_run_gets_the_same_removals(tool):
    # The registry is keyed on the VERSION, and run_once.sh derives that from
    # the sha rather than requiring it -- so an order of your own, run by hand,
    # drops the same tests as the numbered orders it will be compared with.
    once = (REPO / "run_once.sh").read_text()
    assert 'version=${VERSION:-$(version_of "$slug" "$module" "$sha")}' in once
    assert '--env "VERSION=$version"' in once

    tool.versions([(7, -78, "own/repo", "mod", "sha078")])
    out = tool.call('version_of own/repo mod sha078')
    assert out.stdout.strip() == "-78", out.stdout + out.stderr


def test_the_shipped_registry_is_well_formed():
    # Evidence fields are prose full of commas, which is safe only because
    # evidence is the LAST column and versions are space-separated.
    rows = (REPO / "data" / "hanging_tests.csv").read_text().splitlines()
    assert rows[0] == "slug,module,versions,test,status,evidence"
    for row in rows[1:]:
        slug, module, versions, test, status = row.split(",")[:5]
        assert "/" in slug, row
        assert status in ("active", "observed"), row
        assert versions == "*" or all(v.lstrip("-").isdigit() for v in versions.split()), row
        assert "," not in test and " " not in test, row
        assert len(row.split(",")) >= 6 and row.split(",", 5)[5].strip(), "no evidence: " + row


def test_an_observed_row_in_the_shipped_registry_drops_nothing(tool):
    # The registry is mostly observations. Only two rows are meant to change a
    # test set; a typo flipping one of the others would change a module's
    # measurement silently.
    import shutil
    shutil.copy(REPO / "data" / "hanging_tests.csv", tool.path / "data" / "hanging_tests.csv")
    observed = [r.split(",") for r in
                (REPO / "data" / "hanging_tests.csv").read_text().splitlines()[1:]
                if r.split(",")[4] == "observed"]
    assert observed, "no observed rows left to check"

    for slug, module, versions, test, _status, *_ in observed:
        version = "1" if versions == "*" else versions.split()[0]
        (tool.path / "order.txt").write_text(test + "\nkeep.Me#always\n")
        (tool.path / "out").mkdir(exist_ok=True)
        tool.call('source "$tool_dir/container/runtime.sh"\n'
                  'hanging_tests_csv="$tool_dir/data/hanging_tests.csv"\n'
                  'remove_known_hanging_tests "$tool_dir/order.txt" %s %s %s "$tool_dir/out"'
                  % (slug, module, version))
        dropped = (tool.path / "out" / "removed_tests.txt").read_text().split()
        assert dropped == [], "observed row dropped %s at %s: %s" % (test, version, dropped)
