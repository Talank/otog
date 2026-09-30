#!/bin/bash
# usage: bash approaches/warmsort/sweep_warmsort.sh <module> <out_dir> [tool_dir]
#
# The five warmsort orders for one module, one per input set, installed into the
# order tree. Input is summary_merged_runs; OTOG_SUMMARY overrides where it is.
#
# out: <out_dir>/warmsort_<name>_<module>_v0.txt
#      orders/<module>/<version>/warmsort_<name>.txt

set -o pipefail

module=$1
out_dir=$2
tool_dir=${3:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
A="$tool_dir/approaches"
python=${OTOG_PYTHON:-python3}
summary=${OTOG_SUMMARY:-$tool_dir/../summary_merged_runs}

[ -z "$out_dir" ] && { echo "usage: sweep_warmsort.sh <module> <out_dir> [tool_dir]"; exit 1; }
mkdir -p "$out_dir"

for name in v0_99 past_24 past_49 past_74 past_99; do
    echo "== $module $name =="
    raw="$out_dir/raw_warmsort_${name}_${module}.txt"
    final="$out_dir/warmsort_${name}_${module}_v0.txt"

    "$python" "$A/warmsort/warmsort.py" "$summary" "$module" "$name" "$raw" \
        "$tool_dir/orders/$module/0/1.txt" || continue
    [ -s "$raw" ] || { echo "  no order produced"; continue; }

    "$python" "$A/common/adapt_to_target.py" "$raw" "$module" 0 "$final" "$tool_dir" || continue
    rm -f "$tool_dir"/orders/"$module"/*/warmsort_"${name}".txt
    "$python" "$A/common/install_order.py" "$module" "$final" "warmsort_${name}" "$tool_dir" 2>&1 | tail -1
done
