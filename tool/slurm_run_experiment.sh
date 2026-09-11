#!/bin/bash
#SBATCH --job-name=otog_run
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem=24G
#SBATCH --requeue
#SBATCH --constraint=amd
#SBATCH --exclude=amd045
#SBATCH --time=6:00:00
#
# bash slurm_run_experiment.sh                       # submit the work list
# bash slurm_run_experiment.sh job 1685 0 5 1 false  # one run, inside slurm
#
# run_experiment.sh for a cluster: same work list, same priority, same
# container -- one slurm job per repetition instead of local parallelism.
# Resumable, so a repetition that already passed is never submitted.
#
# in : MODULES PHASES ORDERS REPEATS JFR, as run_experiment.sh reads them --
#      JFR only reaches the v0 and historical phases, never x10/x5 -- plus
#      MAX_JOBS (how many of ours may sit in the queue at once).
#      `touch STOP` in this directory stops it submitting.
# out: runs/<module>/<version>/order_<order>/[jfr_]run_<n>/status
#
# 6 CPU and 24G for a container of 4 CPU and 16g: the extra is for the shell
# and apptainer around it, and cpu_slice() pins the container to exactly
# $otog_cpus. Apptainer cannot cgroup-limit without root, so the allocation IS
# the container -- check_container_size() refuses a wrong one rather than
# quietly producing timings nothing can be compared with.
#
# --constraint=amd, always. `normal` mixes 64 amd nodes with 28 intel ones and
# the same order measures 20.3s on amd against 25.2s on hop: a 24% gap, twice
# the ~12% spread between the fastest and slowest ORDER, which is the thing
# being measured. Letting slurm choose would make hardware the loudest variable.

MAX_JOBS=${MAX_JOBS:-250}

set -o pipefail

# slurm copies the batch script into a spool directory before running it, so
# inside a job BASH_SOURCE names the copy and not this tree. The submitting
# side is the only one that knows where the tool is, and passes it through.
source "${OTOG_TOOL_DIR:-$(dirname "${BASH_SOURCE[0]}")}/lib.sh"
export OTOG_TOOL_DIR=$tool_dir


# METHODS

out_dir_for() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5 prefix=run
    [ "$jfr" = true ] && prefix=jfr_run
    echo "$otog_runs_dir/$module/$version/order_$order/${prefix}_$n"
}

jfr_eligible() {
    # Same rule as run_experiment.sh's: JFR only profiles v0 and historical.
    [ "$1" = v0 ] || [ "$1" = historical ]
}

repetitions() {
    # The work list is one order per line, phase included; a job is one
    # repetition of one. With JFR on and this phase eligible, each repetition
    # is also run profiled, in its own directory.
    local module version order phase n jfr_here
    while read -r module version order phase; do
        jfr_here=false
        [ "${JFR:-false}" = true ] && jfr_eligible "$phase" && jfr_here=true
        for n in $(seq 1 "${REPEATS:-3}"); do
            echo "$module $version $order $n false"
            [ "$jfr_here" = true ] && echo "$module $version $order $n true"
        done
    done
}

job_name() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    echo "otog_${module}_v${version}_o${order}_r${n}_j${jfr}"
}

queued_names() {
    squeue -u "$USER" -h -o '%j' 2>/dev/null | grep '^otog_'
}

in_flight() {
    queued_names | grep -c .
}

submit() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    # A run is a build and one test suite: hours, not days. The partition's
    # 5-day default would let a hung JVM hold a node for a working week, and a
    # node held is a node the rest of the campaign cannot have.
    #
    # 4h plain, 6h profiled, against 42598 collected runs: the longest run that
    # has ever PASSED took 2h30m and p99.9 of them took 70m, while every run
    # over 3h failed. So the wall is far above the slowest run that could still
    # succeed -- a job that hits it has hung, not merely been slow, and killing
    # it costs nothing that was going to be collected. The profiled runs get
    # the wider limit because JFR adds to every one of them.
    local time_limit=4:00:00
    [ "$jfr" = true ] && time_limit=6:00:00
    # --chdir, or slurm records the SUBMITTING shell's cwd as the job's WorkDir.
    # A job that reads as belonging to some other tree is a job nobody can trust
    # at a glance -- and when two campaigns are alive at once, that glance is
    # how you tell them apart. Every path here is absolute regardless.
    sbatch --parsable \
        --job-name="$(job_name "$module" "$version" "$order" "$n" "$jfr")" \
        --time="$time_limit" \
        --chdir="$tool_dir" \
        --output="$tool_dir/slurm_logs/%x.%j.out" \
        --export="ALL,OTOG_TOOL_DIR=$tool_dir" \
        "$tool_dir/slurm_run_experiment.sh" job "$module" "$version" "$order" "$n" "$jfr"
}

