#!/bin/bash
#
# source container/jfr.sh
#
# JFR profiling, sourced by entrypoint.sh. Does nothing unless OTOG_JFR is set,
# so an ordinary run stays comparable with every unprofiled one.
#
# The pipeline, in the order entrypoint.sh calls it:
#
#   jfr_before_mvn <out_dir>                 what to record -> JAVA_TOOL_OPTIONS
#   ... mvn test ...                         every JVM writes its own recording
#   jfr_after_mvn <out_dir> <pid> <module>   keep the fork's, name it, count it
#
# in : OTOG_JFR, OTOG_JFR_SETTINGS (a .jfc name or path)
# out: <out_dir>/jfr/<module>.jfr

jfr_settings_file="${OTOG_JFR_SETTINGS:-profile}"

# What jfrsort records on top of the .jfc preset: a sampler throttle above
# profile's 150/s, and the events behind the PROBO metric set (Baz/Lam/Shi,
# ISSTA 2026), which profile's own thresholds otherwise suppress almost
# entirely. TLAB allocation events stay off -- too much volume for one metric.
JFR_EVENTS="jdk.ObjectAllocationSample#throttle=1000/s\
,jdk.Compilation#threshold=0ms,jdk.ClassLoad#enabled=true\
,jdk.FileRead#threshold=0ms,jdk.FileWrite#threshold=0ms\
,jdk.SocketRead#threshold=0ms,jdk.SocketWrite#threshold=0ms\
,jdk.JavaMonitorEnter#threshold=0ms,jdk.ThreadSleep#threshold=0ms"

# From the PROBO artifact. JFR truncates stacks at 64 frames by default, and a
# maven -> surefire -> junit stack is deeper than that, so the frame we
# attribute by -- the test's own -- is exactly the one cut off.
JFR_RECORDER_OPTS="-XX:FlightRecorderOptions=stackdepth=1024"

# jfrsort's in-fork listener, built from jfrsort/agent. Its jfrsort.TestClass
# event spans each test class, so an event goes to the class whose window holds
# it, on any thread -- how jfrsort attributes. Only the JUnit Platform (JUnit 5,
# or JUnit 4 through vintage) reaches the listener; without the jar the run
# still profiles and only the windows are missing.
jfr_agent_jar=/otog/aux/jfrsort-agent.jar


# METHODS

jfr_enabled() {
    [ -n "${OTOG_JFR:-}" ] && [ "${OTOG_JFR}" != "false" ] && [ "${OTOG_JFR}" != "0" ]
}

jfr_java_major() {
    # "1.8.0_502" -> 8, "17.0.19" -> 17. Matched on the line containing
    # "version", not line 1: a JAVA_TOOL_OPTIONS already set (ours, once
    # entrypoint.sh exports it for MaxRAM) makes the JVM print a "Picked up
    # JAVA_TOOL_OPTIONS" line first. Two plain substitutions rather than one \?
    # group, which is a GNU sed extension and matches nothing on BSD sed.
    java -version 2>&1 | sed -n '/version "/{s/.*version "//;p;q;}' | sed -e 's/^1\.//' -e 's/[^0-9].*//'
}

jfr_java_flags() {
    # The JVM flags themselves, on stdout. Everything version dependent is here.
    local jfr_dir=$1
    local events=""
    local agent=""

    # jdk.ObjectAllocationSample, the per-event (#) syntax, and the jdk.jfr API
    # the agent's event is built on all arrive in JDK 17. On 8 and 11 the VM
    # refuses to start with them, and there is no allocation-sample event to
    # attribute anyway, so those versions get the plain preset recording.
    if [ "$(jfr_java_major)" -ge 17 ]; then
        events=",$JFR_EVENTS"
        [ -f "$jfr_agent_jar" ] && agent="-javaagent:$jfr_agent_jar "
    fi

    # A directory as filename=, so each JVM writes its own file instead of
    # overwriting one name. They are renamed once the run is over and we know
    # which is which.
    echo "${agent}-XX:StartFlightRecording=settings=${jfr_settings_file}${events}\
,dumponexit=true,filename=$jfr_dir/ $JFR_RECORDER_OPTS"
}

