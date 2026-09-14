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
# usage: bash slurm_run_experiment.sh [modules] [phases] [orders] [jfr] [max_jobs]
# e.g.   bash slurm_run_experiment.sh 1685 v0 "1 10" false 250
#
# run_experiment.sh for a cluster: same work list, same priority, same
# container -- one slurm job per repetition instead of local parallelism.
#
# in : the arguments above. `touch STOP` in this directory stops it submitting.
#      max_jobs is the cap while the queue is neither busy nor draining; over
#      100 pending it holds at $cap_busy, under 20 it rises to $cap_idle.
# out: runs/<module>/<version>/order_<order>/[jfr_]run_<n>/status
#
# Why 6 CPU for a 4 CPU container, why --constraint=amd, and why these wall
# clocks: docs/design.md, "Running on a cluster".

set -o pipefail

# slurm copies this script into a spool directory, so inside a job BASH_SOURCE
# names the copy. The submitting side passes the real tool through.
source "${OTOG_TOOL_DIR:-$(dirname "${BASH_SOURCE[0]}")}/lib.sh"
export OTOG_TOOL_DIR=$tool_dir

if [ "$1" = job ]; then
    mode=job; shift
else
    mode=feed
    modules=${1:-$otog_modules}
    phases=${2:-$otog_phases}
    orders=${3:-$otog_orders}
    jfr=${4:-$otog_jfr}
    max_jobs=${5:-250}
fi

# What the cap moves to when the queue is busy or draining. A job sitting
# PENDING is not progress, but an idle scheduler slot is waste.
cap_busy=250
cap_idle=350


# METHODS

out_dir_for() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5 prefix=run
    [ "$jfr" = true ] && prefix=jfr_run
    echo "$otog_runs_dir/$module/$version/order_$(order_label "$order")/${prefix}_$n"
}

job_name() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    echo "otog_${module}_v${version}_o$(order_label "$order")_r${n}_j${jfr}"
}

# JFR profiles v0 and historical only -- the same rule as run_experiment.sh.
jfr_eligible() {
    [ "$1" = v0 ] || [ "$1" = historical ]
}

# Work-list rows in, one "<module> <version> <order> <rep> <jfr>" per job out.
repetitions() {
    local module version order phase n jfr_here
    while read -r module version order phase; do
        jfr_here=false
        [ "$jfr" = true ] && jfr_eligible "$phase" && jfr_here=true
        for n in $(seq 1 "$otog_repeats"); do
            echo "$module $version $order $n false"
            [ "$jfr_here" = true ] && echo "$module $version $order $n true"
        done
    done
}

# Our job names currently in the queue.
queued_names() {
    squeue -u "$USER" -h -o '%j' 2>/dev/null | grep '^otog_'
}

in_flight() {
    queued_names | grep -c .
}

pending_jobs() {
    squeue -u "$USER" -h -t PENDING -o '%j' 2>/dev/null | grep -c '^otog_'
}

# The cap moves with the queue, with a dead band so it cannot oscillate.
job_cap() {
    local pending
    pending=$(pending_jobs)
    if [ "$pending" -gt 100 ]; then
        echo "$cap_busy"
    elif [ "$pending" -lt 20 ]; then
        echo "$cap_idle"
    else
        echo "$1"
    fi
}

submit() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    local time_limit=4:00:00
    [ "$jfr" = true ] && time_limit=6:00:00

    sbatch --parsable \
        --job-name="$(job_name "$module" "$version" "$order" "$n" "$jfr")" \
        --time="$time_limit" \
        --chdir="$tool_dir" \
        --output="$tool_dir/slurm_logs/%x.%j.out" \
        --export="ALL,OTOG_TOOL_DIR=$tool_dir" \
        "$tool_dir/slurm_run_experiment.sh" job "$module" "$version" "$order" "$n" "$jfr"
}

# Submits in work-list order, holding at max_jobs. See docs/design.md.
feed() {
    local module version order n jfr_here fed=0 name
    local queued_file="$tool_dir/slurm_logs/queued_at_start.txt"

    # Snapshot once: run_passed() only sees FINISHED work, so a feeder restarted
    # while hundreds of jobs are still running would submit them all again.
    queued_names > "$queued_file"
    [ -s "$queued_file" ] &&
        say "$(grep -c . "$queued_file") already in the queue -- not resubmitting those"

    while read -r module version order n jfr_here; do
        # Checked every order: stopping a feeder must not mean waiting for it.
        [ -e "$tool_dir/STOP" ] && { say "STOP present -- stopping after $fed"; break; }
        run_passed "$(out_dir_for "$module" "$version" "$order" "$n" "$jfr_here")" && continue
        name=$(job_name "$module" "$version" "$order" "$n" "$jfr_here")
        grep -qxF "$name" "$queued_file" && continue
        while [ "$(in_flight)" -ge "$(job_cap "$max_jobs")" ]; do sleep 60; done
        submit "$module" "$version" "$order" "$n" "$jfr_here" > /dev/null && fed=$((fed + 1))
        [ $((fed % 100)) -eq 0 ] && say "submitted $fed"
    done
    say "submitted $fed jobs"
}

# One repetition, in this allocation. run_once.sh decides everything else.
run_job() {
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    local out row slug path sha file rc

    out=$(out_dir_for "$module" "$version" "$order" "$n" "$jfr")
    run_passed "$out" && { say "already PASS: $out"; return 0; }

    row=$(version_row "$module" "$version") || return 1
    [ -z "$row" ] && { fail "no row for module $module version $version"; return 1; }
    IFS=, read -r slug path sha <<< "$row"

    file=$(order_file "$module" "$version" "$order")
    [ -s "$file" ] || { fail "no order at $file"; return 1; }

    # This job's own workspace, so no two runs ever share a checkout.
    export OTOG_WORKSPACE_ROOT="$tool_dir/workspaces/job_${SLURM_JOB_ID:-$$}"

    say "module $module  version $version  order $order  rep $n  jfr $jfr  node $(hostname)"
    IMAGE=$(image_for_version "$module" "$version") \
        bash "$tool_dir/run_once.sh" "$slug" "$path" "$sha" "$out" "$file" "$jfr"
    rc=$?

    rm -rf "$OTOG_WORKSPACE_ROOT"
    return $rc
}


# LOGIC

if [ "$mode" = job ]; then
    module load git 2>/dev/null
    module load apptainer/1.4.1 2>/dev/null || module load apptainer 2>/dev/null \
        || module load singularity 2>/dev/null
    run_job "$@"
    exit $?
fi

mkdir -p "$tool_dir/slurm_logs"
say "cap: $max_jobs in flight   repeats: $otog_repeats   jfr: $jfr"
bash "$tool_dir/run_experiment.sh" --list "$modules" "$phases" "$orders" | repetitions | feed
