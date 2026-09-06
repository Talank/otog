#!/bin/bash
#
# bash run_experiment.sh
#
# Runs the experiment: every order, of every version, of every module listed
# below, in priority order, several containers at a time. Edit the variables to
# run a subset. Resumable: a repetition that already passed is skipped.
#
# in : the variables below
# out: runs/<module>/<version>/order_<order>/run_<n>/status

MODULES="1685 1683 1778 1305 2088 29 33 1122 20 1497 3323 1694 3320 1216 3613 1117"
PHASES="v0 historical x10 x5"   # priority order, first to last
ORDERS="1 100"                  # first and last order number
REPEATS=3
PARALLEL=auto                   # auto = as many as CPUs and memory allow
JFR=false

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

work_for() {
    # One "<module> <version> <order>" per line. At a historical version only
    # its own order runs: order n is the one assigned to version -n.
    local module=$1 phase=$2 version order
    local first=${ORDERS%% *} last=${ORDERS##* }

    for version in $(versions_in "$phase"); do
        if [ "$phase" = historical ]; then
            echo "$module $version ${version#-}"
        else
            for order in $(seq "$first" "$last"); do
                echo "$module $version $order"
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

run_one_order() {
    # Every repetition of one order, each its own container and cold JVM.
    local module=$1 version=$2 order=$3
    local row slug path sha file out n

    row=$(version_row "$module" "$version") || return 0
    [ -z "$row" ] && { fail "no row for module $module version $version"; return 0; }
    IFS=, read -r slug path sha <<< "$row"

    file=$(order_file "$module" "$version" "$order")
    [ -s "$file" ] || return 0

    for n in $(seq 1 "$REPEATS"); do
        out="$otog_runs_dir/$module/$version/order_$order/run_$n"
        run_passed "$out" && continue
        IMAGE=$(image_for_version "$module" "$version") \
            bash "$tool_dir/run_once.sh" "$slug" "$path" "$sha" "$out" "$file" "$JFR"
    done
}


# LOGIC

if [ "$1" = --one ]; then
    shift
    run_one_order "$@"
    exit 0
fi

[ "$PARALLEL" = auto ] && PARALLEL=$(parallel_slots)
say "modules: $(echo $MODULES | wc -w)   phases: $PHASES   parallel: $PARALLEL   repeats: $REPEATS"

build_work_list > "$tool_dir/work_list.txt"
say "work list: $(wc -l < "$tool_dir/work_list.txt") orders -> work_list.txt"

xargs -P "$PARALLEL" -L1 bash "$0" --one < "$tool_dir/work_list.txt"
say "done"
