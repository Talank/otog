#!/bin/bash
#
# usage: source config_default.sh
# e.g.   source config_default.sh; echo "$otog_cpus"
#
# Settings for every run. Copy to config.sh to override; config.sh wins and is
# never overwritten by an update.

# The measurement unit. Every run gets exactly this, on every machine and both
# engines, or timings are not comparable across machines.
otog_cpus=4
otog_memory=16g
otog_repeats="${OTOG_REPEATS:-3}"

# The campaign run_experiment.sh covers when given no arguments. Modules are
# ordered cheapest-run-first, so a finished module is a deliverable while the
# expensive ones are still running.
otog_modules="1685 1683 3320 3323 2088 29 1778 20 1694 1305 1122 1497 33 3613 1216 1117"
otog_phases="v0 historical x10 x5"
otog_orders="1 100"

# docker | apptainer | auto (whichever is installed)
otog_engine="${OTOG_ENGINE:-auto}"

# How many containers at once. auto = cpus/otog_cpus, capped by memory.
# 250 is the figure the SLURM campaign uses; a laptop fits 1-2.
otog_parallel="${OTOG_PARALLEL:-auto}"

# JFR profiling. Off by default: it costs ~8% and a profiled run is not
# comparable with an unprofiled one. run_experiment.sh and run_once.sh both
# take a flag that turns it on for that invocation.
otog_jfr="${OTOG_JFR:-false}"
otog_jfr_settings="${OTOG_JFR_SETTINGS:-profile}"

otog_root="$tool_dir"
otog_orders_dir="$otog_root/orders"

# The orders are the experiment's input: ~17 GB unpacked, far too big for git,
# so setup.sh fetches them once. A google drive link is handled with gdown, any
# other URL with curl.
otog_orders_url="${OTOG_ORDERS_URL:-https://drive.google.com/file/d/1mIeWslnIdGQskIwrePRAQ_PmlWWldrgV/view?usp=sharing}"
otog_dependency_url="${OTOG_DEPENDENCY_URL:-https://drive.google.com/file/d/1IjEtfZzuYQ2hqfKfsWoBOD6NUG28KS-J/view?usp=sharing}"
otog_runs_dir="${OTOG_RUNS_DIR:-$otog_root/runs}"
otog_workspace_root="${OTOG_WORKSPACE_ROOT:-$otog_root/workspaces}"
otog_dependency_dir="$otog_root/dependency"
otog_image_dir="$otog_root/images"
otog_image_sif_dir="$otog_root/images_sif"

versions_csv="$otog_root/data/versions.csv"
idoft_flaky_tests_csv="$otog_root/data/idoft_flaky_tests.csv"
hanging_tests_csv="$otog_root/data/hanging_tests.csv"
fix_registry_csv="$otog_root/data/fix_registry.csv"
fix_strategies_csv="$otog_root/data/fix_strategies.csv"

# Where run_once.sh mounts things and where container/entrypoint.sh looks for
# them. Changing one means changing both, hence: config.
container_work_dir=/work
container_repo_dir=/work/repo
container_out_dir=/out
container_order_file=/order.txt
container_home_dir=/otog_home

# /m2 and NOT /root/.m2: docker runs the container as the calling user, and
# /root is drwx------ in the image, so a non-root uid cannot traverse into it.
container_m2_dir=/m2
container_m2_shared_dir=/m2-shared

# Each container resolves against its own copy, so no lock is needed --
# the resolver's file-lock sync context breaks outright on NFS under load.
maven_shared_repo_opts="-Daether.syncContext.named.factory=noop"

# apptainer only: where an image tag lives on disk. A .sif wins over a sandbox.
image_dir_for_tag() {
    local name
    name=$(printf '%s' "$1" | tr ':/' '__')
    if [ -f "$otog_image_sif_dir/$name.sif" ]; then
        printf '%s/%s.sif' "$otog_image_sif_dir" "$name"
    else
        printf '%s/%s' "$otog_image_dir" "$name"
    fi
}

# Where setup.sh writes one -- always the .sif image_dir_for_tag prefers.
sif_for_tag() {
    printf '%s/%s.sif' "$otog_image_sif_dir" "$(printf '%s' "$1" | tr ':/' '__')"
}

# JDK image per project. Anything unlisted gets java 8.
image_java8=maven:3.9-eclipse-temurin-8
image_java11=maven:3.9-eclipse-temurin-11
image_java17=maven:3.9-eclipse-temurin-17
image_java21=maven:3.9-eclipse-temurin-21

