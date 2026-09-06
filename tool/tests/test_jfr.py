"""JFR profiling is opt-in and must stay that way: an unprofiled run is the
measurement, and a profiled one costs ~8% and cannot be averaged with it.

These tests pin the two things that silently ruin a JFR campaign -- profiling
nothing, and profiling something we cannot attribute to a test class."""

import os
import subprocess
from subprocess import PIPE
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JFR = REPO / "container" / "jfr.sh"


def call(snippet, java_version="17", env=None):
    """Run a jfr.sh function with a stub `java` and stub message printers."""
    e = dict(os.environ, OTOG_JFR="true", PATH=os.environ["PATH"])
    if env:
        e.update(env)
    prelude = (
        'print_info_message() { :; }\n'
        'print_fail_message() { echo "FAIL: $*"; }\n'
        f'jfr_java_major() {{ echo {java_version}; }}\n'
        f'source "{JFR}"\n'
        f'jfr_java_major() {{ echo {java_version}; }}\n'
    )
    return subprocess.run(["bash", "-c", prelude + snippet],
                          env=e, stdout=PIPE, stderr=PIPE, universal_newlines=True)


# --- off unless asked for -------------------------------------------------

def test_nothing_happens_without_otog_jfr(tmp_path):
    # The default path must not even create the directory: a stray empty jfr/
    # in a plain run is how a campaign starts looking profiled when it is not.
    out = call(f'jfr_before_mvn "{tmp_path}"; echo "opts=[${{JAVA_TOOL_OPTIONS:-}}]"',
               env={"OTOG_JFR": ""})
    assert "opts=[]" in out.stdout
    assert not (tmp_path / "jfr").exists()


def test_false_and_zero_are_off():
    for value in ("false", "0", ""):
        out = call('jfr_enabled && echo ON || echo OFF', env={"OTOG_JFR": value})
        assert out.stdout.strip() == "OFF", f"OTOG_JFR={value!r} enabled profiling"


# --- what gets recorded ---------------------------------------------------

def test_java_major_survives_a_java_tool_options_already_set():
    # Entrypoint sets JAVA_TOOL_OPTIONS for MaxRAM before jfr_before_mvn runs,
    # and any JVM invoked with it set prints "Picked up JAVA_TOOL_OPTIONS: ..."
    # as its first stderr line, pushing the version string to line 2.
    out = subprocess.run(
        ["bash", "-c",
         'java() { echo "Picked up JAVA_TOOL_OPTIONS: -XX:MaxRAM=16g" >&2\n'
         '         echo \'openjdk version "17.0.19" 2026-04-21\' >&2; }\n'
         f'source "{JFR}"\njfr_java_major'],
        env=dict(os.environ, OTOG_JFR="true"),
        stdout=PIPE, stderr=PIPE, universal_newlines=True)
    assert out.stdout.strip() == "17"


def test_java_major_parses_both_version_schemes():
    for reported, want in (('1.8.0_502', '8'), ('11.0.21', '11'),
                           ('17.0.19', '17'), ('21.0.4', '21')):
        out = subprocess.run(
            ["bash", "-c",
             f'java() {{ echo \'openjdk version "{reported}"\' >&2; }}\n'
             f'source "{JFR}"\njfr_java_major'],
            env=dict(os.environ, OTOG_JFR="true"),
            stdout=PIPE, stderr=PIPE, universal_newlines=True)
        assert out.stdout.strip() == want, f"{reported} parsed as {out.stdout!r}"


def test_stackdepth_is_raised_on_every_java_version(tmp_path):
    # JFR truncates at 64 frames by default, which cuts the test's own frame
    # out of a maven -> surefire -> junit stack -- the one frame we attribute by.
    for version in ("8", "11", "17", "21"):
        out = call(f'jfr_java_flags "{tmp_path}"', java_version=version)
        assert "stackdepth=1024" in out.stdout, f"java {version} kept the default 64"


