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
otog_dependency_url="${OTOG_DEPENDENCY_URL:-https://drive.google.com/file/d/1oqSBp0uDcBrmQWD-SnE4zvONCwtROvmd/view?usp=sharing}"
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

image_for_project() {
    case "$1" in
        spring-projects/spring-ai|flowable/flowable-engine|mapstruct/mapstruct) echo "$image_java17" ;;
        liquibase/liquibase|apache/incubator-kie-drools|apache/iotdb)           echo "$image_java17" ;;
        *)                                                                      echo "$image_java8"  ;;
    esac
}

# A few versions need a different JDK than the rest of their project.
image_for_version() {
    case "$1:$2" in
        1216:9[0-9]|1216:100) echo "$image_java21" ;;
        1305:[2-9][0-9]|1305:100) echo "$image_java11" ;;
    esac
}

# Maven flags every build gets: skip everything that is not the tests.
MVN_OPTS="-Djacoco.skip=true -Dmaven.javadoc.skip=true -Drat.skip=true
-Dlicense.skip=true -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip=true
-Dfindbugs.skip=true -Ddependency-check.skip=true -Dmaven.test.failure.ignore=true
-Drevapi.skip=true -Djapicmp.skip=true -Dgpg.skip=true -DfailIfNoTests=false -fn
-Dmaven.wagon.http.retryHandler.count=6 -Daether.connector.http.retryHandler.count=6
-Daether.connector.connectTimeout=60000 -Daether.connector.requestTimeout=120000"
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
# the JVM can see -- its cgroup under docker, but the whole node under
# apptainer, which is 64g of heap on a 256g machine. -XX:MaxRAM rather than a
# second -Xmx, so a heap nobody configured stays the JVM's own default.
otog_jvm_max_ram="${OTOG_JVM_MAX_RAM:-$otog_memory}"

# The maven extension that makes -Dsurefire.runOrder=testorder actually
# impose the order. Without it a run still passes -- having measured nothing.
surefire_extension_jar=/otog/aux/surefire-changing-maven-extension-1.0-SNAPSHOT.jar
