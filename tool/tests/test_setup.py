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
