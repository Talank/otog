#!/bin/bash
#
# bash setup.sh docker          # or: bash setup.sh apptainer
#
# One-time setup in this directory: checks the engine is usable, builds the
# container images, fetches the orders, and creates the directories a run
# needs. Safe to re-run -- anything already there is left alone.
#
# in : docker | apptainer, and otog_orders_url for the orders
# out: images/ populated, orders/ unpacked, runs/ workspaces/ dependency/ created

set -o pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

engine=$1
[ -z "$engine" ] && die "$(usage_of "$0")"
case "$engine" in docker|apptainer) ;; *) die "engine must be docker or apptainer" ;; esac

export OTOG_ENGINE=$engine
otog_engine=$engine

images="$image_java8 $image_java11 $image_java17 $image_java21"


# METHODS

check_engine() {
    engine_is_usable && return 0
    fail "$engine is not installed or not usable by this user."
    case "$engine" in
        docker)    fail "  install it, or start it: sudo systemctl start docker"
                   fail "  then, once:              sudo usermod -aG docker \$USER" ;;
        apptainer) fail "  install apptainer 1.1+ (no root needed to run)" ;;
    esac
    return 1
}

save_engine() {
    # config.sh wins over config_default.sh, so this is what every later script
    # uses. Edit that line to run on a different engine. OTOG_ENGINE still wins
    # over both, for a one-off run.
    local config="$tool_dir/config.sh"
    local line="otog_engine=\"\${OTOG_ENGINE:-$engine}\""

    if [ ! -f "$config" ]; then
        printf '# Local settings. config_default.sh has the rest and the comments.\n%s\n' \
               "$line" > "$config"
    elif grep -q '^otog_engine=' "$config"; then
        # Not sed -i: its in-place flag differs between BSD and GNU.
        awk -v line="$line" '/^otog_engine=/ {print line; next} {print}' \
            "$config" > "$config.tmp" && mv "$config.tmp" "$config"
    else
        printf '%s\n' "$line" >> "$config"
    fi
}

make_dirs() {
    mkdir -p "$otog_runs_dir" "$otog_workspace_root" "$otog_dependency_dir" \
             "$otog_image_dir" "$otog_image_sif_dir"
}

build_images() {
    local image
    for image in $images; do
        if engine_image_exists "$image"; then
            say "have   $image"
            continue
        fi
        say "build  $image"
        engine_pull "$image" || return 1
    done
}

fetch_orders() {
    local zip="$tool_dir/orders.zip"

    [ -n "$(ls -A "$otog_orders_dir" 2> /dev/null)" ] && { say "have   orders/"; return 0; }

    if [ -z "$otog_orders_url" ]; then
        fail "no orders URL -- set otog_orders_url in config.sh, or unpack orders.zip here yourself"
        return 1
    fi

    if [ ! -s "$zip" ]; then
        say "fetch  orders.zip"
        download_file "$otog_orders_url" "$zip" || return 1
    fi

    say "unzip  orders.zip -> orders/"
    unzip -q -o "$zip" -d "$tool_dir" || return 1
}

fetch_dependency() {
    local zip="$tool_dir/dependency.zip"

    [ -n "$(ls -A "$otog_dependency_dir" 2> /dev/null)" ] && { say "have   dependency/"; return 0; }

    if [ -z "$otog_dependency_url" ]; then
        fail "no dependency URL -- set otog_dependency_url in config.sh, or unpack dependency.zip here yourself"
        return 1
    fi

    if [ ! -s "$zip" ]; then
        say "fetch  dependency.zip"
        download_file "$otog_dependency_url" "$zip" || return 1
    fi

    say "unzip  dependency.zip -> dependency/"
    unzip -q -o "$zip" -d "$tool_dir" || return 1
}

report() {
    say ""
    say "engine   : $(engine_kind)  (saved in config.sh)"
    say "orders   : $(ls "$otog_orders_dir" 2> /dev/null | wc -l | tr -d ' ') modules"
    say "images   : $(for i in $images; do engine_image_exists "$i" && echo -n .; done | wc -c) of $(echo $images | wc -w)"
    say "parallel : $(parallel_slots) containers fit here ($otog_cpus CPU + $otog_memory each)"
    say ""
    say "next: bash run_experiment.sh"
}


# LOGIC

check_engine || exit 1
save_engine  || die "could not write config.sh"
make_dirs    || die "could not create directories"
build_images || die "could not build the images"
fetch_orders || die "could not fetch the orders"
fetch_dependency || die "could not fetch the dependency"
report