def test_probo_events_and_agent_only_on_17_and_up(tmp_path):
    # jdk.ObjectAllocationSample, the per-event (#) syntax and the jdk.jfr API
    # the agent needs all arrive in JDK 17; on 8 and 11 the VM refuses to start.
    for version in ("8", "11"):
        out = call(f'jfr_java_flags "{tmp_path}"', java_version=version)
        assert "#" not in out.stdout, f"java {version} would fail to boot"
        assert "-javaagent" not in out.stdout

    out = call(f'jfr_java_flags "{tmp_path}"', java_version="17")
    assert "jdk.ObjectAllocationSample#throttle" in out.stdout


def test_recordings_are_written_into_the_run_not_the_repo(tmp_path):
    # A fixed filename would have maven and the fork overwrite each other, and
    # a repo-relative one would leave .jfr files in the checkout to be swept up.
    out = call(f'jfr_before_mvn "{tmp_path}"; echo "$JAVA_TOOL_OPTIONS"')
    assert f"filename={tmp_path}/jfr/" in out.stdout
    assert (tmp_path / "jfr").is_dir()


def test_a_rerun_does_not_inherit_the_last_runs_recordings(tmp_path):
    stale = tmp_path / "jfr" / "stale.jfr"
    stale.parent.mkdir(parents=True)
    stale.write_text("old")
    call(f'jfr_before_mvn "{tmp_path}"')
    assert not stale.exists()


# --- what survives the run ------------------------------------------------

def make_recordings(jfr_dir, *pids):
    jfr_dir.mkdir(parents=True, exist_ok=True)
    for pid in pids:
        (jfr_dir / f"hotspot-pid-{pid}-id-1-2026_01_01_00_00_00.jfr").write_text(str(pid))


def test_mavens_own_recording_is_dropped(tmp_path):
    # Maven's launcher JVM runs no tests, so nothing in its recording can be
    # attributed to one; keeping it would double every run's profiling output.
    jfr_dir = tmp_path / "jfr"
    make_recordings(jfr_dir, 100, 200)
    call(f'jfr_after_mvn "{tmp_path}" 100 mymodule')
    assert [f.name for f in jfr_dir.iterdir()] == ["mymodule.jfr"]
    assert (jfr_dir / "mymodule.jfr").read_text() == "200"


def test_a_lone_recording_is_kept_even_if_it_is_mavens(tmp_path):
    # A project whose own pom sets forkCount=0 runs its tests inside maven's
    # JVM. Dropping by pid unconditionally would throw the whole run away.
    jfr_dir = tmp_path / "jfr"
    make_recordings(jfr_dir, 100)
    out = call(f'jfr_after_mvn "{tmp_path}" 100 mymodule')
    assert (jfr_dir / "mymodule.jfr").exists()
    assert "FAIL" not in out.stdout


def test_recordings_are_named_after_the_module(tmp_path):
    jfr_dir = tmp_path / "jfr"
    make_recordings(jfr_dir, 200)
    call(f'jfr_after_mvn "{tmp_path}" 100 core/api')
    # A nested module path would otherwise be read as a directory.
    assert [f.name for f in jfr_dir.iterdir()] == ["core_api.jfr"]


def test_several_forks_are_all_kept_and_numbered(tmp_path):
    # reuseForks=false in the project's own pom gives one recording per fork.
    # A single fixed name would silently keep only the last.
    jfr_dir = tmp_path / "jfr"
    make_recordings(jfr_dir, 200, 300, 400)
    call(f'jfr_after_mvn "{tmp_path}" 100 mymodule')
    assert sorted(f.name for f in jfr_dir.iterdir()) == [
        "mymodule-1.jfr", "mymodule-2.jfr", "mymodule-3.jfr"]


def test_producing_no_recording_is_reported_loudly(tmp_path):
    # Profiling that silently records nothing is the failure that wastes a
    # whole campaign before anyone looks at the output.
    (tmp_path / "jfr").mkdir()
    out = call(f'jfr_after_mvn "{tmp_path}" 100 mymodule')
    assert "FAIL" in out.stdout


# --- invariants the tool must not break -----------------------------------

def test_the_tool_never_configures_surefire_forking():
    # Forking controls JVM state reuse between test classes, which is one of the
    # mechanisms that makes order matter. Setting it would erase part of the
    # effect being measured, not control for it.
    sources = list(REPO.glob("*.sh")) + list((REPO / "container").glob("*.sh"))
    for path in sources:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for option in ("forkCount", "reuseForks", "forkMode"):
                assert option not in line, f"{path.name}:{n} sets {option}"


