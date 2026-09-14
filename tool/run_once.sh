#!/bin/bash
#
# usage: bash run_once.sh <slug> <module> <sha> <out_dir> [order_file] [jfr]
# e.g.   bash run_once.sh javaparser/javaparser javaparser-core-testing 2c8ce569 runs/1685/0/order_5/run_1 orders/1685/0/5.txt
#
# Runs one test order once, in one container, from a cold JVM. This is the only
# place a measurement is taken; everything else decides what to call it with.
#
# in : the arguments above. With no order_file the container only prepares the
#      version and extracts its test list.
# out: <out_dir>/status = PASS | FAIL:<reason>, plus wall_time.txt, mvn.log,
#      surefire-reports/, order.txt, order_source.txt, node.txt

set -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

slug=$1
module=$2
sha=$3
out_dir=$4
order=${5:-}
jfr=${6:-$otog_jfr}

[ -z "$out_dir" ] && die "$(usage_of "$0")"

image=${IMAGE:-$(image_for_project "$slug")}
# Derived, not required as an argument: the hanging-test registry is keyed on
# the version, and a removal has to reach EVERY run of it -- including one
# started by hand with an order of your own.
version=${VERSION:-$(version_of "$slug" "$module" "$sha")}
workspace="$otog_workspace_root/${slug//\//_}_${module//\//_}_${sha:0:12}"


# METHODS

# Refuse before starting anything a container would only fail on.
check_inputs() {
    require_engine || return 1
    check_container_size || return 1

    if [ -n "$order" ] && [ ! -s "$order" ]; then
        fail "no order at $order"
        return 1
    fi

    # A dry run still validates its inputs; only the image check is skipped.
    [ -n "${OTOG_ENGINE_DRYRUN:-}" ] && return 0

    engine_image_exists "$image" || {
        fail "no $(engine_kind) image $image -- run: bash setup.sh $(engine_kind)"
        return 1
    }
}

# One container per checkout: two mavens in one working tree race in target/.
take_workspace() {
    mkdir -p "$workspace" "$otog_dependency_dir" || return 1
    exec 9> "$workspace.lock" || return 1
    lock_fd 9 || return 1
}

# Start the container that takes the measurement.
run_container() {
    mkdir -p "$out_dir" "$workspace/home" "$workspace/m2" || return 1

    # Docker reads a relative bind source as a named volume, so make it absolute.
    out_dir=$(cd "$out_dir" && pwd) || return 1

    rm -f "$out_dir/status"
    hostname > "$out_dir/node.txt" 2>/dev/null

    local binds=()
    if [ -n "$order" ]; then
        order=$(cd "$(dirname "$order")" && pwd)/$(basename "$order")
        # The order, and where it came from: neither can be reconstructed later.
        cp -f "$order" "$out_dir/order.txt"
        printf '%s\n' "$order" > "$out_dir/order_source.txt"
        binds=(--bind "$order:$container_order_file:ro"
               --env "ORDER_FILE=$container_order_file")
    fi
    [ "$jfr" = true ] && binds+=(--env "OTOG_JFR=true" --env "OTOG_JFR_SETTINGS=$otog_jfr_settings")

    engine_run \
        --image "$image" \
        --cpuset "$(cpu_slice)" --memory "$otog_memory" \
        --env "SLUG=$slug" --env "MODULE=$module" --env "SHA=$sha" \
        --env "VERSION=$version" \
        --env "OTOG_TOOL_SHA=$(tool_sha)" \
        --bind "$tool_dir:/otog:ro" \
        --bind "$workspace:$container_work_dir" \
        --bind "$workspace/m2:$container_m2_dir" \
        --bind "$otog_dependency_dir:$container_m2_shared_dir:ro" \
        --bind "$out_dir:$container_out_dir" \
        --home "$workspace/home:$container_home_dir" \
        --workdir "$container_work_dir" \
        "${binds[@]}" \
        -- bash /otog/container/entrypoint.sh
}

# One line per run: PASS, the failure reason, or DRY for a dry run.
report() {
    [ -n "${OTOG_ENGINE_DRYRUN:-}" ] && { say "DRY   $out_dir"; return 0; }

    local status
    status=$(run_status "$out_dir")
    [ "$status" = PASS ] && { say "PASS  $out_dir"; return 0; }
    fail "$status  $out_dir  (see $out_dir/mvn.log)"
    return 1
}


# LOGIC

check_inputs    || exit 1
take_workspace  || die "could not take $workspace"
run_container   || exit 1
report          || exit 1
