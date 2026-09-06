"""The three scripts, end to end, against a dry-run engine. Nothing here starts
a container; everything else is real."""

import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = ["a.T#one", "a.T#two", "b.U#only"]


def test_every_script_states_its_usage_and_its_in_and_out():
    # The header is the documentation. If it drifts, the script is undocumented.
    for name in ("setup.sh", "run_once.sh", "run_experiment.sh"):
        head = "\n".join((REPO / name).read_text().split("\n")[:14])
        assert "bash " in head, f"{name} has no usage example"
        assert "in :" in head and "out:" in head, f"{name} has no in/out"


def test_run_once_without_arguments_prints_usage(tool):
    result = tool.sh("run_once.sh")
    assert result.returncode != 0
    assert "run_once.sh" in result.stdout + result.stderr


def test_setup_rejects_an_unknown_engine(tool):
    result = tool.sh("setup.sh", "podman")
    assert result.returncode != 0
    assert "docker or apptainer" in result.stdout + result.stderr


def test_setup_without_an_engine_prints_usage(tool):
    result = tool.sh("setup.sh")
    assert result.returncode != 0
    assert "setup.sh" in result.stdout + result.stderr


def test_run_once_dry_run_builds_a_correct_container_command(a_module):
    a_module.order(7, 0, 1, TESTS)
    out_dir = a_module.path / "runs" / "7" / "0" / "order_1" / "run_1"

    result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                         str(out_dir), str(a_module.path / "orders/7/0/1.txt"))

    assert result.returncode == 0, result.stdout + result.stderr
    printed = result.stdout
    assert "--cpuset" in printed or "cpuset" in printed
    assert "16g" in printed
    assert "entrypoint.sh" in printed


def test_a_dry_run_writes_no_status(a_module):
    # A dry run that left a PASS behind would poison the dataset.
    a_module.order(7, 0, 1, TESTS)
    out_dir = a_module.path / "runs" / "7" / "0" / "order_1" / "run_1"
    a_module.sh("run_once.sh", "own/repo", "mod", "sha000", str(out_dir),
                str(a_module.path / "orders/7/0/1.txt"))
    assert not (out_dir / "status").exists()


def test_run_once_refuses_an_order_file_that_is_not_there(a_module):
    result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                         str(a_module.path / "runs/x"), "/nope/missing.txt")
    assert result.returncode != 0
    assert "no order" in (result.stdout + result.stderr).lower()


def test_run_experiment_skips_a_version_missing_from_the_csv(a_module):
    # A typo'd module should not silently produce an empty run tree.
    import re
    text = (a_module.path / "run_experiment.sh").read_text()
    text = re.sub(r'^MODULES=.*$', 'MODULES="999"', text, count=1, flags=re.M)
    text = re.sub(r'^PHASES=.*$', 'PHASES="v0"', text, count=1, flags=re.M)
    (a_module.path / "s.sh").write_text(text)

    result = a_module.sh("s.sh")

    assert result.returncode == 0
    assert not list((a_module.path / "runs").glob("999/**/status"))


def test_a_repetition_that_already_passed_is_not_run_again(a_module):
    # Resumability: re-running must cost only what is left, and must never
    # overwrite a finished measurement with a fresh one.
    a_module.order(7, 0, 1, TESTS)
    done = a_module.run(7, 0, 1, 1, status="PASS")
    stamp = (done / "status").stat().st_mtime_ns

    import re
    text = (a_module.path / "run_experiment.sh").read_text()
    for key, value in (("MODULES", "7"), ("PHASES", "v0"), ("ORDERS", "1 1")):
        text = re.sub(rf'^{key}=.*$', f'{key}="{value}"', text, count=1, flags=re.M)
    (a_module.path / "s.sh").write_text(text)
    a_module.sh("s.sh")

    assert (done / "status").stat().st_mtime_ns == stamp


def test_the_engine_layer_reports_errors_instead_of_crashing(tool):
    # engine.sh calls print_fail_message; if the host side does not define it,
    # every error path dies with "command not found" instead of saying why.
    out = tool.call('engine_run --image x -- ; echo "rc=$?"')
    assert "command not found" not in out.stderr
    assert "rc=2" in out.stdout


def test_bind_mounts_must_be_absolute(tool):
    # Docker reads a relative -v source as a named volume, which would silently
    # mount an empty volume instead of the workspace.
    out = tool.call('engine_run --image x --bind "rel/path:/x" -- true; echo "rc=$?"')
    assert "rc=2" in out.stdout


def test_apptainer_builds_a_command_with_no_undefined_functions(a_module):
    # image_dir_for_tag lives in config_default.sh and only the apptainer path
    # calls it. When it went missing, docker kept working and apptainer -- the
    # engine every HPC and CloudLab node uses -- broke silently.
    a_module.order(7, 0, 1, TESTS)
    result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                         str(a_module.path / "runs/7/0/order_1/run_1"),
                         str(a_module.path / "orders/7/0/1.txt"),
                         env={"OTOG_ENGINE": "apptainer"})

    assert "command not found" not in result.stderr, result.stderr
    assert result.returncode == 0
    # taskset is util-linux: on macOS there is nothing to pin with, and no
    # apptainer to pin either.
    if shutil.which("taskset"):
        assert "taskset" in result.stdout


