#!/bin/bash
# usage: bash approaches/jfrsort/sweep_jfrsort.sh <module> <out_dir> [tool_dir]
#
# The five jfrsort orders for one module, one per input set, mirroring
# sweep_z3.sh. jfrsort ranks test classes by the heap they allocate, read from
# the JFR recordings the otog_v4 campaign collected.
#
#   v0_99   0        order_1..order_99   99 of the 100 random orders at v0
#   past_24 -1..-24  the one order each  24 historical versions
#   past_49 -1..-49
#   past_74 -1..-74
#   past_99 -1..-99
#
# export_jfr.py takes ONE version directory, so a historical set is handed a
# directory of symlinks to the per-version order dirs -- the order dirs are
# named after the version (order_12 at v-12) so they never collide, and the
# original script runs unmodified. The same trick trims v0 to 99 orders.
#
# Recordings come from otog_v4/tool/runs: v4 is the jfr campaign, and its
# recordings are the ones made with the jfrsort agent attached.
#
# Sorting needs the `jfr` tool from JDK 17 or later; the runs themselves use
# the container's own JDK, untouched.
#
# out: <out_dir>/jfrsort_<name>_<module>_v0.txt      the orders, to inspect
#      orders/<module>/<version>/jfrsort_<name>.txt  the orders, to run

set -o pipefail

module=$1
out_dir=$2
tool_dir=${3:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
A="$tool_dir/approaches"
python=${OTOG_PYTHON:-/scratch/tbaral/otog_venv/bin/python}
jfrsort_py=${OTOG_JFRSORT:-$(cd "$tool_dir/.." && pwd)/jfrsort/jfrsort.py}
jfr_bin=${OTOG_JFR_BIN:-/scratch/tbaral/jdk23/bin/jfr}
work=${OTOG_JFRSORT_WORK:-/scratch/tbaral/jfrsort_work}

[ -z "$out_dir" ] && { echo "usage: sweep_jfrsort.sh <module> <out_dir> [tool_dir]"; exit 1; }
[ -x "$jfr_bin" ] || { echo "no jfr tool at $jfr_bin (needs JDK 17+)"; exit 1; }
mkdir -p "$out_dir"

# The order dirs of one input set, as absolute paths.
set_dirs() {
    local m=$1 name=$2 n k
    if [ "$name" = v0_99 ]; then
        for k in $(seq 1 99); do echo "$tool_dir/runs/$m/0/order_$k"; done
        return
    fi
    n=${name#past_}
    for k in $(seq 1 "$n"); do echo "$tool_dir/runs/$m/-$k/order_$k"; done
}

# OTOG_JFRSORT_SETS narrows the run to some of the sets, so one that failed
# can be redone without touching the orders the others already installed.
for name in ${OTOG_JFRSORT_SETS:-v0_99 past_24 past_49 past_74 past_99}; do
    echo "== $module $name =="
    virt="$work/$module/$name/virt"
    export_dir="$work/$module/$name/export"
    raw="$out_dir/raw_jfrsort_${name}_${module}.txt"
    final="$out_dir/jfrsort_${name}_${module}_v0.txt"

    rm -rf "$work/$module/$name"
    mkdir -p "$virt"
    n=0
    while read -r d; do
        [ -d "$d" ] || continue
        ln -s "$d" "$virt/$(basename "$d")" && n=$((n + 1))
    done < <(set_dirs "$module" "$name")
    echo "  $n order dirs linked"
    [ "$n" -eq 0 ] && { echo "  no order dirs -- skipping"; continue; }

    "$python" "$tool_dir/scripts/export_jfr.py" "$virt" "$export_dir" 2>&1 | tail -1 || continue

    # A run whose recordings carry no jfrsort marker stops the sort at that
    # run, so the unreadable ones come out before sorting starts.
    "$python" "$A/jfrsort/drop_unprofiled_runs.py" "$export_dir" || continue

    log="$out_dir/sort_${name}_${module}.log"
    "$python" "$jfrsort_py" sort --out "$export_dir" --jfr-bin "$jfr_bin" > "$log" 2>&1
    grep -E 'classes,|order written|WARNING' "$log" | tail -3
    [ -s "$export_dir/order-alloc-sort.txt" ] || { echo "  no order: $(tail -1 "$log")"; continue; }

    "$python" "$A/jfrsort/expand_class_order.py" "$export_dir/order-alloc-sort.txt" \
        "$tool_dir/orders/$module/0/1.txt" "$raw" || continue

    "$python" "$A/common/adapt_to_target.py" "$raw" "$module" 0 "$final" "$tool_dir" || continue
    rm -f "$tool_dir"/orders/"$module"/*/jfrsort_"${name}".txt
    "$python" "$A/common/install_order.py" "$module" "$final" "jfrsort_${name}" "$tool_dir" 2>&1 | tail -1

    # the export is hardlinks to the recordings; drop it once the order exists
    rm -rf "$work/$module/$name"
done
