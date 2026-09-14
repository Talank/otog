#!/bin/bash
#
# usage: bash run_experiment.sh [modules] [phases] [orders] [jfr]
# e.g.   bash run_experiment.sh 1685 v0 "1 10" false
#
# Runs the experiment: every order, of every version, of every module, in
# priority order, several containers at a time. Resumable, so a repetition
# that already passed is skipped.
#
# in : the four arguments above; repeats and parallelism come from config.
# out: runs/<module>/<version>/order_<order>/run_<n>/status
#      runs/<module>/<version>/order_<order>/jfr_run_<n>/jfr/<module>.jfr

set -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# --list prints the work list and stops; --one runs a single row of it.
# Both take the arguments after the flag, so strip it before reading them.
mode=run
case "$1" in
    --list | --one) mode=${1#--}; shift ;;
esac

if [ "$mode" = one ]; then
    one_module=$1
    one_version=$2
    one_order=$3
    one_phase=$4
    jfr=${5:-false}
else
    modules=${1:-$otog_modules}
    phases=${2:-$otog_phases}
    orders=${3:-$otog_orders}
    jfr=${4:-$otog_jfr}
fi


# METHODS

# A phase name expands to its versions; anything else is a literal version.
versions_in() {
    case $1 in
        v0)         echo 0 ;;
        historical) seq -1 -1 -100 ;;
        x10)        seq 10 10 100 ;;
        x5)         seq 5 10 95 ;;
        *)          echo "$1" ;;
    esac
}

# JFR profiles v0 and historical only. See docs/design.md.
jfr_eligible() {
    [ "$1" = v0 ] || [ "$1" = historical ]
}

# One "<module> <version> <order> <phase>" per line for one phase of one module.
work_for() {
    local module=$1 phase=$2 version order
    local first=${orders%% *} last=${orders##* }

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

# The whole work list, phase by phase, module by module -- the priority order.
build_work_list() {
    local phase module
    for phase in $phases; do
        for module in $modules; do
            work_for "$module" "$phase"
        done
    done
}

# One container, one cold JVM, one measurement.
run_repetition() {
    local out=$1 image=$2 jfr_here=$3
    local slug=$4 path=$5 sha=$6 file=$7

    run_passed "$out" && return 0
    IMAGE=$image bash "$tool_dir/run_once.sh" "$slug" "$path" "$sha" "$out" "$file" "$jfr_here"
}

# Every repetition of one order, plain and -- when eligible -- profiled too.
run_one_order() {
    local module=$1 version=$2 order=$3 phase=$4
    local row slug path sha file image label dir n jfr_here=false

    row=$(version_row "$module" "$version") || return 0
    [ -z "$row" ] && { fail "no row for module $module version $version"; return 0; }
    IFS=, read -r slug path sha <<< "$row"

    file=$(order_file "$module" "$version" "$order")
    [ -s "$file" ] || return 0

    label=$(order_label "$order")
    dir="$otog_runs_dir/$module/$version/order_$label"
    image=$(image_for_version "$module" "$version")
    [ "$jfr" = true ] && jfr_eligible "$phase" && jfr_here=true

    for n in $(seq 1 "$otog_repeats"); do
        run_repetition "$dir/run_$n" "$image" false "$slug" "$path" "$sha" "$file"
        [ "$jfr_here" = true ] &&
            run_repetition "$dir/jfr_run_$n" "$image" true "$slug" "$path" "$sha" "$file"
    done
    return 0
}


# LOGIC

# The work list alone, for a scheduler that submits it as jobs.
if [ "$mode" = list ]; then
    build_work_list
    exit 0
fi

if [ "$mode" = one ]; then
    run_one_order "$one_module" "$one_version" "$one_order" "$one_phase"
    exit 0
fi

parallel=$(parallel_slots)
say "modules: $(echo $modules | wc -w)   phases: $phases   parallel: $parallel   repeats: $otog_repeats   jfr: $jfr"

build_work_list > "$tool_dir/work_list.txt"
say "work list: $(wc -l < "$tool_dir/work_list.txt") orders -> work_list.txt"

# work_list.txt stays four columns -- it is what --list prints and what a
# cluster scheduler reads. The jfr flag is appended here, for this run only.
sed "s/\$/ $jfr/" "$tool_dir/work_list.txt" | xargs -P "$parallel" -L1 bash "$0" --one
say "done"