def test_both_engines_pin_exactly_four_cpus(a_module):
    a_module.order(7, 0, 1, TESTS)
    # docker: --cpuset-cpus <list>.  apptainer: taskset -c <list>.
    for engine, flag, offset in (("docker", "--cpuset-cpus", 1),
                                 ("apptainer", "taskset", 2)):
        result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                             str(a_module.path / f"runs/7/0/order_1/run_{engine}"),
                             str(a_module.path / "orders/7/0/1.txt"),
                             env={"OTOG_ENGINE": engine})
        lines = result.stdout.split("\n")
        if flag == "taskset" and not shutil.which("taskset"):
            continue
        assert flag in lines, f"{engine} did not pin CPUs"
        cpus = lines[lines.index(flag) + offset]
        assert len(cpus.split(",")) == 4, f"{engine} pinned {cpus}, want 4 CPUs"


def test_memory_is_capped_and_cannot_swap_past_it(a_module):
    # --memory without --memory-swap lets a container swap past its limit and
    # end up timing the disk instead of the tests.
    a_module.order(7, 0, 1, TESTS)
    result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                         str(a_module.path / "runs/7/0/order_1/run_m"),
                         str(a_module.path / "orders/7/0/1.txt"),
                         env={"OTOG_ENGINE": "docker"})
    lines = result.stdout.split("\n")
    assert "--memory" in lines and "--memory-swap" in lines
    assert lines[lines.index("--memory") + 1] == lines[lines.index("--memory-swap") + 1]


def test_jfr_is_absent_unless_asked_for(a_module):
    a_module.order(7, 0, 1, TESTS)
    args = ("own/repo", "mod", "sha000",
            str(a_module.path / "runs/7/0/order_1/run_j"),
            str(a_module.path / "orders/7/0/1.txt"))

    off = a_module.sh("run_once.sh", *args)
    on = a_module.sh("run_once.sh", *args, "true")

    assert "OTOG_JFR" not in off.stdout
    assert "OTOG_JFR=true" in on.stdout


def test_the_order_is_mounted_read_only(a_module):
    # The container must not be able to rewrite the order it was given.
    a_module.order(7, 0, 1, TESTS)
    result = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                         str(a_module.path / "runs/7/0/order_1/run_r"),
                         str(a_module.path / "orders/7/0/1.txt"))
    assert any(l.endswith("/order.txt:ro") for l in result.stdout.split("\n"))


def test_an_apptainer_image_is_one_file_and_both_sides_agree(tool):
    # A --sandbox directory loses individual ELF files on shared storage, and
    # every run after that dies with "executable file not found". setup.sh
    # writes a .sif; the run side has to look for that same path.
    env = {"OTOG_ENGINE": "apptainer"}
    tag = "maven:3.9-eclipse-temurin-17"

    written = tool.call(f"sif_for_tag {tag}", env=env).stdout.strip()
    assert written.endswith(".sif"), written

    Path(written).parent.mkdir(parents=True, exist_ok=True)
    Path(written).touch()
    read = tool.call(f"image_dir_for_tag {tag}", env=env).stdout.strip()
    assert read == written, "setup writes one path and the run reads another"

    code = [l for l in (REPO / "container" / "engine.sh").read_text().splitlines()
            if not l.lstrip().startswith("#")]
    assert not [l for l in code if "--sandbox" in l], "still builds a sandbox"


def test_a_version_that_needs_a_different_jdk_gets_one(a_module):
    # image_for_version returns nothing for most pairs, so run_once.sh has to
    # treat an EMPTY override as "no override". ${IMAGE-...} would not.
    override = a_module.sh("run_once.sh", "mapstruct/mapstruct", "processor",
                           "sha000", a_module.path / "out",
                           a_module.order(7, 0, 1, TESTS),
                           env={"IMAGE": "maven:3.9-eclipse-temurin-21"})
    assert "temurin-21" in override.stdout

    default = a_module.sh("run_once.sh", "mapstruct/mapstruct", "processor",
                          "sha000", a_module.path / "out",
                          a_module.order(7, 0, 1, TESTS), env={"IMAGE": ""})
    assert "temurin-17" in default.stdout, "an empty override hid the real image"


def test_every_path_the_container_expects_is_actually_mounted(a_module):
    # run_once.sh bound the private maven repo at /root/.m2 while entrypoint.sh
    # resolved against $container_m2_dir. The two have to be the same string,
    # so both read it from config.
    out = a_module.sh("run_once.sh", "own/repo", "mod", "sha000",
                      a_module.path / "out", a_module.order(7, 0, 1, TESTS)).stdout

    config = (REPO / "config_default.sh").read_text()
    for name in ("container_work_dir", "container_out_dir", "container_m2_dir",
                 "container_m2_shared_dir", "container_order_file",
                 "container_home_dir"):
        path = re.search(r'^%s=(\S+)' % name, config, re.M).group(1)
        assert re.search(r':%s(:ro)?$' % re.escape(path), out, re.M), \
            f"{name}={path} is never mounted"
