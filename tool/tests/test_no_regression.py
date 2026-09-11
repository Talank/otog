"""Things that were true, stopped being true, and cost a campaign to notice.

Every test here stands for a specific way this tool has silently measured the
wrong thing. None of them fail loudly on their own: a build still "passes", a
run still writes a wall time, an order still gets a verdict. That is what makes
them worth a test rather than a comment.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def config(snippet):
    """Evaluate a snippet with config_default.sh loaded, and return stdout."""
    r = subprocess.run(
        ["bash", "-c", 'source "%s/config_default.sh" > /dev/null 2>&1\n%s'
         % (REPO, snippet)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return r.stdout.strip()


def mvn_opts():
    return config('echo "$MVN_OPTS"')


# --- maven has to survive a compute node -------------------------------------

def test_maven_resolves_through_the_central_mirror():
    # Central answers 429 for every artifact when the request comes from a
    # compute node, and maven records that as a compile failure -- which is
    # indistinguishable from a broken commit. The mirror is the fix, and it
    # only applies if -s actually names the file.
    opts = mvn_opts()
    assert " -s " in " %s " % opts, "MVN_OPTS passes no -s settings file"

    settings = re.search(r'-s\s+(\S+)', opts).group(1)
    assert settings.endswith("settings.xml"), settings
    local = REPO / "aux" / Path(settings).name
    assert local.is_file(), "MVN_OPTS names %s but %s does not exist" % (settings, local)
    assert "<mirror>" in local.read_text(), "%s mirrors nothing" % local


def test_the_shipped_settings_file_is_not_dead_weight():
    # aux/settings.xml was carried forward once while the -s that used it was
    # dropped, so the mirror was shipped, documented, and never applied.
    assert "settings.xml" in mvn_opts(), "aux/settings.xml is shipped but never passed to maven"


def test_maven_trusts_the_seeded_local_repo():
    # The seeded repo records every artifact as coming from repo id `central`,
    # which the mirror renames. Without this flag maven calls each seeded
    # artifact "present, but unavailable" and re-verifies it over the network:
    # 164 needless round trips per run, any one of which can reset the build.
    assert "-Dmaven.legacyLocalRepo=true" in mvn_opts()


def test_transport_faults_are_retried_rather_than_recorded_as_broken_commits():
    for flag in ("-Dmaven.wagon.http.retryHandler.count",
                 "-Dmaven.wagon.http.retryHandler.requestSentEnabled",
                 "-Dmaven.wagon.httpconnectionManager.ttlSeconds",
                 "-Dmaven.wagon.rto",
                 "-Daether.connector.http.retryHandler.count",
                 "-Daether.connector.http.retryHandler.requestSentEnabled",
                 "-Daether.connector.connectTimeout",
                 "-Daether.connector.requestTimeout"):
        assert flag in mvn_opts(), "lost transport hardening: %s" % flag


# --- the right JDK, and a C compiler where one is needed ---------------------

def test_netty_builds_on_an_image_that_has_a_c_toolchain():
    # netty's reactor runs autogen.sh. The run-time native_build_toolchain fix
    # installs one with apt, which needs root and a writable /usr -- true under
    # docker, false under apptainer, where the container runs as the calling
    # user on a read-only image. Baked into the image, it is true under both.
    assert config('image_for_project netty/netty') == config('echo "$image_java8_native"')


def test_setup_builds_the_native_images_it_maps_projects_onto():
    # An image nothing builds is an image every netty run dies on.
    setup = (REPO / "setup.sh").read_text()
    assert "$image_java8_native" in setup and "$image_java11_native" in setup
    assert "build_native_image" in setup


def test_the_native_images_add_a_complete_autotools_chain():
    # libtoolize, not libtool: netty's autogen.sh calls libtoolize, and the
    # libtool script itself is generated per project by configure.
    packages = config('echo "$native_packages"')
    for pkg in ("build-essential", "autoconf", "automake", "libtool"):
        assert pkg in packages, "native image would lack %s" % pkg


def test_the_versions_that_need_another_jdk_actually_get_one():
    # Test sources that do not compile on the project's usual JDK do not fail
    # the build: -fn lets the reactor carry on, so the build is called OK and
    # the test list comes back EMPTY. A wrong answer, not a failure. These
    # boundaries were all missed once by globbing on "$module:$version".
    java11 = config('echo "$image_java11"')
    java21 = config('echo "$image_java21"')
    java11_native = config('echo "$image_java11_native"')

    for module, version, want in (
            (1305, 19, java11), (1305, 20, java11), (1305, 100, java11),
            (1305, 18, ""),
            (1685, -18, java11), (1685, -17, java11), (1685, -19, ""),
            (1216, 87, java21), (1216, 89, java21), (1216, 100, java21),
            (1216, 86, ""), (1216, -90, ""),
            (20, 100, java11_native), (20, 90, ""),
            (7, 0, "")):
        got = config('image_for_version %s %s' % (module, version))
        assert got == want, "module %s v%s -> %r, wanted %r" % (module, version, got, want)


# --- the order actually being imposed ----------------------------------------

def test_the_surefire_fork_version_is_named_in_one_place():
    # It appears in the guard inside the container and in the setup check. Two
    # copies drift, and the drift shows up as "Plugin could not be resolved".
    version = config('echo "$surefire_fork_version"')
    assert version, "surefire_fork_version is not set"
    for f in (REPO / "container" / "entrypoint.sh", REPO / "setup.sh"):
        text = f.read_text()
        assert version not in text, "%s hardcodes %s instead of $surefire_fork_version" % (f.name, version)
        assert "surefire_fork_version" in text, "%s does not check the fork" % f.name


def test_setup_refuses_a_fork_built_without_the_junit5_method_orderer():
    # PR #15 is what makes -Dsurefire.runOrder=testorder control METHOD order on
    # JUnit 5. Without it the provider hands whole classes to the Jupiter engine
    # and the engine picks -- so class order is imposed, method order is not,
    # and every run still passes. The seeded repo arrives as a zip, so the only
    # moment to notice is setup.
    setup = (REPO / "setup.sh").read_text()
    assert "TestOrderMethodOrderer" in setup, "setup does not verify PR #15 is in the fork"
    assert "check_surefire_fork" in setup


def test_the_order_extension_is_shipped_and_wired_in():
    jar = config('echo "$surefire_extension_jar"')
    assert jar.endswith(".jar")
    local = REPO / "aux" / Path(jar).name
    assert local.is_file(), "%s is not shipped in aux/" % jar
    entrypoint = (REPO / "container" / "entrypoint.sh").read_text()
    assert "-Dmaven.ext.class.path=" in entrypoint
    assert "-Dsurefire.runOrder=testorder" in entrypoint


def test_a_class_that_dies_before_its_first_test_is_not_read_as_a_method(tmp_path):
    # A class that fails in @BeforeAll -- a missing native library, say -- gets
    # ONE <testcase name=""> standing for the whole class. Recorded as a method,
    # it leaves the class with a phantom [''] to compare against the methods the
    # order file named, which can only mismatch. The class ran no methods; there
    # is nothing to judge, and the run must not be reported as misordered.
    run = tmp_path / "run_1"
    (run / "surefire-reports").mkdir(parents=True)
    (run / "mvn.log").write_text(
        "[INFO] Running com.example.AliveTest\n"
        "[INFO] Running com.example.DeadTest\n")
    (run / "surefire-reports" / "TEST-com.example.AliveTest.xml").write_text(
        '<testsuite name="com.example.AliveTest" tests="2">'
        '<testcase name="a" classname="com.example.AliveTest" time="0"/>'
        '<testcase name="b" classname="com.example.AliveTest" time="0"/>'
        '</testsuite>')
    (run / "surefire-reports" / "TEST-com.example.DeadTest.xml").write_text(
        '<testsuite name="com.example.DeadTest" tests="1" errors="1">'
        '<testcase name="" classname="com.example.DeadTest" time="0">'
        '<error message="failed to load the required native library"'
        ' type="java.lang.UnsatisfiedLinkError"/></testcase></testsuite>')

    order = tmp_path / "order.txt"
    order.write_text("com.example.AliveTest#a\ncom.example.AliveTest#b\n"
                     "com.example.DeadTest#x\ncom.example.DeadTest#y\n")

    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_order_imposed.py"),
         str(order), str(run)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 0, r.stdout


def test_a_status_reader_answers_with_the_verdict_and_nothing_else():
    # write_status appends the tool sha as line 2, and every caller compares
    # the result against PASS. A reader that hands back both lines makes a run
    # that passed look unfinished -- and a resumable campaign then redoes work
    # it already has, which is the one thing it exists to avoid.
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "status"), "w") as fh:
            fh.write("PASS\ndeadbeef\n")
        for lib, fn in ((REPO / "container" / "runtime.sh", "read_status"),
                        (REPO / "lib.sh", "run_status")):
            r = subprocess.run(
                ["bash", "-c", 'source "%s" > /dev/null 2>&1; %s "%s"' % (lib, fn, d)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            assert r.stdout.strip() == "PASS", \
                "%s() returned %r, which never equals PASS" % (fn, r.stdout)


# --- the run configuration itself -------------------------------------------

def test_the_heap_backstop_offers_the_whole_container_not_a_quarter_of_it():
    # -XX:MaxRAM only tells the JVM how much machine to assume; it still takes a
    # fraction of that, 25% by default. So MaxRAM=16g on its own hands a fork a
    # 4g heap -- a quarter of the container, and a quarter of what
    # -DargLine=-Xmx16g gives every fork that receives the argLine.
    entrypoint = (REPO / "container" / "entrypoint.sh").read_text()
    assert "-XX:MaxRAM=" in entrypoint, "no heap backstop at all"
    assert "MaxRAMPercentage=100" in entrypoint or "MaxRAMFraction=1" in entrypoint, \
        "MaxRAM alone caps the heap at 25% of the container"


def test_the_heap_share_flag_matches_the_jdk_that_will_read_it():
    # The flag was renamed in JDK 10, and the wrong one is FATAL, not ignored:
    # java 8 answers -XX:MaxRAMPercentage with "Could not create the Java
    # Virtual Machine" and the run dies before maven starts. Half the campaign's
    # modules build on java 8, so shipping only the modern name breaks them all.
    entrypoint = (REPO / "container" / "entrypoint.sh").read_text()
    assert "MaxRAMFraction=1" in entrypoint, \
        "no java 8 form of the heap share flag; java 8 JVMs will refuse to start"
    assert "MaxRAMPercentage=100" in entrypoint, "no JDK 10+ form of the flag"
    assert re.search(r'java\s+-version', entrypoint), \
        "the flag is not chosen from the JDK actually in the image"


def test_every_image_the_campaign_uses_gets_the_whole_container_heap(tmp_path):
    """Start a real JVM in each image and read MaxHeapSize back.

    The one check that does not take the shell's word for it. Set
    OTOG_PROBE_HEAP=1; needs the images built.
    """
    import os, pytest
    if not os.environ.get("OTOG_PROBE_HEAP"):
        pytest.skip("starts a JVM in every image; set OTOG_PROBE_HEAP=1")

    want = int(config('echo "${otog_memory%g}"'))
    for image in ("image_java8", "image_java11", "image_java17", "image_java21"):
        snippet = """
