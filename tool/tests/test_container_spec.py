"""The container is the measurement. These are the invariants that make timings
comparable across machines; if one breaks, every comparison silently becomes
meaningless rather than failing loudly."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def config():
    return (REPO / "config_default.sh").read_text()


def test_the_container_is_four_cpus_and_sixteen_gigabytes():
    assert re.search(r'^otog_cpus=4$', config(), re.M)
    assert re.search(r'^otog_memory=16g$', config(), re.M)


def test_three_repetitions():
    assert re.search(r'^otog_repeats=3$', config(), re.M)


def test_jfr_is_off_by_default():
    # A profiled run costs ~8% and is not comparable with an unprofiled one, so
    # profiling must never be something you get without asking.
    assert re.search(r'otog_jfr="\$\{OTOG_JFR:-false\}"', config())


def test_parallel_sizing_respects_both_cpu_and_memory(tool):
    # 8 cores but only 16 GB is one container, not two: sizing on cores alone
    # would put two 16 GB containers on a 16 GB box and both would swap.
    out = tool.call(
        'otog_cpus=4; otog_memory=16g; otog_parallel=auto\n'
        'parallel_slots() {\n'
        '  by_cpu=$(( 8 / otog_cpus )); by_mem=$(( 16 / ${otog_memory%g} ))\n'
        '  [ "$by_mem" -lt "$by_cpu" ] && by_cpu=$by_mem\n'
        '  echo $by_cpu; }\n'
        'parallel_slots')
    assert out.stdout.strip() == "1"


def test_parallel_slots_is_at_least_one(tool):
    out = tool.call('parallel_slots')
    assert out.returncode == 0
    assert int(out.stdout.strip()) >= 1


def test_cpu_slice_pins_exactly_otog_cpus(tool):
    # An unpinned container takes the whole machine and is no longer the unit
    # being measured, so a slice is always returned -- never empty.
    out = tool.call('cpu_slice')
    assert out.returncode == 0
    cpus = out.stdout.strip()
    assert cpus, "cpu_slice returned nothing; the container would be unpinned"
    assert len(cpus.split(",")) == 4


def test_one_run_is_one_container_and_repeats_live_outside_it():
    # Repeating inside one container measures a warmed-up JVM, not the order.
    # run_once.sh therefore takes no repeat count; run_experiment.sh loops.
    once = (REPO / "run_once.sh").read_text()
    experiment = (REPO / "run_experiment.sh").read_text()
    assert "REPEATS" not in once
    assert "for n in $(seq 1 \"$REPEATS\")" in experiment
