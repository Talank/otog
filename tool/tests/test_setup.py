"""Setup has to produce the same machine everywhere -- Hopper, a Linux box or a
laptop -- because the container IS the measurement. These pin the parts of that
which can go wrong quietly: the wrong container size, or missing orders."""

import os
import subprocess
from subprocess import PIPE
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_orders_and_the_zip_are_both_ignored():
    # 17 GB unpacked and 2 GB zipped: committing either would be unrecoverable.
    ignored = (REPO / ".gitignore").read_text().split()
    assert "orders/" in ignored
    assert "orders.zip" in ignored


def test_setup_fetches_the_orders_before_it_says_it_is_done():
    text = (REPO / "setup.sh").read_text()
    logic = text.split("# LOGIC", 1)[1]
    assert logic.index("fetch_orders") < logic.index("report")


def methods_of(script):
    """The script's functions alone -- no argument parsing, no LOGIC pipeline."""
    text = (REPO / script).read_text()
    return text.split("# METHODS", 1)[1].split("# LOGIC", 1)[0]


def test_setup_is_rerunnable_when_the_orders_are_already_there(tool):
    # Re-running setup must never re-download 2 GB.
    (tool.path / "orders" / "1685").mkdir(parents=True)
    out = tool.call(f'{methods_of("setup.sh")}\n'
                    f'otog_orders_dir="{tool.path}/orders"\n'
                    'fetch_orders')
    assert out.returncode == 0
    assert "have   orders/" in out.stdout


def test_setup_stops_rather_than_running_without_orders(tool):
    # A campaign that starts with no orders produces nothing but failed runs.
    out = tool.call(f'{methods_of("setup.sh")}\n'
                    f'otog_orders_dir="{tool.path}/orders"\n'
                    'otog_orders_url=""\n'
                    'fetch_orders')
    assert out.returncode != 0


def test_a_google_drive_link_does_not_go_through_curl(tool):
    # A drive link over 100 MB answers with a confirm page, and curl would save
    # that HTML as orders.zip -- a corrupt archive nobody notices until unzip.
    out = tool.call('command() { return 1; }\n'
                    'download_file "https://drive.google.com/file/d/abc/view" /dev/null')
    assert "gdown" in out.stdout + out.stderr


def test_the_container_is_the_same_size_on_every_engine():
    # docker gets a cgroup limit; apptainer cannot have one without root, so it
    # checks the allocation instead. Neither may silently run undersized.
    engine = (REPO / "container" / "engine.sh").read_text()
    assert "--memory" in engine and "--cpuset-cpus" in engine
    assert "check_container_size" in (REPO / "lib.sh").read_text()
    assert "check_container_size" in (REPO / "run_once.sh").read_text()


def run_size_check(env):
    e = dict(os.environ, OTOG_ENGINE="apptainer", **env)
    return subprocess.run(
        ["bash", "-c", f'source "{REPO}/lib.sh"\ncheck_container_size'],
        env=e, stdout=PIPE, stderr=PIPE, universal_newlines=True, cwd=str(REPO))


def test_an_undersized_slurm_allocation_is_refused():
    out = run_size_check({"SLURM_JOB_ID": "1", "SLURM_CPUS_ON_NODE": "2",
                          "SLURM_MEM_PER_NODE": "8192"})
    assert out.returncode != 0
    assert "4" in out.stdout + out.stderr


def test_a_correct_slurm_allocation_passes():
    out = run_size_check({"SLURM_JOB_ID": "1", "SLURM_CPUS_ON_NODE": "4",
                          "SLURM_MEM_PER_NODE": "16384"})
    assert out.returncode == 0


def test_off_cluster_runs_are_not_blocked_by_the_check():
    # A laptop has no SLURM variables and must still be able to run.
    assert run_size_check({}).returncode == 0


def test_surefire_fork_is_built_from_source_only_when_the_check_fails():
    # Cloning and building a maven reactor is not something to redo on every
    # setup.sh run -- only when the seeded dependency/ turns out to be missing
    # or wrong.
    logic = (REPO / "setup.sh").read_text().split("# LOGIC", 1)[1]
    assert "check_surefire_fork || build_surefire_fork" in logic


def test_build_surefire_fork_clones_pr15s_own_repo():
    # PR #15 is open, not merged, against TestingResearchIllinois/maven-surefire
    # -- not the upstream apache/maven-surefire, and not a contributor's fork.
    fn = methods_of("setup.sh").split("build_surefire_fork()", 1)[1].split("\n}", 1)[0]
    assert "TestingResearchIllinois/maven-surefire" in fn
    assert "refs/pull/15/head" in fn


def test_build_surefire_fork_installs_and_wires_the_extension(tool):
    # Fakes git and mvn so this runs in milliseconds with no network: git
    # "clone" just creates the target dir, and "mvn install" drops the
    # extension jar where the real build would -- the same relative path the
    # fork's own README gives for it. The seeded .m2 stands in for what a real
    # `mvn install` would have populated.
    home = tool.path / "home"
    m2 = home / ".m2" / "repository" / "org" / "apache" / "maven"
    for kind, sub in (("surefire", "surefire/surefire-junit-platform"),
                      ("plugins", "plugins/maven-surefire-plugin")):
        d = m2 / sub / "3.0.0-M8-SNAPSHOT"
        d.mkdir(parents=True)
        (d / "artifact.jar").write_text("jar")

    fakebin = tool.path / "fakebin"
    fakebin.mkdir()
    (fakebin / "git").write_text(
        "#!/bin/bash\n"
        'for a in "$@"; do case "$a" in\n'
        '    clone) mkdir -p "${@: -1}"; exit 0 ;;\n'
        '    merge-base) exit 1 ;;\n'
        'esac; done\n'
        "exit 0\n")
    (fakebin / "mvn").write_text(
        "#!/bin/bash\n"
        'ext="$PWD/surefire-changing-maven-extension/target"\n'
        'mkdir -p "$ext"\n'
        'echo jar > "$ext/surefire-changing-maven-extension-1.0-SNAPSHOT.jar"\n')
    (fakebin / "git").chmod(0o755)
    (fakebin / "mvn").chmod(0o755)

    out = tool.call(f'{methods_of("setup.sh")}\nbuild_surefire_fork',
                     env={"HOME": str(home),
                          "PATH": f"{fakebin}:{os.environ['PATH']}"})

    assert out.returncode == 0, out.stdout + out.stderr
    dep = tool.path / "dependency" / "org" / "apache" / "maven"
    assert (dep / "surefire" / "surefire-junit-platform" /
            "3.0.0-M8-SNAPSHOT" / "artifact.jar").is_file()
    assert (dep / "plugins" / "maven-surefire-plugin" /
            "3.0.0-M8-SNAPSHOT" / "artifact.jar").is_file()
    assert (tool.path / "aux" /
            "surefire-changing-maven-extension-1.0-SNAPSHOT.jar").is_file()
