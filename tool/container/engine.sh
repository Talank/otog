#!/bin/bash
#
# usage: source container/engine.sh; engine_run --image <tag> [opts] -- <command>
# e.g.   source container/engine.sh; engine_run --image maven:3.9-eclipse-temurin-8 -- mvn -v
#
# Docker and apptainer behind one interface, so nothing above this file knows
# which engine it is on.
#
# in : $otog_engine (docker|apptainer|auto)
# out: engine_kind, engine_run, engine_image_exists, engine_pull

# --------------------------------------------------------------- which engine

# The engine to use: $otog_engine if set, else the first daemonless one installed.
engine_kind() {
    if [ -n "${otog_engine:-}" ] && [ "${otog_engine}" != auto ]; then
        echo "$otog_engine"
        return 0
    fi

    local candidate
    for candidate in apptainer singularity docker; do
        if command -v "$candidate" > /dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

# apptainer and singularity take the same flags; docker does not.
engine_family() {
    case "$(engine_kind 2> /dev/null)" in
        apptainer | singularity) echo "apptainer" ;;
        docker | podman | nerdctl) echo "docker" ;;
        *) return 1 ;;
    esac
}

# On PATH is not the same as usable: docker is installed for non-group members too.
engine_is_usable() {
    local kind
    kind=$(engine_kind) || return 1

    command -v "$kind" > /dev/null 2>&1 || return 1

    if [ "$(engine_family)" = "docker" ]; then
        "$kind" info > /dev/null 2>&1 || return 1
    fi
    return 0
}

# Exit with advice unless an engine is usable. A dry run needs none.
require_engine() {
    [ -n "${OTOG_ENGINE_DRYRUN:-}" ] && return 0

    local kind
    if ! kind=$(engine_kind); then
        print_fail_message "error: no container engine on PATH (apptainer, singularity or docker)"
        print_fail_message "       on a cluster:  module load apptainer/1.4.1"
        print_fail_message "       elsewhere:     install docker, or set OTOG_ENGINE"
        exit 1
    fi

    if ! engine_is_usable; then
        print_fail_message "error: $kind is on PATH but not usable"
        if [ "$(engine_family)" = "docker" ]; then
            print_fail_message "       \`$kind info\` failed. The daemon is not running, or you are"
            print_fail_message "       not in the docker group:  id -nG | tr ' ' '\\n' | grep docker"
        fi
        exit 1
    fi
}

# ---------------------------------------------------------------- image names

# What this engine wants passed where an image goes.
engine_image_ref() {
    local tag=$1

    if [ "$(engine_family)" = "docker" ]; then
        printf '%s' "$tag"
    else
        image_dir_for_tag "$tag"
    fi
}

# Is this image already here? docker keeps tags, apptainer keeps files.
engine_image_exists() {
    local tag=$1
    local ref
    ref=$(engine_image_ref "$tag")

    if [ "$(engine_family)" = "docker" ]; then
        # images -q, not inspect: inspect resolves only fully qualified refs
        # under docker's containerd image store.
        [ -n "$("$(engine_kind)" images -q "$ref" 2> /dev/null)" ]
    else
        # -e not -d: a ref is a sandbox directory or a .sif file.
        [ -e "$ref" ]
    fi
}

# --------------------------------------------------------------- capacity

# What the ENGINE can give a container: Docker Desktop's VM, not the host.
# Print nothing when the engine cannot be asked.

engine_cpu_count() {
    [ "$(engine_family 2> /dev/null)" = docker ] || return 1
    "$(engine_kind)" info --format '{{.NCPU}}' 2> /dev/null | grep -Ex '[0-9]+'
}

engine_mem_bytes() {
    [ "$(engine_family 2> /dev/null)" = docker ] || return 1
    "$(engine_kind)" info --format '{{.MemTotal}}' 2> /dev/null | grep -Ex '[0-9]+'
}

# ------------------------------------------------------------------- running

