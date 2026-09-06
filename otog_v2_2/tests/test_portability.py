"""This tree is meant to be unzipped anywhere and just work. These are the
things that quietly tie it to one machine."""

import re
import stat
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHELL = sorted(REPO.glob("*.sh")) + sorted((REPO / "container").glob("*.sh"))
DOCS = sorted(REPO.glob("*.md")) + sorted((REPO / "docs").glob("*.md"))


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


def test_the_readme_only_points_at_files_that_exist():
    readme = (REPO / "README.md").read_text()
    for link, _ in re.findall(r'\]\((docs/[^)]+|[a-z_]+\.(sh|md))\)', readme):
        assert (REPO / link).exists(), f"README links to missing {link}"


def test_there_is_a_tutorial_for_each_platform():
    for name in ("HOPPER.md", "CLOUDLAB.md", "AWS.md"):
        assert (REPO / "docs" / name).exists()


def test_docs_do_not_promise_flags_the_scripts_do_not_have():
    # A tutorial that shows a flag which does not exist wastes the reader's
    # time at exactly the moment they are trusting it.
    scripts = " ".join(f.read_text() for f in SHELL)
    for doc in DOCS:
        for flag in set(re.findall(r'(?<!-)--[a-z][a-z-]{2,}', doc.read_text())):
            if flag in ("--cpuset-cpus", "--memory-swap", "--only-show-errors",
                        "--partial", "--sandbox"):
                continue
            if flag.startswith("--") and flag in scripts:
                continue
            # SLURM/docker/aws flags are not ours to define
            assert not flag.startswith("--otog"), f"{doc.name} invents {flag}"