feed() {
    # Submits in work-list order, waiting rather than queueing without limit: a
    # job sitting PENDING is not progress, and the cap is what keeps our share
    # of the scheduler fair.
    local module version order n jfr fed=0 name
    # What is already in the queue, once, at the start. run_passed() only sees
    # FINISHED work, so a feeder restarted by the watchdog while 250 jobs are
    # still running would submit every one of them a second time. This feeder
    # cannot duplicate its own submissions -- it walks the list start to end
    # and never revisits an order -- so the snapshot only has to cover what a
    # PREVIOUS feeder left behind, and that set cannot grow after this point.
    local -A queued=()
    while read -r name; do queued[$name]=1; done < <(queued_names)
    [ ${#queued[@]} -gt 0 ] && say "${#queued[@]} already in the queue -- not resubmitting those"

    while read -r module version order n jfr; do
        # Checked every order, not once at the start: a feeder can run for
        # hours, and stopping it has to not mean waiting for it to finish.
        [ -e "$tool_dir/STOP" ] && { say "STOP present -- stopping after $fed"; break; }
        run_passed "$(out_dir_for "$module" "$version" "$order" "$n" "$jfr")" && continue
        name=$(job_name "$module" "$version" "$order" "$n" "$jfr")
        [ -n "${queued[$name]:-}" ] && continue
        while [ "$(in_flight)" -ge "$MAX_JOBS" ]; do sleep 60; done
        submit "$module" "$version" "$order" "$n" "$jfr" > /dev/null && fed=$((fed + 1))
        [ $((fed % 100)) -eq 0 ] && say "submitted $fed"
    done
    say "submitted $fed jobs"
}

run_job() {
    # One repetition, in this allocation. Everything the measurement depends on
    # is decided by run_once.sh; this only resolves the version and gets out of
    # the way.
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    local out row slug path sha file

    out=$(out_dir_for "$module" "$version" "$order" "$n" "$jfr")
    run_passed "$out" && { say "already PASS: $out"; return 0; }

    row=$(version_row "$module" "$version") || return 1
    [ -z "$row" ] && { fail "no row for module $module version $version"; return 1; }
    IFS=, read -r slug path sha <<< "$row"

    file=$(order_file "$module" "$version" "$order")
    [ -s "$file" ] || { fail "no order at $file"; return 1; }

    # This job's own workspace, so no two runs ever share a checkout: a shared
    # one would let the second repetition read a target/ the first compiled.
    export OTOG_WORKSPACE_ROOT="$tool_dir/workspaces/job_${SLURM_JOB_ID:-$$}"

    say "module $module  version $version  order $order  rep $n  jfr $jfr  node $(hostname)"
    IMAGE=$(image_for_version "$module" "$version") \
        bash "$tool_dir/run_once.sh" "$slug" "$path" "$sha" "$out" "$file" "$jfr"
    local rc=$?

    rm -rf "$OTOG_WORKSPACE_ROOT"
    return $rc
}


# LOGIC

if [ "$1" = job ]; then
    shift
    module load git 2>/dev/null
    module load apptainer/1.4.1 2>/dev/null || module load apptainer 2>/dev/null \
        || module load singularity 2>/dev/null
    run_job "$@"
    exit $?
fi

mkdir -p "$tool_dir/slurm_logs"
say "cap: $MAX_JOBS in flight   repeats: ${REPEATS:-3}   jfr: ${JFR:-false}"
bash "$tool_dir/run_experiment.sh" --list | repetitions | feed
