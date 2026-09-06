#!/bin/bash
#
# source container/jfr.sh
#
# JFR profiling, sourced by entrypoint.sh. Does nothing unless OTOG_JFR is set,
# so an ordinary run stays comparable with every unprofiled one.
#
# in : OTOG_JFR, OTOG_JFR_SETTINGS (a .jfc name or path)
# out: <out_dir>/jfr/*.jfr

jfr_settings_file="${OTOG_JFR_SETTINGS:-profile}"

# No filename= : JDK 8 will not expand %p, so a fixed name would have maven's
# JVM and the forked surefire JVM overwrite each other.
JFR_OPTIONS="-XX:StartFlightRecording=settings=${jfr_settings_file},dumponexit=true"


jfr_enabled() {
    [ -n "${OTOG_JFR:-}" ] && [ "${OTOG_JFR}" != "false" ] && [ "${OTOG_JFR}" != "0" ]
}

jfr_before_mvn() {
    jfr_enabled || return 0

    # JAVA_TOOL_OPTIONS, not -DargLine: argLine is already used for heap sizing
    # and a second one on the command line would silently drop it.
    export JAVA_TOOL_OPTIONS="$JFR_OPTIONS"

    # Timestamped maven lines in UTC turn surefire's "Running <class>" pairs
    # into class windows on the same clock JFR stamps its events with. Nothing
    # else gives that timeline.
    export TZ=UTC
    JFR_MVN_FLAGS=(-Dorg.slf4j.simpleLogger.showDateTime=true
                   "-Dorg.slf4j.simpleLogger.dateTimeFormat=yyyy-MM-dd'T'HH:mm:ss.SSS")

    print_info_message "🔬 JFR on: $JAVA_TOOL_OPTIONS"
}

jfr_after_mvn() {
    jfr_enabled || return 0
    local repo_dir=$1 out_dir=$2

    unset JAVA_TOOL_OPTIONS TZ

    mkdir -p "$out_dir/jfr"
    find "$repo_dir" -name 'hotspot-pid-*.jfr' -exec mv {} "$out_dir/jfr/" \; 2> /dev/null

    local count
    count=$(find "$out_dir/jfr" -name '*.jfr' | wc -l | tr -d ' ')
    print_info_message "🔬 JFR recordings collected: $count"

    # Not fatal, but loud: silently profiling nothing is the failure to catch.
    if [ "$count" -eq 0 ]; then
        print_fail_message "⚠️  JFR was requested but produced no recording"
    fi
}
