"""Setup has to produce the same machine everywhere -- Hopper, a Linux box or a
laptop -- because the container IS the measurement. These pin the parts of that
which can go wrong quietly: the wrong container size, or missing orders."""

import os
import subprocess
import zipfile
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


FORK_VERSION = "3.0.0-M8-SNAPSHOT"
ORDERER = "org/apache/maven/surefire/junitplatform/TestOrderMethodOrderer.class"
PROVIDER = "org/apache/maven/surefire/junitplatform/JUnitPlatformProvider.class"


def seed_fork(tool, entries, extra_jars=()):
    """dependency/ shaped like the seeded maven repo, plus the shipped aux jar."""
    dep = tool.path / "dependency" / "org" / "apache" / "maven"
    (dep / "plugins" / "maven-surefire-plugin" / FORK_VERSION).mkdir(parents=True)
    provider = dep / "surefire" / "surefire-junit-platform" / FORK_VERSION
    provider.mkdir(parents=True)

    def jar(path, names):
        with zipfile.ZipFile(path, "w") as z:
            for name in names:
                z.writestr(name, "x")

    jar(provider / f"surefire-junit-platform-{FORK_VERSION}.jar", entries)
    for suffix, names in extra_jars:
        jar(provider / f"surefire-junit-platform-{FORK_VERSION}-{suffix}.jar", names)

    aux = tool.path / "aux"
    aux.mkdir(exist_ok=True)
    (aux / "surefire-changing-maven-extension-1.0-SNAPSHOT.jar").write_text("jar")


def check_fork(tool, repeat=1):
    # pipefail is on in setup.sh, and it is what made this check flaky.
    return tool.call(f'set -o pipefail\n{methods_of("setup.sh")}\n'
                     'fails=0\n'
                     f'for i in $(seq 1 {repeat}); do\n'
                     '    check_surefire_fork > /dev/null 2>&1 || fails=$((fails+1))\n'
                     'done\n'
                     'echo "fails=$fails"')


def test_setup_compiles_nothing_on_the_host():
    # Everything needing a compiler ships prebuilt: the surefire fork in
    # dependency/, the two small jars in aux/. Building on the host meant setup
    # broke on any machine whose JDK was newer than the sources expected -- a
    # JDK 25 laptop could not set up a tool whose builds all happen in
    # containers targeting JDK 8.
    text = (REPO / "setup.sh").read_text()
    logic = text.split("# LOGIC", 1)[1]
    for command in ("mvn ", "javac ", "cherry-pick", "git clone"):
        assert command not in text, "setup.sh compiles on the host: %r" % command
    assert "check_surefire_fork" in logic and "check_jfrsort_agent" in logic


def test_the_fork_check_survives_the_sigpipe_race(tool):
    # `unzip -l | grep -q` let grep exit on the match, which SIGPIPEd unzip,
    # which pipefail reported as a failed check: a measured 8% of runs called a
    # correct dependency/ "built without PR #15". That sent setup down a host
    # maven build that could not work. The listing here is long and the match
    # is near the front, which is exactly when the old code raced.
    seed_fork(tool, [ORDERER, PROVIDER] + ["pad/%d.class" % i for i in range(200)])
    out = check_fork(tool, repeat=60)
    assert "fails=0" in out.stdout, out.stdout + out.stderr


def test_a_javadoc_jar_cannot_stand_in_for_the_real_one(tool):
    # -javadoc and -sources sort ahead of the real jar and name the class in an
    # .html or .java entry. A globbed, token-matching check passes on them --
    # so a fork built WITHOUT PR #15 would be waved through, silently, which is
    # the one thing this check exists to prevent. Maven's release profiles
    # attach both, so a rebuilt dependency.zip is likely to contain them.
    seed_fork(tool, [PROVIDER], extra_jars=[
        ("javadoc", ["org/apache/maven/surefire/junitplatform/TestOrderMethodOrderer.html"]),
        ("sources", ["org/apache/maven/surefire/junitplatform/TestOrderMethodOrderer.java"]),
    ])
    out = check_fork(tool)
    assert "fails=1" in out.stdout, out.stdout + out.stderr


def test_setup_refuses_a_checkout_without_the_order_extension(tool):
    # Maven ignores a -Dmaven.ext.class.path that does not exist -- no warning,
    # BUILD SUCCESS -- and then keeps whatever surefire the project's own pom
    # asks for. The run passes having imposed no order at all.
    seed_fork(tool, [ORDERER, PROVIDER])
    (tool.path / "aux" / "surefire-changing-maven-extension-1.0-SNAPSHOT.jar").unlink()
    out = check_fork(tool)
    assert "fails=1" in out.stdout, out.stdout + out.stderr
