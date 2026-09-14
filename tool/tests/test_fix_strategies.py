"""Two orders of one module-version are comparable only if they were built and
run identically. Fixes are what could break that, so they are keyed on the
VERSION and never on the order -- including for an order that is just a file
someone handed us."""

import os
import subprocess
from subprocess import PIPE
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def fix_call(tool, snippet):
    """Run a snippet with fix_helper.sh loaded the way the container loads it."""
    return tool.call('source "$tool_dir/fix_helper.sh"\n' + snippet)


def test_the_registry_key_has_no_order_in_it():
    # slug, slug::module, slug@sha, slug::module@sha -- four keys, and not one
    # of them can vary between two orders of the same module-version.
    text = (REPO / "fix_helper.sh").read_text()
    keys = 'for key in "$slug" "$slug::$module" "$slug@$sha" "$slug::$module@$sha"'
    assert keys in text, "the fix registry keys changed"
    assert "order" not in text.split("apply_fixes()")[1].split("\n}")[0]


def test_nothing_between_the_order_and_the_fixes_knows_the_order(tool):
    # entrypoint.sh is what calls apply_fixes, and it passes only the three
    # things that identify a version. If the order file ever reached it, two
    # orders of one version could be built differently.
    text = (REPO / "container" / "entrypoint.sh").read_text()
    for stage in ("compile", "runorder"):
        assert 'apply_fixes "$slug" "$module" "$sha" "%s" "$repo_dir"' % stage in text


def test_one_version_resolves_to_one_set_of_strategies(tool):
    # The real registry, looked up the way apply_fixes looks it up. netty's
    # epoll module at this sha is registered; the same module at another sha is
    # not, which is what "keyed on the version" means.
    out = fix_call(tool,
                   'strategies_for "netty/netty::transport-native-epoll'
                   '@699549dcbcc4b2de5aaa6e707e157925d20e3791"')
    assert out.stdout.strip() == "native_build_toolchain", out.stdout + out.stderr

    out = fix_call(tool, 'strategies_for "netty/netty::transport-native-epoll@deadbeef"')
    assert out.stdout.strip() == ""


def test_a_registry_row_naming_an_unknown_strategy_is_refused(tool):
    # A typo in the registry must not silently do nothing -- that would leave
    # the version unfixed and the failure would look like a broken commit.
    (tool.path / "data" / "fix_registry.csv").unlink()
    (tool.path / "data" / "fix_registry.csv").write_text(
        "key,strategies\nown/repo@sha000,no_such_strategy\n")
    out = fix_call(tool, 'apply_fixes own/repo mod sha000 compile /tmp > /dev/null')
    assert out.returncode != 0
    assert "unknown fix strategy" in (out.stdout + out.stderr).lower()


def test_the_fix_tables_need_no_bash_4(tool):
    # An associative array is bash 4, and macOS ships 3.2. The lookups are awk
    # over the CSVs precisely so this file runs anywhere the rest of it does.
    for name in ("fix_helper.sh", "slurm_run_experiment.sh", "lib.sh"):
        text = (REPO / name).read_text()
        assert "declare -A" not in text and "local -A" not in text, name


# --- an arbitrary order is an order like any other -------------------------

def run_dirs_for(tool, order, runs_dir):
    """The run directories run_experiment.sh would create for one order."""
    out = tool.sh("run_experiment.sh", "--one", 7, 0, order, "v0", "false",
                  env={"OTOG_RUNS_DIR": str(runs_dir)})
    return [l.split()[-1] for l in out.stdout.splitlines() if l.startswith("DRY")], out


def test_an_arbitrary_order_file_gets_its_own_named_directory(a_module, tmp_path):
    # "Run this order of mine at version V of module M" has to work, and land
    # somewhere a human can find. A path would otherwise be interpolated raw
    # into the run directory, one level per slash.
    a_module.order(7, 0, 1, ["A#a"])
    mine = tmp_path / "arbitrary_order.txt"
    mine.write_text("A#a\n")

    dirs, out = run_dirs_for(a_module, str(mine), a_module.path / "runs")
    assert dirs, out.stdout + out.stderr
    for d in dirs:
        assert "/order_arbitrary_order/" in d, d


def test_an_arbitrary_order_is_run_three_times_in_isolation(a_module, tmp_path):
    # Three repetitions, three directories, three containers -- the same unit
    # of measurement every numbered order gets.
    a_module.order(7, 0, 1, ["A#a"])
    mine = tmp_path / "arbitrary_order.txt"
    mine.write_text("A#a\n")

    dirs, out = run_dirs_for(a_module, str(mine), a_module.path / "runs")
    assert len(dirs) == 3, out.stdout
    assert len(set(dirs)) == 3, "repetitions shared a directory: %s" % dirs
    assert sorted(Path(d).name for d in dirs) == ["run_1", "run_2", "run_3"]


def test_an_arbitrary_order_reaches_the_container_as_itself(a_module, tmp_path):
    # The file is bound in and passed to -Dtest= unchanged, so what runs is
    # what was handed over -- not something re-derived from a number.
    a_module.order(7, 0, 1, ["A#a"])
    mine = tmp_path / "arbitrary_order.txt"
    mine.write_text("A#a\n")

    out = a_module.sh("run_experiment.sh", "--one", 7, 0, str(mine), "v0", "false",
                      env={"OTOG_RUNS_DIR": str(a_module.path / "runs")})
    assert "%s:/order.txt:ro" % mine in out.stdout, out.stdout


def test_a_cluster_job_name_survives_an_arbitrary_order():
    # slurm job names cannot contain a path. The label is what goes in, so the
    # feeder's resume check and squeue both still work.
    out = subprocess.run(
        ["bash", "-c",
         'source "%s/lib.sh"\n'
         'echo "otog_1685_v0_o$(order_label /tmp/some/arbitrary_order.txt)_r1_jfalse"' % REPO],
        stdout=PIPE, stderr=PIPE, universal_newlines=True, env=dict(os.environ))
    assert out.stdout.strip() == "otog_1685_v0_oarbitrary_order_r1_jfalse", out.stdout