def test_jfr_flags_never_go_through_argline():
    # surefire reads argLine as ${argLine}, and jacoco's prepare-agent rewrites
    # that property mid-build, so anything sent that way is silently dropped.
    code = "\n".join(line for line in JFR.read_text().splitlines()
                     if not line.lstrip().startswith("#"))
    assert "argLine" not in code


def test_entrypoint_hands_jfr_the_maven_pid_and_module():
    # jfr_after_mvn cannot tell maven's recording from the fork's without the
    # pid, nor name the file without the module.
    text = (REPO / "container" / "entrypoint.sh").read_text()
    assert 'jfr_after_mvn "$out_dir" "$maven_pid" "$module"' in text
    assert 'maven_pid=$!' in text


# --- the profiled run is paired with a plain one --------------------------

def test_jfr_adds_a_profiled_run_beside_every_plain_one(tool, a_module):
    # Profiling costs ~8%, so the comparison has to come from the same order in
    # the same campaign -- not from a plain run collected weeks earlier.
    tool.order(7, 0, 1, ["A#a"])
    out = tool.sh("run_experiment.sh", "--one", 7, 0, 1,
                  env={"JFR": "true", "REPEATS": "2"})
    started = [line.split()[-1] for line in out.stdout.splitlines()
               if line.startswith("DRY")]
    assert [Path(p).name for p in started] == [
        "run_1", "jfr_run_1", "run_2", "jfr_run_2"], out.stdout


def test_a_plain_campaign_starts_no_profiled_runs(tool, a_module):
    tool.order(7, 0, 1, ["A#a"])
    out = tool.sh("run_experiment.sh", "--one", 7, 0, 1)
    assert "jfr_run" not in out.stdout


def test_profiled_and_plain_runs_never_share_a_directory(tool, a_module):
    # Averaging a profiled timing into the plain repetitions would silently
    # inflate every measurement of that order.
    tool.order(7, 0, 1, ["A#a"])
    out = tool.sh("run_experiment.sh", "--one", 7, 0, 1, env={"JFR": "true", "REPEATS": "1"})
    dirs = [line.split()[-1] for line in out.stdout.splitlines() if line.startswith("DRY")]
    assert len(set(dirs)) == len(dirs)


def test_every_knob_can_be_set_without_editing_the_file(tool, a_module):
    # Editing the script to run a subset means the file differs from the one in
    # git, and tool_sha then reports -dirty for every run of that campaign.
    tool.order(7, 0, 1, ["A#a"])
    tool.order(7, 0, 2, ["A#a"])
    out = tool.sh("run_experiment.sh",
                  env={"MODULES": "7", "PHASES": "v0", "ORDERS": "1 2",
                       "REPEATS": "1", "PARALLEL": "1", "JFR": "false"})
    started = [Path(line.split()[-1]).parent.name
               for line in out.stdout.splitlines() if line.startswith("DRY")]
    assert sorted(started) == ["order_1", "order_2"], out.stdout


# --- provenance -----------------------------------------------------------

def test_the_status_file_records_which_tool_version_ran(tool, a_module):
    # A timing whose code cannot be identified cannot be reproduced or trusted
    # once the tool has moved on.
    out = tool.call('tool_sha')
    assert out.returncode == 0


def test_status_stays_readable_with_a_sha_appended(tool):
    # Readers take line 1; a second line must not turn PASS into something else.
    d = tool.path / "runs" / "x"
    d.mkdir(parents=True)
    (d / "status").write_text("PASS\nabc123def456\n")
    out = tool.call(f'run_status "{d}"; run_passed "{d}" && echo YES || echo NO')
    assert out.stdout.split() == ["PASS", "YES"]


def test_a_run_outside_a_git_checkout_still_works(tmp_path):
    # Running from a tarball on a cluster is normal; no .git must not be fatal.
    out = subprocess.run(
        ["bash", "-c", f'tool_dir="{tmp_path}"\n'
                       f'source "{REPO}/lib.sh"\ntool_sha; echo "rc=$?"'],
        stdout=PIPE, stderr=PIPE, universal_newlines=True, cwd=str(tmp_path))
    assert "rc=0" in out.stdout
