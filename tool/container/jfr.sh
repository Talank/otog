#!/bin/bash
#
# source container/jfr.sh
#
# JFR profiling for entrypoint.sh; enabled only when OTOG_JFR is set.

jfr_settings_file="${OTOG_JFR_SETTINGS:-profile}"

# Extra events required by jfrsort and other metrics used by PROBO.
JFR_EVENTS="jdk.ObjectAllocationSample#throttle=1000/s\
,jdk.Compilation#threshold=0ms,jdk.ClassLoad#enabled=true\
,jdk.FileRead#threshold=0ms,jdk.FileWrite#threshold=0ms\
,jdk.SocketRead#threshold=0ms,jdk.SocketWrite#threshold=0ms\
,jdk.JavaMonitorEnter#threshold=0ms,jdk.ThreadSleep#threshold=0ms"

# Optional JUnit test-window agent used by jfrsort.
jfr_agent_jar=/otog/aux/jfrsort-agent.jar


# METHODS

jfr_enabled() {
    [ -n "${OTOG_JFR:-}" ] && [ "${OTOG_JFR}" != "false" ] && [ "${OTOG_JFR}" != "0" ]
}

jfr_java_major() {
    # Handle both legacy (1.8) and modern version formats.
    java -version 2>&1 | sed -n '/version "/{s/.*version "//;p;q;}' | sed -e 's/^1\.//' -e 's/[^0-9].*//'
}

jfr_java_flags() {
    local jfr_dir=$1
    local jfrsort_agent_option=""
    local events=""

    # Custom events and test windows require JDK 17+.
    if [ "$(jfr_java_major)" -ge 17 ]; then
        events=",$JFR_EVENTS"
        [ -f "$jfr_agent_jar" ] && jfrsort_agent_option="-javaagent:$jfr_agent_jar "
    fi

    # Each JVM writes one file and finalizes it on exit.
    echo "${jfrsort_agent_option}-XX:StartFlightRecording=settings=${jfr_settings_file}${events},dumponexit=true,filename=$jfr_dir/"
}

jfr_drop_maven_recording() {
    # Drop Maven's file when a separate test JVM exists.
    local jfr_dir=$1
    local maven_pid=$2

    [ "$(jfr_count "$jfr_dir")" -gt 1 ] && rm -f "$jfr_dir/hotspot-pid-$maven_pid-"*.jfr
    return 0
}

jfr_name_recordings() {
    local jfr_dir=$1
    local name=${2//\//_}
    local files=("$jfr_dir"/*.jfr)
    local i

    [ -e "${files[0]}" ] || return 0

    # Preserve multiple test-fork recordings.
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

    # An absolute timestamp on every maven line, in UTC. Surefire prints
    # "Running <class>" when a class starts and "Tests run: ... - in <class>"
    # when it ends; with timestamps those pairs become exact class windows on
    # the same clock JFR stamps its events with, which is what makes an event
    # attributable to the test class that caused it.
    #
    # The jfrsort agent supplies the same windows more precisely, but only on
    # JDK 17+, and NINE of the sixteen modules build on java 8. Without this
    # their recordings have no class attribution at all -- and nothing else can
    # supply it: the surefire XMLs are all flushed in the same moment at the end
    # of a run, jdk.ClassLoad never fires for the test classes themselves, and
    # jdk.ExecutionSample names a suite class in about 15% of its samples.
    export TZ=UTC
    MVN_OPTS="$MVN_OPTS -Dorg.slf4j.simpleLogger.showDateTime=true"
    MVN_OPTS="$MVN_OPTS -Dorg.slf4j.simpleLogger.dateTimeFormat=yyyy-MM-dd'T'HH:mm:ss.SSS"

    # Start clean.
    rm -rf "$jfr_dir"
    mkdir -p "$jfr_dir"

    # Use the startup environment so Maven and Surefire inherit it.
    jfr_saved_tool_options="${JAVA_TOOL_OPTIONS:-}"
    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:+$jfr_saved_tool_options }$(jfr_java_flags "$jfr_dir")"

    print_info_message "🔬 JFR on: $JAVA_TOOL_OPTIONS"
}

jfr_after_mvn() {
    jfr_enabled || return 0
    local jfr_dir=$1/jfr
    local maven_pid=$2
    local module=$3

    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:-}"
    [ -z "$JAVA_TOOL_OPTIONS" ] && unset JAVA_TOOL_OPTIONS
    jfr_drop_maven_recording "$jfr_dir" "$maven_pid"
    jfr_name_recordings "$jfr_dir" "$module"

    print_info_message "🔬 JFR recordings collected: $(jfr_count "$jfr_dir")"

    if [ "$(jfr_count "$jfr_dir")" -eq 0 ]; then
        print_fail_message "⚠️  JFR was requested but produced no recording"
    fi
}
