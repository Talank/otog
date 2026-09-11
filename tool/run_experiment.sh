#!/bin/bash
#
# bash run_experiment.sh
#
# Runs the experiment: every order, of every version, of every module listed
# below, in priority order, several containers at a time. Edit the variables to
# run a subset, or set any of them in the environment for a one-off.
# Resumable: a repetition that already passed is skipped.
#
# in : the variables below. JFR=true adds a profiled run beside every plain
#      one, but only on the v0 and historical phases (jfr_eligible).
# out: runs/<module>/<version>/order_<order>/run_<n>/status
#      runs/<module>/<version>/order_<order>/jfr_run_<n>/jfr/<module>.jfr

MODULES="${MODULES:-1685 1683 1778 1305 2088 29 33 1122 20 1497 3323 1694 3320 1216 3613 1117}"
PHASES="${PHASES:-v0 historical x10 x5}"   # priority order, first to last
ORDERS="${ORDERS:-1 100}"                  # first and last order number
REPEATS=${REPEATS:-3}
PARALLEL=${PARALLEL:-auto}                 # auto = as many as CPUs and memory allow
JFR=${JFR:-false}

set -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"


# METHODS

versions_in() {
    case $1 in
        v0)         echo 0 ;;
        historical) seq -1 -1 -100 ;;
        x10)        seq 10 10 100 ;;
        x5)         seq 5 10 95 ;;
        *)          echo "$1" ;;      # a phase can also be a literal version
    esac
}

jfr_eligible() {
    # JFR only runs on v0 and historical -- the versions the campaign actually
    # analyzes test-order effects on. The future x10/x5 versions exist to
    # confirm an order still applies going forward, not to profile it again.
    [ "$1" = v0 ] || [ "$1" = historical ]
}

work_for() {
    # One "<module> <version> <order> <phase>" per line. At a historical
    # version only its own order runs: order n is the one assigned to
    # version -n. The phase rides along so a consumer can gate JFR on it.
    local module=$1 phase=$2 version order
    local first=${ORDERS%% *} last=${ORDERS##* }

    for version in $(versions_in "$phase"); do
        if [ "$phase" = historical ]; then
            echo "$module $version ${version#-} $phase"
        else
            for order in $(seq "$first" "$last"); do
                echo "$module $version $order $phase"
            done
        fi
    done
}

build_work_list() {
    local phase module
    for phase in $PHASES; do
        for module in $MODULES; do
            work_for "$module" "$phase"
        done
    done
}

run_repetition() {
    # One container, one cold JVM, one measurement. Profiled or not, it is the
    # same run in its own directory: JFR's ~8% cannot be averaged with a plain
    # timing, and the separate directory is also the separate resume state.
    local module=$1 version=$2 order=$3 n=$4 jfr=$5
    local slug=$6 path=$7 sha=$8 file=$9
    local prefix=run out

    [ "$jfr" = true ] && prefix=jfr_run
    out="$otog_runs_dir/$module/$version/order_$order/${prefix}_$n"

    run_passed "$out" && return 0
    IMAGE=$(image_for_version "$module" "$version") \
        bash "$tool_dir/run_once.sh" "$slug" "$path" "$sha" "$out" "$file" "$jfr"
}

run_one_order() {
    # Every repetition of one order. With JFR on and this phase eligible, each
    # repetition is run twice -- once plain, once profiled -- so the cost of
    # profiling is measured against a timing from the same order rather than
    # an earlier campaign.
    local module=$1 version=$2 order=$3 phase=$4
    local row slug path sha file n jfr_here=false

    row=$(version_row "$module" "$version") || return 0
    [ -z "$row" ] && { fail "no row for module $module version $version"; return 0; }
    IFS=, read -r slug path sha <<< "$row"

    file=$(order_file "$module" "$version" "$order")
    [ -s "$file" ] || return 0

    [ "$JFR" = true ] && jfr_eligible "$phase" && jfr_here=true

    for n in $(seq 1 "$REPEATS"); do
        run_repetition "$module" "$version" "$order" "$n" false "$slug" "$path" "$sha" "$file"
        [ "$jfr_here" = true ] &&
            run_repetition "$module" "$version" "$order" "$n" true "$slug" "$path" "$sha" "$file"
    done
    return 0
}


# LOGIC

# The work list alone, for a scheduler that submits it as jobs rather than
# running it here. Keeps the priority order defined in exactly one place.
if [ "$1" = --list ]; then
    build_work_list
    exit 0
fi

if [ "$1" = --one ]; then
    shift
    run_one_order "$@"
    exit 0
fi

[ "$PARALLEL" = auto ] && PARALLEL=$(parallel_slots)
# jfr is worth saying out loud: it doubles the containers a campaign runs.
say "modules: $(echo $MODULES | wc -w)   phases: $PHASES   parallel: $PARALLEL   repeats: $REPEATS   jfr: $JFR"

build_work_list > "$tool_dir/work_list.txt"
say "work list: $(wc -l < "$tool_dir/work_list.txt") orders -> work_list.txt"

xargs -P "$PARALLEL" -L1 bash "$0" --one < "$tool_dir/work_list.txt"
say "done"
