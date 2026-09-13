# Settings for every run. Copy to config.sh to override; config.sh wins and is
# never overwritten by an update.

# The measurement unit. Every run gets exactly this, on every machine and both
# engines, or timings are not comparable across machines.
otog_cpus=4
otog_memory=16g
otog_repeats=3

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
otog_orders_url="${OTOG_ORDERS_URL:-https://drive.google.com/file/d/1YWehYp3KAh2KubJcHE2w600N_qgicdZz/view?usp=sharing}"
otog_dependency_url="${OTOG_DEPENDENCY_URL:-https://drive.google.com/file/d/1IjEtfZzuYQ2hqfKfsWoBOD6NUG28KS-J/view?usp=sharing}"
otog_runs_dir="${OTOG_RUNS_DIR:-$otog_root/runs}"
otog_workspace_root="${OTOG_WORKSPACE_ROOT:-$otog_root/workspaces}"
otog_dependency_dir="$otog_root/dependency"
otog_image_dir="$otog_root/images"
otog_image_sif_dir="$otog_root/images_sif"

versions_csv="$otog_root/data/versions.csv"
idoft_flaky_tests_csv="$otog_root/data/idoft_flaky_tests.csv"
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
# resolver's file-lock sync context breaks outright on NFS under load.
maven_shared_repo_opts="-Daether.syncContext.named.factory=noop"

# apptainer only: where an image tag lives on disk. A .sif wins over a sandbox
# directory -- sandbox trees on shared storage have been seen losing individual
# ELF files, which breaks every run with "executable file not found".
image_dir_for_tag() {
    local name
    name=$(printf '%s' "$1" | tr ':/' '__')
    if [ -f "$otog_image_sif_dir/$name.sif" ]; then
        printf '%s/%s.sif' "$otog_image_sif_dir" "$name"
    else
        printf '%s/%s' "$otog_image_dir" "$name"
    fi
}

# Where setup.sh writes one. Always the .sif: it is what image_dir_for_tag
# picks up next time, and the sandbox branch above is only for trees that
# already have one.
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

# A few versions need a different JDK than the rest of their project. Numeric
# tests, not globs on "$1:$2": a glob has to spell out every version it covers,
# and the ones it silently missed (1216 v87-v89, 1305 v19) are versions whose
# test sources do not compile on the project's usual JDK. With -fn the reactor
# carries on regardless, so the build is called OK and the test list comes back
# EMPTY -- a wrong answer rather than a failure.
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
# these are not obvious:
#   -Djapicmp.skip=true   mapstruct binds japicmp to the build for 14 straight
#                         versions; they fail on that goal with no compilation
#                         error at all.
#   -s aux/settings.xml   Central answers 429 for EVERY artifact when the
#                         request comes from a compute node, and maven records
#                         that as a compile failure -- which is exactly what a
#                         broken commit looks like. That file mirrors central to
#                         Google's byte-for-byte copy. Maven does NOT fall back
#                         from a mirror, so read it before changing this.
#   retryHandler / rto / ttlSeconds
#                         Belt and braces for the same fault: a transport error
#                         is indistinguishable from a broken commit.
#   -Dmaven.legacyLocalRepo=true
#                         The seeded repo's _remote.repositories files record
#                         every artifact as coming from repo id `central`, but
#                         the mirror above renames that id, so maven calls each
#                         seeded artifact "present, but unavailable" and
#                         re-verifies it over the network -- 164 needless round
#                         trips per run, measured, any one of which can reset
#                         and fail the build. The flag makes the resolver trust
#                         the local repo rather than its origin tracking. Same
#                         jars, same versions, so execution is unchanged:
#                         A/B'd on 1685 v90 order 10, both arms PASS with 247
#                         reports, re-verifications 164 -> 0, wall 897s -> 664s.
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

# Apptainer cannot enforce $otog_memory, so the container sees the whole
# machine's MemTotal and JDK 8 would size its heap off that -- and get the job
# killed. Tell the JVMs directly. Set OTOG_JVM_HEAP= to disable.
otog_jvm_heap="${OTOG_JVM_HEAP-${otog_memory%g}g}"
if [ -n "$otog_jvm_heap" ]; then
    export MAVEN_OPTS="${MAVEN_OPTS:+$MAVEN_OPTS }-Xmx2g"
    MVN_OPTS="$MVN_OPTS -DargLine=-Xmx$otog_jvm_heap"
fi

# The backstop for where that -DargLine never arrives: jacoco's prepare-agent
# rewrites the argLine property mid-build, and the fork is then sized by what
# the JVM can see -- its cgroup under docker, but the whole NODE under
# apptainer, which measured 30g of heap on this 376g login node and would be
# ~61g on a 244g compute node. Way over the 16g the container is supposed to be.
#
# The percentage is not optional. -XX:MaxRAM alone only tells the JVM how much
# machine to assume, and it still takes MaxRAMPercentage of it -- the default
# 25%, so MaxRAM=16g yields a 4g heap. Measured, temurin-17:
#   nothing                        29.97g
#   MaxRAM=16g                      4.00g
#   MaxRAM=16g MaxRAMPercentage=100 16.00g
# The last is the one that means "this container's whole 16g is available",
# which is what -DargLine=-Xmx16g already gives every fork that receives it.
# An explicit -Xmx still wins over both, so the normal path is unchanged.
# OFF by default, and that is deliberate. Every timing already collected was
# taken WITHOUT it, and a run only means something next to the other runs of
# the same order: setting it here would give the profiled repetitions of an
# order a different heap regime from the plain ones they are compared against.
# Turn it on (OTOG_JVM_MAX_RAM=16g) only for a campaign that re-runs everything.
otog_jvm_max_ram="${OTOG_JVM_MAX_RAM-}"

# The maven extension that makes -Dsurefire.runOrder=testorder actually
# impose the order. Without it a run still passes -- having measured nothing.
surefire_extension_jar=/otog/aux/surefire-changing-maven-extension-1.0-SNAPSHOT.jar

# The forked plugin that extension pins every build to. It has to be in the
# seeded dependency/ repo, and it has to be a build that carries PR #15 -- see
# check_surefire_fork() in setup.sh for what goes wrong when it is not.
surefire_fork_version=3.0.0-M8-SNAPSHOT
