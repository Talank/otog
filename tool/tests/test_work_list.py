"""run_experiment.sh decides WHAT runs and in WHICH ORDER. Getting the priority
wrong wastes weeks of cluster time on work that was meant to come last."""


def work_list(tool, **variables):
    """Run run_experiment.sh with the top-of-file variables overridden."""
    text = (tool.path / "run_experiment.sh").read_text()
    for key, value in variables.items():
        import re
        text = re.sub(rf'^{key}=.*$', f'{key}="{value}"', text, count=1, flags=re.M)
    (tool.path / "subset.sh").write_text(text)
    result = tool.sh("subset.sh")
    listed = tool.path / "work_list.txt"
    return result, (listed.read_text().split("\n") if listed.exists() else [])


def test_phases_run_in_priority_order(a_module):
    # v0 first, then historical, then x10, then x5. This is the agreed order and
    # the feeder walks the list top to bottom.
    _, lines = work_list(a_module, MODULES="7", PHASES="v0 historical x10 x5",
                         ORDERS="1 1")
    versions = [l.split()[1] for l in lines if l.strip()]
    assert versions[0] == "0"
    assert versions[1].startswith("-")
    assert "10" in versions
    assert versions.index("0") < versions.index("-1") < versions.index("10")


def test_a_subset_is_just_a_shorter_variable(a_module):
    _, lines = work_list(a_module, MODULES="7", PHASES="v0", ORDERS="1 3")
    rows = [l for l in lines if l.strip()]
    assert rows == ["7 0 1", "7 0 2", "7 0 3"]


def test_historical_runs_only_its_own_order(a_module):
    # Order n belongs to version -n. Running all 100 orders at every historical
    # version would be 100x the intended work and a different experiment.
    _, lines = work_list(a_module, MODULES="7", PHASES="historical", ORDERS="1 100")
    rows = [l.split() for l in lines if l.strip()]
    for module, version, order in rows:
        assert version.lstrip("-") == order, f"{version} should run order {version[1:]}"


def test_x10_is_every_tenth_version(a_module):
    _, lines = work_list(a_module, MODULES="7", PHASES="x10", ORDERS="1 1")
    versions = sorted({int(l.split()[1]) for l in lines if l.strip()})
    assert versions == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def test_x5_never_overlaps_x10(a_module):
    # The two phases must partition the future versions; an overlap would run
    # the same measurement twice and double-count it.
    _, ten = work_list(a_module, MODULES="7", PHASES="x10", ORDERS="1 1")
    _, five = work_list(a_module, MODULES="7", PHASES="x5", ORDERS="1 1")
    a = {l.split()[1] for l in ten if l.strip()}
    b = {l.split()[1] for l in five if l.strip()}
    assert a & b == set()


def test_a_literal_version_can_be_used_as_a_phase(a_module):
    _, lines = work_list(a_module, MODULES="7", PHASES="10", ORDERS="1 2")
    assert [l for l in lines if l.strip()] == ["7 10 1", "7 10 2"]


def test_the_plan_is_written_down_before_anything_runs(a_module):
    # work_list.txt is how you check what it is about to do.
    _, lines = work_list(a_module, MODULES="7", PHASES="v0", ORDERS="1 2")
    assert (a_module.path / "work_list.txt").exists()
    assert len([l for l in lines if l.strip()]) == 2
