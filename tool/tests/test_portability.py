"""This tree is meant to be unzipped anywhere and just work. These are the
things that quietly tie it to one machine.

Documentation is not checked here: a doc that is missing or stale is a thing
you read, not a thing that breaks a run."""

import re
import stat
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHELL = sorted(REPO.glob("*.sh")) + sorted((REPO / "container").glob("*.sh"))


def test_no_script_hardcodes_someone_elses_path():
    # An absolute path from the packaging machine makes the artifact useless to
    # everyone else, and fails at run time rather than at unzip time.
    bad = [f.name for f in SHELL if re.search(r'/(scratch|home)/[a-z][a-z0-9_]*/', f.read_text())]
    assert not bad, f"hardcoded paths in: {bad}"


def test_every_script_derives_its_own_location():
    # tool_dir comes from BASH_SOURCE, so the tree works wherever it is put.
    for name in ("run_once.sh", "run_experiment.sh", "setup.sh"):
        text = (REPO / name).read_text()
        assert 'dirname "${BASH_SOURCE[0]}"' in text, f"{name} does not locate itself"


def test_the_entry_points_are_executable():
    # Only these are run directly; lib.sh, config_default.sh and fix_helper.sh
    # are sourced.
    for name in ("setup.sh", "run_once.sh", "run_experiment.sh"):
        f = REPO / name
        assert f.stat().st_mode & stat.S_IXUSR, f"{name} is not executable"


def test_every_script_parses():
    import subprocess
    for f in SHELL:
        r = subprocess.run(["bash", "-n", str(f)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        assert r.returncode == 0, f"{f.name}: {r.stderr.decode()}"