source "%s/lib.sh"
engine_image_exists "$%s" || exit 3
engine_run --image "$%s" --workdir / -- bash -c '
    java_major=$(java -version 2>&1 | sed -n "/version \\"/{s/.*version \\"//;s/^1\\.//;s/[^0-9].*//;p;q;}")
    if [ "${java_major:-8}" -ge 10 ] 2>/dev/null; then s=-XX:MaxRAMPercentage=100; else s=-XX:MaxRAMFraction=1; fi
    JAVA_TOOL_OPTIONS="-XX:MaxRAM=%dg $s" java -XX:+PrintFlagsFinal -version 2>&1 |
        awk "/ MaxHeapSize/ {print \\$4}"'
""" % (REPO, image, image, want)
        r = subprocess.run(["bash", "-c", snippet], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, universal_newlines=True)
        if r.returncode == 3:
            pytest.skip("%s is not built" % image)
        assert "Could not create the Java Virtual Machine" not in r.stdout, \
            "%s: the JVM refuses the flags we pass it:\n%s" % (image, r.stdout)
        got = [int(t) for t in re.findall(r'^\s*(\d{6,})\s*$', r.stdout, re.M)]
        assert got, "%s: no MaxHeapSize in:\n%s" % (image, r.stdout)
        assert abs(got[0] / 1024**3 - want) < 0.5, \
            "%s: heap is %.2f GB, wanted %d GB" % (image, got[0] / 1024**3, want)


def test_the_test_jvm_is_offered_the_whole_container_memory():
    # 16g of container, 16g of heap for the tests, by the same route as always.
    assert "-DargLine=-Xmx$otog_jvm_heap" in (REPO / "config_default.sh").read_text()
    assert config('echo "${otog_jvm_heap}"') == config('echo "${otog_memory%g}g"')


def test_a_plain_run_passes_the_jvm_exactly_what_the_collected_runs_got():
    # A run only means something beside the other runs of the SAME ORDER, and
    # tens of thousands of those were collected with no JAVA_TOOL_OPTIONS at
    # all. Switching the backstop on by default would give the profiled
    # repetitions of an order a different heap regime from the plain ones they
    # are compared against -- which is the one comparison JFR runs exist for.
    assert config('echo "[$otog_jvm_max_ram]"') == "[]", \
        "the heap backstop is on by default; plain runs no longer match the corpus"
    entrypoint = (REPO / "container" / "entrypoint.sh").read_text()
    assert re.search(r'if \[ -n "\$otog_jvm_max_ram" \]', entrypoint), \
        "JAVA_TOOL_OPTIONS is exported unconditionally"


def test_a_profiled_run_can_still_be_attributed_to_test_classes():
    # JFR events are only useful if you can say which test class caused them.
    # Two mechanisms do that: the jfrsort agent, which needs JDK 17+, and
    # timestamped maven lines, which work everywhere. NINE of the sixteen
    # modules build on java 8, so dropping the timestamps would leave most of
    # the campaign's recordings unattributable.
    jfr = (REPO / "container" / "jfr.sh").read_text()
    assert "TZ=UTC" in jfr, "recordings and the maven log would be on different clocks"
    assert "simpleLogger.showDateTime" in jfr, "maven lines carry no timestamp"
    assert "jfrsort-agent.jar" in jfr, "the JDK 17+ agent is gone too"


def test_nothing_touches_the_surefire_fork_flags():
    # How many JVMs surefire forks, and whether it reuses them, is the project's
    # own decision. Overriding it would change what is being measured from "this
    # order in this project" to "this order in a project we reconfigured".
    shell = sorted(REPO.glob("*.sh")) + sorted((REPO / "container").glob("*.sh"))
    for f in shell:
        text = f.read_text()
        for flag in ("reuseForks", "forkCount", "forkMode", "forkedProcessTimeout"):
            assert flag not in text, "%s sets surefire's %s" % (f.name, flag)


def test_a_slurm_job_is_one_node_and_one_container():
    # Isolation is the measurement: two runs sharing a node share its memory
    # bandwidth and its page cache, and neither timing means anything after
    # that. One allocation, one container, one checkout of its own.
    runner = REPO / "slurm_run_experiment.sh"
    if not runner.is_file():
        import pytest; pytest.skip("no slurm runner in this tree")
    text = runner.read_text()
    assert "#SBATCH --nodes=1" in text
    assert "#SBATCH --ntasks=1" in text
    assert "OTOG_WORKSPACE_ROOT" in text, "jobs would share a checkout"
    assert "SLURM_JOB_ID" in text, "the workspace is not unique per job"


def test_the_slurm_runner_finds_the_tool_after_slurm_moves_it(tmp_path):
    # slurm copies the batch script into a spool directory before running it, so
    # a job that locates the tool from BASH_SOURCE looks for lib.sh next to the
    # copy and dies four seconds in, before it has written anything at all.
    runner = REPO / "slurm_run_experiment.sh"
    if not runner.is_file():
        import pytest; pytest.skip("no slurm runner in this tree")

    assert "OTOG_TOOL_DIR" in runner.read_text(), "the tool location cannot travel with the job"

    spooled = tmp_path / "slurm_script"
    spooled.write_text(runner.read_text())
    r = subprocess.run(
        ["bash", str(spooled), "job", "0", "0", "0", "1", "false"],
        env=dict(os.environ, OTOG_TOOL_DIR=str(REPO)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert "lib.sh: No such file" not in r.stdout, r.stdout
    assert "command not found" not in r.stdout, r.stdout


# --- the assumption the whole experiment rests on ----------------------------

PROBE_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>probe</groupId><artifactId>probe</artifactId><version>1.0</version>
  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version><scope>test</scope></dependency>
    <dependency><groupId>org.junit.vintage</groupId><artifactId>junit-vintage-engine</artifactId>
      <version>5.12.2</version><scope>test</scope></dependency>
  </dependencies>
</project>
"""

PROBE_CLASS = """package probe;
import %s;
public class %sTest {
    @Test public void alpha()   { System.out.println("RAN %sTest#alpha"); }
    @Test public void bravo()   { System.out.println("RAN %sTest#bravo"); }
    @Test public void charlie() { System.out.println("RAN %sTest#charlie"); }
}
"""


def test_the_fork_imposes_method_order_on_jupiter_but_not_on_vintage(tmp_path):
    """The order file is Class#method, and this is what actually happens to it.

    Run it whenever the fork, its cherry-picked PRs, or a module's JUnit
    version changes -- it is the only check that reads the real answer out of a
    real surefire rather than out of the code that was supposed to produce it.

    PR #15 imposes method order by registering a Jupiter MethodOrderer. The
    vintage engine has no such hook, so a JUnit 4 class keeps its own order.
    That is not a defect in the setup: it is the reach of the mechanism, and a
    mixed-engine module's method-order differences follow from it. If this ever
    starts passing for vintage too, the caveat in check_order_imposed.py and
    the ones recorded against those modules are out of date.
    """
    import os, pytest
    if not os.environ.get("OTOG_PROBE_ORDER"):
        pytest.skip("builds and runs a maven project; set OTOG_PROBE_ORDER=1")

    src = tmp_path / "src" / "test" / "java" / "probe"
    src.mkdir(parents=True)
    (tmp_path / "pom.xml").write_text(PROBE_POM)
    for name, imp in (("Jupiter", "org.junit.jupiter.api.Test"), ("Vintage", "org.junit.Test")):
        (src / ("%sTest.java" % name)).write_text(PROBE_CLASS % ((imp,) + (name,) * 4))

    # Reverse alphabetical, so no accidental default can look like success.
    (tmp_path / "order.txt").write_text("".join(
        "probe.%sTest#%s\n" % (c, m)
        for c in ("Jupiter", "Vintage") for m in ("charlie", "bravo", "alpha")))

    snippet = """
source "%s/lib.sh"
mkdir -p "%s/home"
engine_run --image "$image_java17" --workdir /work \
    --home "%s/home:$container_home_dir" \
    --bind "%s:/work" --bind "$otog_dependency_dir:$container_m2_dir" \
    --bind "$tool_dir:/otog:ro" \
    -- mvn -B -Dmaven.ext.class.path="$surefire_extension_jar" \
           test -Dtest=/work/order.txt -Dsurefire.runOrder=testorder \
           -Dmaven.repo.local="$container_m2_dir" $MVN_OPTS
""" % (REPO, tmp_path, tmp_path, tmp_path)
    r = subprocess.run(["bash", "-c", snippet],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    ran = re.findall(r'RAN (\w+)Test#(\w+)', r.stdout)
    if not ran:
        pytest.skip("probe did not run; needs an engine and a seeded repo:\n" + r.stdout[-2000:])

    jupiter = [m for c, m in ran if c == "Jupiter"]
    vintage = [m for c, m in ran if c == "Vintage"]
    assert jupiter == ["charlie", "bravo", "alpha"], \
        "PR #15 is not imposing Jupiter method order: %s" % jupiter
    assert vintage == ["alpha", "bravo", "charlie"], \
        "vintage method order changed -- the documented caveat may be stale: %s" % vintage


def test_a_run_leaves_behind_everything_a_later_question_needs():
    # The nine things every run directory has carried since the first campaign.
    # Losing one is invisible until someone asks the question it answers, by
    # which point the runs are collected and the answer is gone. order_source
    # went missing exactly that way: order.txt says WHAT ran, and only
    # order_source.txt says which file it came from.
    written = ((REPO / "run_once.sh").read_text()
               + (REPO / "container" / "entrypoint.sh").read_text()
               + (REPO / "container" / "runtime.sh").read_text())
    for artefact in ("compile.log", "git.log", "mvn.log", "node.txt",
                     "order_source.txt", "order.txt", "status",
                     "surefire-reports", "wall_time.txt"):
        assert artefact in written, "no run writes %s any more" % artefact


def test_a_profiled_run_keeps_one_recording_named_for_its_module():
    # The old runner left every JVM's raw hotspot-pid-*.jfr in place -- two per
    # run, maven's own among them, none of them saying which module they came
    # from. One recording, named for the module, is the point of the new one.
    jfr = (REPO / "container" / "jfr.sh").read_text()
    assert "jfr_drop_maven_recording" in jfr, "maven's own recording is kept"
    assert "jfr_name_recordings" in jfr, "recordings keep their hotspot-pid names"
    assert 'mv -f "${files[0]}" "$jfr_dir/$name.jfr"' in jfr, \
        "a single recording is not renamed to <module>.jfr"


def test_the_feeder_can_be_stopped_without_hunting_for_its_pid(tmp_path):
    # A watchdog is exactly the thing you need to stop when you have lost track
    # of which process is which. During the v2 transition three of them had to
    # be killed by hand, and one had already overwritten the throttle meant to
    # hold it -- so a stop that needs a trustworthy pid is not a stop.
    import os, pytest
    runner = REPO / "slurm_run_experiment.sh"
    watchdog = REPO / "slurm_experiment_watchdog.sh"
    if not runner.is_file():
        pytest.skip("no slurm runner in this tree")

    for f in (runner, watchdog):
        assert '"$tool_dir/STOP"' in f.read_text(), "%s cannot be stopped by a file" % f.name

    stop = REPO / "STOP"
    created = not stop.exists()
    try:
        stop.touch()
        r = subprocess.run(["bash", str(runner)], cwd=str(REPO),
                           env=dict(os.environ, MAX_JOBS="1", PHASES="v0",
                                    MODULES="1683", ORDERS="1 2"),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, timeout=120)
        assert "submitted 0 jobs" in r.stdout, r.stdout
    finally:
        if created:
            stop.unlink(missing_ok=True)


def test_a_submitted_job_runs_in_the_tool_that_submitted_it(tmp_path):
    # Without --chdir, slurm records the SUBMITTING shell's cwd as the job's
    # WorkDir. The job still works -- every path is absolute -- but `scontrol`
    # then shows it as belonging to whatever directory the operator happened to
    # be standing in, and when two campaigns are alive at once that is exactly
    # how you tell them apart.
    import os, pytest
    runner = REPO / "slurm_run_experiment.sh"
    if not runner.is_file():
        pytest.skip("no slurm runner in this tree")
    assert '--chdir="$tool_dir"' in runner.read_text(), "submitted jobs inherit the caller's cwd"

    # And prove it reaches sbatch, rather than merely appearing in the source.
    shim = tmp_path / "bin"; shim.mkdir()
    log = tmp_path / "sbatch.log"
    (shim / "sbatch").write_text(
        '#!/bin/bash\nprintf "%%s\\n" "$*" >> "%s"\necho 999999\n' % log)
    (shim / "squeue").write_text("#!/bin/bash\nexit 0\n")
    for f in ("sbatch", "squeue"):
        (shim / f).chmod(0o755)

    subprocess.run(["bash", str(runner)], cwd=str(REPO),
                   env=dict(os.environ, PATH="%s:%s" % (shim, os.environ["PATH"]),
                            MAX_JOBS="100000", PHASES="v0", MODULES="1683",
                            ORDERS="1 1", JFR="true"),
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    if not log.exists():
        pytest.skip("nothing was submitted (all reps already passed)")
    assert "--chdir=%s" % REPO in log.read_text().splitlines()[0]


def _write_engine_split_run(tmp_path, vintage_jar_in_classpath):
    # A module that mixes junit-vintage-engine and Jupiter runs each engine's
    # classes as one contiguous block (PR #15's own caveat), so both CLASS and
    # METHOD order for the vintage block differ from the order file no matter
    # what the fork does. check_order_imposed.py must not fail a run for that
    # -- only for a genuine, non-engine-shaped mismatch.
    run = tmp_path / "run_1"
    (run / "surefire-reports").mkdir(parents=True)
    (run / "mvn.log").write_text(
        "[INFO] Running com.example.JupiterTest\n"
        "[INFO] Running com.example.VintageTest\n")
    classpath = (
        "/m2/org/junit/vintage/junit-vintage-engine/5.12.2/junit-vintage-engine-5.12.2.jar"
        if vintage_jar_in_classpath else "/m2/org/junit/jupiter/junit-jupiter/5.12.2/x.jar")
    for cls, methods in (("JupiterTest", ("a", "b")), ("VintageTest", ("x", "y"))):
        cases = "".join(
            '<testcase name="%s" classname="com.example.%s" time="0"/>' % (m, cls)
            for m in methods)
        (run / "surefire-reports" / ("TEST-com.example.%s.xml" % cls)).write_text(
            '<testsuite name="com.example.%s" tests="2">'
            '<properties><property name="java.class.path" value="%s"/></properties>'
            '%s</testsuite>' % (cls, classpath, cases))

    # Order file asks for VintageTest first, reversed methods -- the opposite
    # of what mvn.log and the surefire XMLs above record.
    order = tmp_path / "order.txt"
    order.write_text("com.example.VintageTest#y\ncom.example.VintageTest#x\n"
                     "com.example.JupiterTest#a\ncom.example.JupiterTest#b\n")
    return order, run


def test_an_engine_split_does_not_fail_a_vintage_mixed_module(tmp_path):
    order, run = _write_engine_split_run(tmp_path, vintage_jar_in_classpath=True)
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_order_imposed.py"),
         str(order), str(run)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 0, r.stdout
    assert "not gated" in r.stdout


def test_the_same_split_still_fails_a_pure_jupiter_module(tmp_path):
    # Same class- and method-order mismatch, but with no vintage engine on the
    # classpath -- nothing excuses it, so it must still fail.
    order, run = _write_engine_split_run(tmp_path, vintage_jar_in_classpath=False)
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_order_imposed.py"),
         str(order), str(run)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert r.returncode == 1, r.stdout
