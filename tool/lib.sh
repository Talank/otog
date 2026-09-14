#!/bin/bash
#
# usage: source lib.sh
# e.g.   source lib.sh; version_row 1685 0
#
# Sourced by every host-side script: loads config, then defines what they
# share. The container uses container/runtime.sh instead.

tool_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$tool_dir/config_default.sh"
[ -f "$tool_dir/config.sh" ] && source "$tool_dir/config.sh"
source "$tool_dir/container/engine.sh"


# ---------------------------------------------------------------- messages

say()  { printf '%s\n' "$*"; }
fail() { printf '%s\n' "$*" >&2; }
die()  { fail "$*"; exit 1; }

# Same vocabulary as the container, so engine.sh reads the same on both sides.
print_info_message() { say "$@"; }
print_fail_message() { fail "$@"; }

# A script's usage is its header comment, so there is one place to edit.
usage_of() {
    sed -n '3,/^$/p' "$1" | sed 's/^# \{0,1\}//'
}


# ------------------------------------------------------------------ lookups

# module version -> "slug,module_path,sha" from data/versions.csv.
version_row() {
    awk -F, -v m="$1" -v v="$2" 'NR>1 && $1==m && $4==v {print $2","$3","$5; exit}' "$versions_csv"
}

# slug module_path sha -> the version number. (slug, module, sha) is unique.
version_of() {
    awk -F, -v s="$1" -v p="$2" -v h="$3" \
        'NR>1 && $2==s && $3==p && $5==h {print $4; exit}' "$versions_csv" 2>/dev/null
}

# module version order -> the order file. A number is looked up, anything else is a path.
order_file() {
    case "$3" in
        ''|*[!0-9-]*) printf '%s' "$3" ;;
        *)            printf '%s/%s/%s/%s.txt' "$otog_orders_dir" "$1" "$2" "$3" ;;
    esac
}

# The same order as a directory name: a number stays a number, a path becomes its file name.
order_label() {
    case "$1" in
        ''|*[!0-9-]*) printf '%s' "$(basename "$1" .txt)" ;;
        *)            printf '%s' "$1" ;;
    esac
}


# -------------------------------------------------------------------- state

# Line 1 of a run's status file, or NONE. Line 2 is the tool sha.
run_status() {
    head -1 "$1/status" 2>/dev/null || echo NONE
}

run_passed() {
    [ "$(run_status "$1")" = PASS ]
}

# Which version of this tool produced a run. Empty outside a git checkout.
tool_sha() {
    local sha
    sha=$(git -C "$tool_dir" rev-parse --short=12 HEAD 2>/dev/null) || return 0
    git -C "$tool_dir" diff --quiet HEAD 2>/dev/null || sha="$sha-dirty"
    echo "$sha"
}


# ------------------------------------------------------------------- files

# gdown for a google drive link, curl for anything else. See docs/design.md.
download_file() {
    local url=$1
    local dest=$2

    case "$url" in
        *drive.google.com*|*docs.google.com*)
            command -v gdown > /dev/null 2>&1 || {
                fail "gdown is needed for a google drive link: pip3 install gdown"
                return 1
            }
            gdown --fuzzy -O "$dest" "$url" ;;
        *)  curl -fL --retry 3 -o "$dest" "$url" ;;
    esac
}

# Take an exclusive lock on an open file descriptor. flock(1) is not on macOS.
lock_fd() {
    local fd=$1

    if command -v flock > /dev/null 2>&1; then
        flock "$fd"
    elif command -v python3 > /dev/null 2>&1; then
        python3 -c 'import fcntl,sys; fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX)' "$fd"
    else
        fail "need flock or python3 to lock a workspace"
        return 1
    fi
}


# ---------------------------------------------------------------- capacity

# Refuse an allocation smaller than the measurement unit. See docs/design.md.
check_container_size() {
    [ "$(engine_family)" = docker ] && return 0
    [ -z "${SLURM_JOB_ID:-}" ] && return 0

    local want_cpu=$otog_cpus
    local want_mem=${otog_memory%g}
    local got_cpu=${SLURM_CPUS_ON_NODE:-0}
    local got_mem=$(( ${SLURM_MEM_PER_NODE:-0} / 1024 ))

    [ "$got_cpu" -ge "$want_cpu" ] && [ "$got_mem" -ge "$want_mem" ] && return 0
    fail "allocation is ${got_cpu} CPU + ${got_mem}g, the experiment needs ${want_cpu} + ${want_mem}g"
    fail "  ask for it: --cpus-per-task=$want_cpu --mem=${want_mem}G"
    return 1
}

# CPUs a container can have. Ask the engine first: Docker Desktop runs a VM.
machine_cpus() {
    local n
    n=$(engine_cpu_count 2> /dev/null)
    [ -n "$n" ] && { printf '%s' "$n"; return; }
    getconf _NPROCESSORS_ONLN 2> /dev/null || sysctl -n hw.ncpu 2> /dev/null || echo 4
}

machine_mem_gb() {
    local bytes
    bytes=$(engine_mem_bytes 2> /dev/null)
    [ -n "$bytes" ] && { printf '%s' $(( bytes / 1073741824 )); return; }

    if [ -r /proc/meminfo ]; then
        printf '%s' $(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
    else
        printf '%s' $(( $(sysctl -n hw.memsize 2> /dev/null || echo 8589934592) / 1073741824 ))
    fi
}

# The CPUs this process may use, one per line -- the SLURM allocation, not the node.
available_cpus() {
    local list
    if [ -r /proc/self/status ]; then
        list=$(awk '/^Cpus_allowed_list:/{print $2}' /proc/self/status)
        if [ -n "$list" ]; then
            echo "$list" | tr ',' '\n' | while IFS=- read -r a b; do seq "$a" "${b:-$a}"; done
            return 0
        fi
    fi
    seq 0 $(( $(machine_cpus) - 1 ))
}

# How many containers fit here: CPUs and memory both have a say.
parallel_slots() {
    [ "$otog_parallel" != auto ] && { printf '%s' "$otog_parallel"; return; }

    local by_cpu by_mem
    by_cpu=$(( $(machine_cpus) / otog_cpus ))
    by_mem=$(( $(machine_mem_gb) / ${otog_memory%g} ))
    [ "$by_mem" -lt "$by_cpu" ] && by_cpu=$by_mem
    [ "$by_cpu" -lt 1 ] && by_cpu=1
    printf '%s' "$by_cpu"
}

# The $otog_cpus CPUs this container is pinned to. Always pins. See docs/design.md.
cpu_slice() {
    local all count start
    all=$(available_cpus)
    count=$(echo "$all" | wc -l)
    [ "$count" -lt "$otog_cpus" ] && return 1

    start=$(( ($$ % (count / otog_cpus)) * otog_cpus + 1 ))
    echo "$all" | sed -n "${start},$((start + otog_cpus - 1))p" | paste -sd, -
}