# Run one command in one container, the same way on both engines.
engine_run() {
    local image="" workdir="" home_spec="" cpuset="" memory="" name=""
    local envs=() binds=() command=()

    while [ $# -gt 0 ]; do
        case "$1" in
            --image)   image=$2;     shift 2 ;;
            --workdir) workdir=$2;   shift 2 ;;
            --home)    home_spec=$2; shift 2 ;;
            --cpuset)  cpuset=$2;    shift 2 ;;
            --memory)  memory=$2;    shift 2 ;;
            --name)    name=$2;      shift 2 ;;
            --env)     envs+=("$2");  shift 2 ;;
            --bind)    binds+=("$2"); shift 2 ;;
            --)        shift; command=("$@"); break ;;
            *)
                print_fail_message "error: engine_run: unknown argument $1"
                return 2
                ;;
        esac
    done

    if [ -z "$image" ] || [ ${#command[@]} -eq 0 ]; then
        print_fail_message "error: engine_run needs --image and a -- command"
        return 2
    fi

    # Docker reads a relative -v source as a named volume, not a path.
    local spec
    for spec in "${binds[@]}"; do
        case "$spec" in
            /*) ;;
            *)
                print_fail_message "error: engine_run: bind source must be absolute: $spec"
                return 2
                ;;
        esac
    done

    local ref
    ref=$(engine_image_ref "$image")

    local argv=()
    if [ "$(engine_family)" = "docker" ]; then
        argv=("$(engine_kind)" run --rm --init)

        # Without --user, everything written into runs/ is owned by root.
        argv+=(--user "$(id -u):$(id -g)")

        # cpuset, never --cpus: a share of every CPU is not four CPUs.
        [ -n "$cpuset" ] && argv+=(--cpuset-cpus "$cpuset")
        if [ -n "$memory" ]; then
            argv+=(--memory "$memory" --memory-swap "$memory")
        fi

        [ -n "$name" ] && argv+=(--name "$name")
        [ -n "$workdir" ] && argv+=(-w "$workdir")

        if [ -n "$home_spec" ]; then
            argv+=(-v "$home_spec")
            argv+=(-e "HOME=${home_spec##*:}")
        fi
        for spec in "${envs[@]}"; do argv+=(-e "$spec"); done
        for spec in "${binds[@]}"; do argv+=(-v "$spec"); done
        argv+=("$ref" "${command[@]}")
    else
        # taskset: apptainer cannot cgroup-limit unprivileged, and affinity
        # is inherited by the JVM the suite actually runs in.
        if [ -n "$cpuset" ] && command -v taskset > /dev/null 2>&1; then
            argv=(taskset -c "$cpuset")
        fi
        argv+=("$(engine_kind)" exec --cleanenv)

        # No memory limit is possible here: the allocation bounds the
        # container, and check_container_size() is what refuses a wrong one.
        [ -n "$workdir" ] && argv+=(--pwd "$workdir")
        [ -n "$home_spec" ] && argv+=(--home "$home_spec")
        for spec in "${envs[@]}"; do argv+=(--env "$spec"); done
        for spec in "${binds[@]}"; do argv+=(--bind "$spec"); done
        argv+=("$ref" "${command[@]}")
    fi

    # OTOG_ENGINE_DRYRUN prints the argv, one argument per line, and runs nothing.
    if [ -n "${OTOG_ENGINE_DRYRUN:-}" ]; then
        printf '%s\n' "${argv[@]}"
        return 0
    fi

    "${argv[@]}"
}

# Fetch an image: docker into its own store, apptainer into a .sif here.
engine_pull() {
    local tag=$1
    case "$(engine_family)" in
        docker)
            docker pull "$tag"
            ;;
        apptainer)
            # A .sif is one file; a --sandbox is thousands, and on shared
            # storage its ELF files have been seen disappearing.
            local sif; sif=$(sif_for_tag "$tag")
            mkdir -p "$(dirname "$sif")"
            # An interrupted build leaves .sif.tmp behind, and apptainer then
            # asks whether to overwrite it rather than just building.
            rm -f "$sif.tmp"
            "$(engine_kind)" build "$sif.tmp" "docker://$tag" && mv "$sif.tmp" "$sif"
            ;;
    esac
}
