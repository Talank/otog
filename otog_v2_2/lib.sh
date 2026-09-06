# Sourced by every script. Loads config, then defines what they share.

tool_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$tool_dir/config_default.sh"
[ -f "$tool_dir/config.sh" ] && source "$tool_dir/config.sh"
source "$tool_dir/container/engine.sh"

say()  { printf '%s\n' "$*"; }
fail() { printf '%s\n' "$*" >&2; }

# engine.sh is sourced here and inside the container, where runtime.sh names
# these differently. Same vocabulary on both sides.
print_info_message() { say "$@"; }
print_fail_message() { fail "$@"; }

die() {
    fail "$*"
    exit 1
}

usage_of() {
    # The header comment of a script is its usage. One place to edit.
    sed -n '3,/^$/p' "$1" | sed 's/^# \{0,1\}//'
}

# in : module version -> out: slug,module,sha
version_row() {
    awk -F, -v m="$1" -v v="$2" 'NR>1 && $1==m && $4==v {print $2","$3","$5; exit}' "$versions_csv"
}

module_versions() {
    awk -F, -v m="$1" 'NR>1 && $1==m {print $4}' "$versions_csv" | sort -n
}

all_modules() {
    awk -F, 'NR>1 {print $1}' "$versions_csv" | sort -un
}

order_file() {
    # A number means orders/<module>/<version>/<n>.txt; anything else is a path.
    case "$3" in
        ''|*[!0-9-]*) printf '%s' "$3" ;;
        *)            printf '%s/%s/%s/%s.txt' "$otog_orders_dir" "$1" "$2" "$3" ;;
    esac
}

run_status() {
    head -1 "$1/status" 2>/dev/null || echo NONE
}

run_passed() {
    [ "$(run_status "$1")" = PASS ]
}

# flock(1) is util-linux and not on macOS. python3 locks the same open file
# description, so the lock outlives the helper and is released by the kernel
# when this shell's fd closes -- same guarantee, both platforms.
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

# What a container can be given here. Ask the engine first: under Docker
# Desktop it is the VM's allocation, not the Mac's, that bounds a run.
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

# The CPUs a container may be pinned to, one per line. On Linux that is the
# affinity mask we inherited -- a SLURM allocation, not the whole node.
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

# How many containers this machine can hold: CPUs and memory both have a say.
parallel_slots() {
    [ "$otog_parallel" != auto ] && { printf '%s' "$otog_parallel"; return; }

    local by_cpu by_mem
    by_cpu=$(( $(machine_cpus) / otog_cpus ))
    by_mem=$(( $(machine_mem_gb) / ${otog_memory%g} ))
    [ "$by_mem" -lt "$by_cpu" ] && by_cpu=$by_mem
    [ "$by_cpu" -lt 1 ] && by_cpu=1
    printf '%s' "$by_cpu"
}

# The $otog_cpus CPUs this container gets. Always pins: an unpinned container
# quietly takes the whole machine and is no longer the unit being measured.
cpu_slice() {
    local all count start
    all=$(available_cpus)
    count=$(echo "$all" | wc -l)
    [ "$count" -lt "$otog_cpus" ] && return 1

    # Pick a slice by pid so concurrent containers land on different CPUs.
    start=$(( ($$ % (count / otog_cpus)) * otog_cpus + 1 ))
    echo "$all" | sed -n "${start},$((start + otog_cpus - 1))p" | paste -sd, -
}
