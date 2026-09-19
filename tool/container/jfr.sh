#!/bin/bash
#
# usage: source container/jfr.sh
# e.g.   source container/jfr.sh; jfr_before_mvn /out
#
# JFR profiling for entrypoint.sh; does nothing unless OTOG_JFR is set.
# What it records and why: docs/design.md, "JFR".

jfr_settings_file="${OTOG_JFR_SETTINGS:-profile}"

# The event settings behind the metrics of jfrsort and of PROBO, applied to a
# copy of the preset. One rule per line: event|setting=value. The two TLAB
# events give the allocation of each test class; they exist on every JDK from
# 8 on, and a settings file is the one form every JDK accepts. The sample
# event of JDK 16 and later is turned off so that allocation is counted once.
JFR_EVENT_RULES="jdk.ObjectAllocationInNewTLAB|enabled=true
jdk.ObjectAllocationInNewTLAB|stackTrace=false
jdk.ObjectAllocationOutsideTLAB|enabled=true
jdk.ObjectAllocationOutsideTLAB|stackTrace=false
jdk.ObjectAllocationSample|enabled=false
jdk.Compilation|threshold=0 ms
jdk.ClassLoad|enabled=true
jdk.FileRead|threshold=0 ms
jdk.FileWrite|threshold=0 ms
jdk.SocketRead|threshold=0 ms
jdk.SocketWrite|threshold=0 ms
jdk.JavaMonitorEnter|threshold=0 ms
jdk.ThreadSleep|threshold=0 ms"

# The test-window agent that jfrsort attributes events with. Built for JDK 8,
# so it loads on every JDK the containers use.
jfr_agent_jar=/otog/aux/jfrsort-agent.jar


# METHODS

jfr_enabled() {
    [ -n "${OTOG_JFR:-}" ] && [ "${OTOG_JFR}" != "false" ] && [ "${OTOG_JFR}" != "0" ]
}

# The JDK's major version, from either the 1.8 or the modern format.
jfr_java_major() {
    java -version 2>&1 | sed -n '/version "/{s/.*version "//;p;q;}' | sed -e 's/^1\.//' -e 's/[^0-9].*//'
}

# The directory that holds the JVM's own preset files, default.jfc and profile.jfc.
jfr_preset_dir() {
    local home=${JAVA_HOME:-}
    if [ -z "$home" ]; then
        home=$(command -v java) || return 1
        home=$(readlink -f "$home")
        home=$(dirname "$(dirname "$home")")
    fi
    if [ -d "$home/lib/jfr" ]; then
        printf '%s' "$home/lib/jfr"
    elif [ -d "$home/jre/lib/jfr" ]; then
        printf '%s' "$home/jre/lib/jfr"
    else
        return 1
    fi
}

# OTOG_JFR_SETTINGS is a preset name or a path to a .jfc file.
jfr_preset_file() {
    case "$jfr_settings_file" in
        */*|*.jfc) printf '%s' "$jfr_settings_file" ;;
        *)         printf '%s/%s.jfc' "$(jfr_preset_dir)" "$jfr_settings_file" ;;
    esac
}

# Write a copy of the preset with JFR_EVENT_RULES applied, and print its path.
jfr_write_settings() {
    local out=$1/otog.jfc
    local preset
    preset=$(jfr_preset_file) || return 1
    [ -f "$preset" ] || { print_fail_message "jfr: no preset file at $preset"; return 1; }

    # One line per rule here; awk on macOS takes no newline in -v.
    awk -v rules="$(printf '%s' "$JFR_EVENT_RULES" | tr '\n' ';')" '
        BEGIN {
            n = split(rules, lines, ";")
            for (i = 1; i <= n; i++) {
                split(lines[i], parts, "|"); split(parts[2], kv, "=")
                want[parts[1] "|" kv[1]] = kv[2]
            }
        }
        /<event name="/ { match($0, /name="[^"]*"/); event = substr($0, RSTART + 6, RLENGTH - 7) }
        /<\/event>/ { event = "" }
        event != "" && /<setting name="/ {
            match($0, /<setting name="[^"]*"/); setting = substr($0, RSTART + 15, RLENGTH - 16)
            key = event "|" setting
            if (key in want) sub(/>[^<]*<\/setting>/, ">" want[key] "</setting>")
        }
        { print }
    ' "$preset" > "$out" || return 1
    printf '%s' "$out"
}

# The JAVA_TOOL_OPTIONS that turn recording on for every JVM the build starts.
jfr_java_flags() {
    local jfr_dir=$1
    local agent="" settings

    [ -f "$jfr_agent_jar" ] && agent="-javaagent:$jfr_agent_jar "
    settings=$(jfr_write_settings "$jfr_dir") || return 1

    # Each JVM writes one file and finalizes it on exit.
    echo "${agent}-XX:StartFlightRecording=settings=${settings},dumponexit=true,filename=$jfr_dir/"
}

# Drop maven's own recording when a separate test JVM produced one too.
jfr_drop_maven_recording() {
    local jfr_dir=$1
    local maven_pid=$2

    [ "$(jfr_count "$jfr_dir")" -gt 1 ] && rm -f "$jfr_dir/hotspot-pid-$maven_pid-"*.jfr
    return 0
}

# Name the recordings after the module, keeping every test-fork recording.
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

# Turn recording on, and timestamp maven's output so events can be attributed.
jfr_before_mvn() {
    jfr_enabled || return 0
    local jfr_dir=$1/jfr

    # Timestamps turn surefire's "Running <class>" / "Tests run: ... - in
    # <class>" pairs into class windows on JFR's own clock, a check on the
    # windows the agent records.
    export TZ=UTC
    MVN_OPTS="$MVN_OPTS -Dorg.slf4j.simpleLogger.showDateTime=true"
    MVN_OPTS="$MVN_OPTS -Dorg.slf4j.simpleLogger.dateTimeFormat=yyyy-MM-dd'T'HH:mm:ss.SSS"

    rm -rf "$jfr_dir"
    mkdir -p "$jfr_dir"

    local flags
    flags=$(jfr_java_flags "$jfr_dir") || {
        print_fail_message "error: jfr was requested but its settings could not be written"
        return 1
    }

    # The startup environment, so maven and surefire both inherit it.
    jfr_saved_tool_options="${JAVA_TOOL_OPTIONS:-}"
    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:+$jfr_saved_tool_options }$flags"

    print_info_message "jfr: on -- $JAVA_TOOL_OPTIONS"
}

# Put the environment back, then keep one named recording per test JVM.
jfr_after_mvn() {
    jfr_enabled || return 0
    local jfr_dir=$1/jfr
    local maven_pid=$2
    local module=$3

    export JAVA_TOOL_OPTIONS="${jfr_saved_tool_options:-}"
    [ -z "$JAVA_TOOL_OPTIONS" ] && unset JAVA_TOOL_OPTIONS
    jfr_drop_maven_recording "$jfr_dir" "$maven_pid"
    jfr_name_recordings "$jfr_dir" "$module"

    print_info_message "jfr: $(jfr_count "$jfr_dir") recording(s) collected"

    if [ "$(jfr_count "$jfr_dir")" -eq 0 ]; then
        print_fail_message "warning: jfr was requested but produced no recording"
    fi
}
