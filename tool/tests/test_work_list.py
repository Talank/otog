"""run_experiment.sh decides WHAT runs and in WHICH ORDER. Getting the priority
wrong wastes weeks of cluster time on work that was meant to come last."""


def work_list(tool, modules="", phases="", orders=""):
    """The work list for these arguments, one "<module> <version> <order> <phase>" per line."""
    result = tool.sh("run_experiment.sh", "--list", modules, phases, orders)
    return result, result.stdout.split("\n")


def test_phases_run_in_priority_order(a_module):
    # v0 first, then historical, then x10, then x5. This is the agreed order and
    # the feeder walks the list top to bottom.
    _, lines = work_list(a_module, "7", "v0 historical x10 x5", "1 1")
    versions = [l.split()[1] for l in lines if l.strip()]
    assert versions[0] == "0"
    assert versions[1].startswith("-")
    assert "10" in versions
    assert versions.index("0") < versions.index("-1") < versions.index("10")


def test_a_subset_is_just_a_shorter_argument(a_module):
    # "<module> <version> <order> <phase>". The phase is the 4th column so a
    # consumer -- the JFR gate, or a scheduler reading --list -- can tell which
    # phase a row came from without re-deriving it from the version number.
    _, lines = work_list(a_module, "7", "v0", "1 3")
    rows = [l for l in lines if l.strip()]
    assert rows == ["7 0 1 v0", "7 0 2 v0", "7 0 3 v0"]


def test_the_defaults_come_from_config_not_from_the_script(a_module):
    # An argument left off must fall back to config_default.sh, so a campaign
    # never needs the script edited -- which would make every run report a
    # -dirty tool sha.
    text = (a_module.path / "run_experiment.sh").read_text()
    assert "$otog_modules" in text and "$otog_phases" in text and "$otog_orders" in text


def test_historical_runs_only_its_own_order(a_module):
    # Order n belongs to version -n. Running all 100 orders at every historical
    # version would be 100x the intended work and a different experiment.
    _, lines = work_list(a_module, "7", "historical", "1 100")
    rows = [l.split() for l in lines if l.strip()]
    for module, version, order, phase in rows:
        assert version.lstrip("-") == order, f"{version} should run order {version[1:]}"
        assert phase == "historical"


def test_x10_is_every_tenth_version(a_module):
    _, lines = work_list(a_module, "7", "x10", "1 1")
    versions = sorted({int(l.split()[1]) for l in lines if l.strip()})
    assert versions == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def test_x5_never_overlaps_x10(a_module):
    # The two phases must partition the future versions; an overlap would run
    # the same measurement twice and double-count it.
    _, ten = work_list(a_module, "7", "x10", "1 1")
    _, five = work_list(a_module, "7", "x5", "1 1")
    a = {l.split()[1] for l in ten if l.strip()}
    b = {l.split()[1] for l in five if l.strip()}
    assert a & b == set()


def test_a_literal_version_can_be_used_as_a_phase(a_module):
    _, lines = work_list(a_module, "7", "10", "1 2")
    assert [l for l in lines if l.strip()] == ["7 10 1 10", "7 10 2 10"]


def test_the_plan_is_written_down_before_anything_runs(a_module):
    # work_list.txt is how you check what it is about to do.
    a_module.order(7, 0, 1, ["A#a"])
    a_module.order(7, 0, 2, ["A#a"])
    a_module.sh("run_experiment.sh", "7", "v0", "1 2", "false")
    listed = a_module.path / "work_list.txt"
    assert listed.exists()
    assert len([l for l in listed.read_text().split("\n") if l.strip()]) == 2