# The same images with a C toolchain baked in, for netty's native reactor.
# Baked in, and not installed by the native_build_toolchain fix at run time,
# because that fix needs root and a writable /usr: true under docker, false
# under apptainer, where the container runs as the calling user on a read-only
# image. Without these, all three netty modules fail to build on apptainer.
image_java8_native=otog/maven-3.9-eclipse-temurin-8-native
image_java11_native=otog/maven-3.9-eclipse-temurin-11-native

# What those two add. One list, so the two images cannot drift apart.
native_packages="build-essential autoconf automake libtool pkg-config"

native_source_image() {
    # The stock image a native tag is built from; empty if the tag is not one.
    case "$1" in
        "$image_java8_native")  echo "$image_java8"  ;;
        "$image_java11_native") echo "$image_java11" ;;
    esac
}

image_for_project() {
    case "$1" in
        spring-projects/spring-ai|flowable/flowable-engine|mapstruct/mapstruct) echo "$image_java17" ;;
        liquibase/liquibase|apache/incubator-kie-drools|apache/iotdb)           echo "$image_java17" ;;
        netty/netty)                                                            echo "$image_java8_native" ;;
        *)                                                                      echo "$image_java8"  ;;
    esac
}

# The few versions needing a different JDK than the rest of their project.
image_for_version() {
    local module_id=$1
    local version=$2

    case "$module_id" in
        1305)
            # async-http-client client: java 11 from v19 onward.
            [ "$version" -ge 19 ] 2> /dev/null && echo "$image_java11" ;;
        1685)
            # javaparser-core-testing: java 11 at exactly v-18 and v-17.
            case "$version" in -18 | -17) echo "$image_java11" ;; esac ;;
        1216)
            # mapstruct added jdk21/ test sources in 2c84d04463a3 (2025-05-11),
            # which use SequencedCollection. v87 is the first version descended
            # from that commit; on java 17 its testCompile cannot find them.
            [ "$version" -ge 87 ] 2> /dev/null && echo "$image_java21" ;;
        20)
            # netty transport-native-epoll: 4.2.3 at v100 needs java 11; v90
            # and earlier build on java 8, verified under both.
            [ "$version" = 100 ] && echo "$image_java11_native" ;;
    esac
    return 0
}

# Maven flags every build gets: skip everything that is not the tests. Four of
# them are not obvious -- japicmp.skip, the settings.xml mirror, the retry
# handlers, and legacyLocalRepo. See docs/design.md, "Maven flags".
MVN_OPTS="-Djacoco.skip=true -Dmaven.javadoc.skip=true -Drat.skip=true
-Dlicense.skip=true -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip=true
-Dfindbugs.skip=true -Ddependency-check.skip=true -Dmaven.test.failure.ignore=true
-Dhawtjni.skip=true -Drevapi.skip=true -Djapicmp.skip=true -Dgpg.skip=true
-DfailIfNoTests=false -fn
-Dmaven.wagon.http.retryHandler.count=6
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true
-Dmaven.wagon.httpconnectionManager.ttlSeconds=60 -Dmaven.wagon.rto=120000
-Daether.connector.http.retryHandler.count=6
-Daether.connector.http.retryHandler.requestSentEnabled=true
-Daether.connector.connectTimeout=60000 -Daether.connector.requestTimeout=120000
-s /otog/aux/settings.xml -Dmaven.legacyLocalRepo=true"
MVN_OPTS=$(echo $MVN_OPTS)

# Apptainer cannot enforce $otog_memory, so a JVM would size its heap off the
# whole machine and get the job killed. Set OTOG_JVM_HEAP= to disable.
otog_jvm_heap="${OTOG_JVM_HEAP-${otog_memory%g}g}"
if [ -n "$otog_jvm_heap" ]; then
    export MAVEN_OPTS="${MAVEN_OPTS:+$MAVEN_OPTS }-Xmx2g"
    MVN_OPTS="$MVN_OPTS -DargLine=-Xmx$otog_jvm_heap"
fi

# The backstop for the forks -DargLine never reaches. OFF by default: every
# timing collected so far was taken without it. See docs/design.md, "Heap".
otog_jvm_max_ram="${OTOG_JVM_MAX_RAM-}"

# The maven extension that makes -Dsurefire.runOrder=testorder impose the
# order. Without it a run still passes -- having measured nothing.
surefire_extension_jar=/otog/aux/surefire-changing-maven-extension-1.0-SNAPSHOT.jar

# The forked plugin that extension pins every build to. It must be in the
# seeded dependency/ repo, and must carry PR #15. See docs/design.md.
surefire_fork_version=3.0.0-M8-SNAPSHOT
