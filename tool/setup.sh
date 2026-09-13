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

images="$image_java8 $image_java11 $image_java17 $image_java21
        $image_java8_native $image_java11_native"


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

quietly() {
    # Pulling and building images prints hundreds of lines -- layer progress,
    # apt-get, beanshell. Setup should read as one line per step, so keep the
    # transcript and only open it when the step actually fails.
    local log; log=$(mktemp) || return 1
    "$@" > "$log" 2>&1 || {
        fail "  failed -- last 20 lines of $*:"
        tail -20 "$log" >&2
        rm -f "$log"
        return 1
    }
    rm -f "$log"
}

build_native_image() {
    # A stock image plus the C toolchain netty's native reactor needs. It is
    # baked in here, and not installed by the native_build_toolchain fix while
    # the run is going, because that needs root and a writable /usr -- true
    # under docker, false under apptainer, which runs as the calling user on a
    # read-only image.
    local tag=$1
    local source_tag=$2
    local rc

    if [ "$(engine_family)" = docker ]; then
        # An empty build context holding only the Dockerfile: handing docker
        # the tool directory would ship the whole runs/ tree to the daemon.
        local context; context=$(mktemp -d) || return 1
        cat > "$context/Dockerfile" <<DOCKERFILE
FROM $source_tag
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends $native_packages \
    && rm -rf /var/lib/apt/lists/*
DOCKERFILE
        docker build -t "$tag" "$context"; rc=$?
        rm -rf "$context"
        return $rc
    fi

    # A sandbox is apptainer's only writable form, so build one, add the
    # toolchain, then seal it into the .sif that every run uses.
    local sif; sif=$(sif_for_tag "$tag")
    local sandbox="$sif.sandbox"
    mkdir -p "$(dirname "$sif")"
    rm -rf "$sandbox" "$sif.tmp"

    "$(engine_kind)" build --sandbox "$sandbox" "docker://$source_tag" || {
        rm -rf "$sandbox"; return 1
    }

    # Three things this needs that a plain apt-get install does not:
    #   --fakeroot            uid 0 inside, or dpkg cannot unpack
    #   APPTAINER_BIND unset  the apptainer module presets binds, and with
    #                         --writable apptainer cannot create a missing
    #                         mountpoint
    #   APT::Sandbox::User    apt drops to the _apt user to fetch, and a
    #                         root-mapped namespace with no subuid range has no
    #                         second uid to drop TO
    env -u APPTAINER_BIND -u SINGULARITY_BIND \
        "$(engine_kind)" exec --fakeroot --writable "$sandbox" \
        bash -c "export DEBIAN_FRONTEND=noninteractive
                 apt-get -o APT::Sandbox::User=root update -qq \
                 && apt-get -o APT::Sandbox::User=root install -y -qq \
                        --no-install-recommends $native_packages" || {
        fail "could not install the C toolchain into $tag"
        rm -rf "$sandbox"; return 1
    }

    # libtoolize, not libtool: the package ships the macros and libtoolize, and
    # the libtool script itself is generated per project by configure. netty's
    # autogen.sh calls libtoolize.
    "$(engine_kind)" exec "$sandbox" \
        bash -c 'command -v make gcc autoconf automake libtoolize > /dev/null' || {
        fail "$tag still has no complete C toolchain"
        rm -rf "$sandbox"; return 1
    }

    "$(engine_kind)" build "$sif.tmp" "$sandbox" && mv "$sif.tmp" "$sif"; rc=$?
    rm -rf "$sandbox"
    return $rc
}

build_images() {
    local image source
    for image in $images; do
        if engine_image_exists "$image"; then
            say "have   $image"
            continue
        fi
        source=$(native_source_image "$image")
        if [ -n "$source" ]; then
            say "build  $image (from $source, + C toolchain)"
            quietly build_native_image "$image" "$source" || return 1
        else
            say "build  $image"
            quietly engine_pull "$image" || return 1
        fi
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

check_surefire_fork() {
    # The whole experiment rests on -Dsurefire.runOrder=testorder actually
    # imposing the order, and that takes a FORK of maven-surefire, seeded into
    # dependency/. Two things can be wrong with what arrives there, and both
    # look like a working run that measured the wrong thing:
    #
    #   the plugin is missing     every order run dies "Plugin could not be
    #                             resolved", which is at least loud.
    #   the plugin is there, but  built without PR #15. Then the JUnit 5
    #   without the method        provider hands whole classes to the Jupiter
    #   orderer                   engine and lets the engine pick method order,
    #                             so class order is imposed and method order is
    #                             not -- silently, on every JUnit 5 project.
    local repo=$otog_dependency_dir/org/apache/maven
    local plugin=$repo/plugins/maven-surefire-plugin/$surefire_fork_version
    local provider=$repo/surefire/surefire-junit-platform/$surefire_fork_version
    local jar=$provider/surefire-junit-platform-$surefire_fork_version.jar
    local ext_jar=$tool_dir/aux/$(basename "$surefire_extension_jar")

    [ -d "$plugin" ] || {
        fail "dependency/ has no maven-surefire-plugin:$surefire_fork_version"
        fail "  the order-imposing fork is what makes runOrder=testorder work"
        return 1
    }

    [ -f "$jar" ] || {
        fail "dependency/ has no surefire-junit-platform:$surefire_fork_version"
        return 1
    }

    # Named rather than globbed, and matched on the .class entry: a -sources or
    # -javadoc jar sorts ahead of the real one and carries the same name in a
    # .java or .html entry, so a glob would let a fork built WITHOUT PR #15
    # pass. Read the listing before matching, too -- piping it into grep -q
    # lets grep exit on the match, SIGPIPEs unzip, and pipefail reports that as
    # a missing class on a few percent of runs.
    local listing; listing=$(unzip -l "$jar" 2> /dev/null)
    case "$listing" in
        *"org/apache/maven/surefire/junitplatform/TestOrderMethodOrderer.class"*) ;;
        *) fail "$(basename "$jar") has no TestOrderMethodOrderer"
           fail "  built without PR #15, so JUnit 5 method order will NOT be imposed"
           return 1 ;;
    esac

    # Without the extension maven quietly keeps whatever surefire the project's
    # own pom asks for -- and dependency/ carries a dozen other versions, so the
    # run passes having measured nothing at all.
    [ -s "$ext_jar" ] || {
        fail "aux/ has no $(basename "$ext_jar")"
        fail "  without it -Dsurefire.runOrder=testorder imposes no order"
        return 1
    }

    say "have   surefire fork $surefire_fork_version (with the JUnit 5 method orderer)"
}

check_jfrsort_agent() {
    # Shipped built, in git, like the surefire extension beside it: setup
    # compiles nothing on the host, so a machine with no JDK -- or one whose
    # JDK is newer than the sources expect -- still sets up.
    local aux_jar="$tool_dir/aux/jfrsort-agent.jar"

    [ -s "$aux_jar" ] || {
        fail "aux/ has no jfrsort-agent.jar"
        fail "  rebuild it from jfrsort/agent and commit it, or restore the checkout"
        return 1
    }

    say "have   jfrsort agent"
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
check_surefire_fork || die "the seeded dependency repo cannot impose test order"
check_jfrsort_agent || die "the jfrsort agent is missing"
report
