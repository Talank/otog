#!/bin/bash
#
# source container/engine.sh; engine_run --image maven:3.9-eclipse-temurin-8 -- bash -c 'mvn -v'
#
# Docker and apptainer behind one interface, so nothing above this file knows
# which engine it is on.
#
# in : $otog_engine (docker|apptainer|auto)
# out: engine_kind, engine_run, engine_image_exists, engine_pull

# --------------------------------------------------------------- which engine

engine_kind() {
    # $otog_engine wins -- a cluster may install apptainer under a third name,
    # and a docker user wants to say so explicitly. Otherwise prefer the
    # daemonless engines: on a shared machine they are the ones that work.
    # "auto" is the default and means detect below; anything else is a name.
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

engine_family() {
    # apptainer and singularity take the same flags; docker does not.
    case "$(engine_kind 2> /dev/null)" in
        apptainer | singularity) echo "apptainer" ;;
        docker | podman | nerdctl) echo "docker" ;;
        *) return 1 ;;
    esac
}

engine_is_usable() {
    # Present on PATH is not the same as usable. The docker binary is installed
    # on machines whose owner is not in the docker group, so presence is not enough.
    local kind
    kind=$(engine_kind) || return 1

    # $otog_engine is taken on trust by engine_kind -- it has to be, since it
    # exists to name an engine this script does not know about. Here is where
    # that trust is checked.
    command -v "$kind" > /dev/null 2>&1 || return 1

    if [ "$(engine_family)" = "docker" ]; then
        "$kind" info > /dev/null 2>&1 || return 1
    fi
    return 0
}

require_engine() {
    # A dry run prints the command and starts nothing, so it must work on a
    # machine with no engine installed at all -- that is how someone reads what
    # a run would do before committing to it.
    [ -n "${OTOG_ENGINE_DRYRUN:-}" ] && return 0

    local kind
    if ! kind=$(engine_kind); then
        print_fail_message "❌ No container engine on PATH (apptainer, singularity or docker)"
        print_fail_message "   on a cluster:  module load apptainer/1.4.1"
        print_fail_message "   elsewhere:     install docker, or set OTOG_ENGINE"
        exit 1
    fi

    if ! engine_is_usable; then
        print_fail_message "❌ $kind is on PATH but not usable"
        if [ "$(engine_family)" = "docker" ]; then
            print_fail_message "   \`$kind info\` failed. The daemon is not running, or you are"
            print_fail_message "   not in the docker group:  id -nG | tr ' ' '\\n' | grep docker"
        fi
        exit 1
    fi
}

# ---------------------------------------------------------------- image names

engine_image_ref() {
    # What this engine wants passed where an image goes.
    local tag=$1

    if [ "$(engine_family)" = "docker" ]; then
        printf '%s' "$tag"
    else
        image_dir_for_tag "$tag"
    fi
}

engine_image_exists() {
    local tag=$1
    local ref
    ref=$(engine_image_ref "$tag")

    if [ "$(engine_family)" = "docker" ]; then
        # images -q, not image inspect: with docker's containerd image store
        # inspect resolves only fully qualified refs, and would report every
        # short tag missing on a machine that can in fact run it.
        [ -n "$("$(engine_kind)" images -q "$ref" 2> /dev/null)" ]
    else
        # -e not -d: a ref is a sandbox directory or a .sif file.
        [ -e "$ref" ]
    fi
}

# --------------------------------------------------------------- capacity

# What the engine can give a container, which is not what the host reports when
# Docker Desktop runs them in a VM: a 64 GB Mac whose VM has 16 GB fits ONE
# container, not four. Print nothing when the engine cannot be asked.

engine_cpu_count() {
    [ "$(engine_family 2> /dev/null)" = docker ] || return 1
    "$(engine_kind)" info --format '{{.NCPU}}' 2> /dev/null | grep -Ex '[0-9]+'
}

engine_mem_bytes() {
    [ "$(engine_family 2> /dev/null)" = docker ] || return 1
    "$(engine_kind)" info --format '{{.MemTotal}}' 2> /dev/null | grep -Ex '[0-9]+'
}

# ------------------------------------------------------------------- running

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
                print_fail_message "❌ engine_run: unknown argument $1"
                return 2
                ;;
        esac
    done

    if [ -z "$image" ] || [ ${#command[@]} -eq 0 ]; then
        print_fail_message "❌ engine_run needs --image and a -- command"
        return 2
    fi

    # Docker reads a relative -v source as a named volume, not a path, so bind
    # mounts must be absolute.
    local spec
    for spec in "${binds[@]}"; do
        case "$spec" in
            /*) ;;
            *)
                print_fail_message "❌ engine_run: bind source must be absolute: $spec"
                return 2
                ;;
        esac
    done

    local ref
    ref=$(engine_image_ref "$image")

    local argv=()
    if [ "$(engine_family)" = "docker" ]; then
        argv=("$(engine_kind)" run --rm --init)

        # Without --user, docker runs the container as root and every file it
        # writes into the bind-mounted runs/ directory is owned by root -- on a
        # machine where the caller cannot chown them back.
        argv+=(--user "$(id -u):$(id -g)")

        # cpuset, never --cpus. See the note at the top of this file.
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
        # taskset, because apptainer cannot apply cgroup limits unprivileged.
        # Affinity is inherited, so pinning the engine pins the JVM the suite
        # actually runs in.
        if [ -n "$cpuset" ] && command -v taskset > /dev/null 2>&1; then
            argv=(taskset -c "$cpuset")
        fi
        argv+=("$(engine_kind)" exec --cleanenv)

        # No memory limit is possible here. Said out loud rather than ignored:
        # under apptainer the allocation is what bounds the container, and it is
        # the caller's job to ask for the right one.
        [ -n "$workdir" ] && argv+=(--pwd "$workdir")
        [ -n "$home_spec" ] && argv+=(--home "$home_spec")
        for spec in "${envs[@]}"; do argv+=(--env "$spec"); done
        for spec in "${binds[@]}"; do argv+=(--bind "$spec"); done
        argv+=("$ref" "${command[@]}")
    fi

    # OTOG_ENGINE_DRYRUN prints the argv, one argument per line, and runs
    # nothing. That is what the tests assert against, and it is how to see what
    # a run would do without a container engine present at all.
    if [ -n "${OTOG_ENGINE_DRYRUN:-}" ]; then
        printf '%s\n' "${argv[@]}"
        return 0
    fi

    "${argv[@]}"
}

engine_pull() {
    # docker keeps tags in its own store; apptainer builds a sandbox dir here.
    local tag=$1
    case "$(engine_family)" in
        docker)
            docker pull "$tag"
            ;;
        apptainer)
            # A .sif is one file. A --sandbox is thousands, and on shared
            # storage its ELF files have been seen disappearing, which breaks
            # every later run with "executable file not found".
            local sif; sif=$(sif_for_tag "$tag")
            mkdir -p "$(dirname "$sif")"
            "$(engine_kind)" build "$sif.tmp" "docker://$tag" && mv "$sif.tmp" "$sif"
            ;;
    esac
}