jfr_drop_maven_recording() {
    # Maven's launcher JVM only orchestrates the build -- no test runs in it, so
    # nothing in its recording can be attributed. The mvn script execs the JVM,
    # so the pid we backgrounded IS that JVM's, and JFR names each file after
    # the pid that wrote it.
    #
    # Only when a fork's recording outlives it, though: a project that sets
    # forkCount=0 in its own pom runs the tests inside maven's JVM, and that
    # recording is then the whole run. We never configure forking ourselves.
    local jfr_dir=$1
    local maven_pid=$2

    [ "$(jfr_count "$jfr_dir")" -gt 1 ] && rm -f "$jfr_dir/hotspot-pid-$maven_pid-"*.jfr
    return 0
}

jfr_name_recordings() {
    # PROBO names a recording after what it profiled, not after the pid that
    # happened to write it. The run directory already says which version, order
    # and repetition this is, so the module alone is enough.
    local jfr_dir=$1
    local name=${2//\//_}
    local files=("$jfr_dir"/*.jfr)
    local i

    [ -e "${files[0]}" ] || return 0

    # One fork is the normal case. Several mean the project's own pom sets
    # reuseForks=false; they are numbered only to keep them apart.
    if [ "${#files[@]}" -eq 1 ]; then
        mv -f "${files[0]}" "$jfr_dir/$name.jfr"
        return 0
    fi
    for i in "${!files[@]}"; do
        mv -f "${files[$i]}" "$jfr_dir/$name-$((i + 1)).jfr"
    done
}

jfr_count() {
    find "$1" -name '*.jfr' | wc -l | tr -d ' '
}


# THE PIPELINE

jfr_before_mvn() {
    jfr_enabled || return 0
    local jfr_dir=$1/jfr

    # Fresh, like surefire-reports: a re-run into the same directory must not
    # inherit the last one's recordings.
    rm -rf "$jfr_dir"
    mkdir -p "$jfr_dir"

    # JAVA_TOOL_OPTIONS, not the PROBO artifact's -DargLine: surefire reads
    # argLine as ${argLine}, and jacoco's prepare-agent REWRITES that property
    # mid-build, so a command line -DargLine is silently thrown away on any
    # project that has jacoco -- javaparser among them. The env var is read by
    # the JVM at startup, before any plugin can touch it, and so needs no pom
    # modification anywhere. It reaches maven's own JVM too; that recording is
    # dropped by pid afterwards. Appended, not assigned: the heap sizing the
    # build already put there has to survive profiling.
    jfr_saved_tool_options="${JAVA_TOOL_OPTIONS:-}"
    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:+$jfr_saved_tool_options }$(jfr_java_flags "$jfr_dir")"

    # Timestamped maven lines in UTC turn surefire's "Running <class>" pairs
    # into class windows on the same clock JFR stamps its events with. The
    # fallback wherever the agent's own windows are not there.
    export TZ=UTC
    JFR_MVN_FLAGS=(-Dorg.slf4j.simpleLogger.showDateTime=true
                   "-Dorg.slf4j.simpleLogger.dateTimeFormat=yyyy-MM-dd'T'HH:mm:ss.SSS")

    print_info_message "🔬 JFR on: $JAVA_TOOL_OPTIONS"
}

jfr_after_mvn() {
    jfr_enabled || return 0
    local jfr_dir=$1/jfr
    local maven_pid=$2
    local module=$3

    # Back to the build's own options, heap sizing included.
    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:-}"
    [ -z "$JAVA_TOOL_OPTIONS" ] && unset JAVA_TOOL_OPTIONS
    unset TZ

    jfr_drop_maven_recording "$jfr_dir" "$maven_pid"
    jfr_name_recordings "$jfr_dir" "$module"

    print_info_message "🔬 JFR recordings collected: $(jfr_count "$jfr_dir")"

    # Not fatal, but loud: silently profiling nothing is the failure to catch.
    if [ "$(jfr_count "$jfr_dir")" -eq 0 ]; then
        print_fail_message "⚠️  JFR was requested but produced no recording"
    fi
}
