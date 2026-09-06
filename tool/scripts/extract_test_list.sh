#!/bin/bash

# Get a module's test list WITHOUT running the tests, by reflecting on its
# compiled test classes.
#
#   bash scripts/extract_test_list.sh <project_dir> <module> <out_file>
#
# The counterpart to scripts/get_test_list.py, which reads surefire XML and so
# only works after a full run. This one only needs the module to have been
# COMPILED, which is what makes it usable for generating the very first random
# orders for a version.
#
# CONTAINER-SIDE (or anywhere with the module built): needs mvn, javac and java
# on PATH, and the module's dependencies resolvable.

set -o pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tool_dir=$(cd "$script_dir/.." && pwd)
source "$tool_dir/container/runtime.sh"
source "$tool_dir/config_default.sh"

# Sourcing config resets MVN_OPTS, discarding the flags apply_fixes added for
# this project -- some of which are needed just to RESOLVE. runtime.sh's
# get_test_list() hands them through in OTOG_MVN_OPTS.
MVN_OPTS="${OTOG_MVN_OPTS:-$MVN_OPTS}"

project_dir=$1
module=$2
out_file=$3

if [ -z "$project_dir" ] || [ -z "$module" ] || [ -z "$out_file" ]; then
    print_usage_and_exit \
        "extract_test_list.sh <project_dir> <module> <out_file>" \
        "extract_test_list.sh /work/repo liquibase-standard /out/test_list.txt"
fi

require_command mvn
require_command javac
require_command java

test_classes_dir="$project_dir/$module/target/test-classes"
classes_dir="$project_dir/$module/target/classes"

# Everything we generate lives together so a single rm cleans up after us.
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/otog_reflection.XXXXXX")
classpath_file="$work_dir/classpath.txt"
tool_classes_dir="$work_dir/tool-classes"

trap 'rm -rf "$work_dir"' EXIT


# METHODS

build_classpath() {
    # Reflecting on a class resolves its supertypes and annotations, so the
    # module's whole test classpath has to be present -- otherwise classes fail
    # to load one by one and the list comes out quietly short.
    print_info_message "🛠️ Resolving the test classpath for $module..."

    mvn -q -B dependency:build-classpath \
        -pl "$module" \
        -Dmdep.outputFile="$classpath_file" \
        -Dmdep.includeScope=test \
        $MVN_OPTS \
        -f "$project_dir" > "$work_dir/mvn.log" 2>&1 || {
        print_fail_message "❌ Failed to resolve the classpath. Last lines of $work_dir/mvn.log:"
        tail -n 30 "$work_dir/mvn.log"
        return 1
    }

    if [ ! -s "$classpath_file" ]; then
        print_fail_message "❌ maven produced no classpath file at $classpath_file"
        return 1
    fi

    return 0
}

compile_tool() {
    mkdir -p "$tool_classes_dir"
    javac -d "$tool_classes_dir" "$script_dir/GetTestList.java" 2> "$work_dir/javac.log" || {
        print_fail_message "❌ Failed to compile GetTestList.java:"
        cat "$work_dir/javac.log"
        return 1
    }

    return 0
}

run_tool() {
    local dependency_classpath
    dependency_classpath=$(cat "$classpath_file")

    # The module's own output dirs go first, so its classes win over any shaded
    # copy sitting in a dependency jar.
    local full_classpath="$test_classes_dir:$classes_dir:$dependency_classpath:$tool_classes_dir"

    print_info_message "🔍 Reflecting on the test classes in $test_classes_dir..."

    java -cp "$full_classpath" GetTestList "$test_classes_dir" "$out_file" \
        2> "$work_dir/reflection.log" || {
        print_fail_message "❌ GetTestList failed:"
        tail -n 30 "$work_dir/reflection.log"
        return 1
    }

    # Unloadable classes are the one failure mode that does not stop the run but
    # does corrupt the answer, so surface the warning instead of burying it.
    if grep -q "^WARNING:" "$work_dir/reflection.log"; then
        print_fail_message "🤕 $(grep '^WARNING:' "$work_dir/reflection.log")"
        print_fail_message "🤕 Full detail: $work_dir/reflection.log (kept until this shell exits)"
        trap - EXIT
    fi

    return 0
}


# LOGIC

if [ ! -d "$test_classes_dir" ]; then
    print_fail_message "❌ No compiled test classes at $test_classes_dir"
    print_fail_message "🤕 Compile the module first: mvn install -DskipTests -pl $module -am"
    exit 1
fi

build_classpath || exit 1
compile_tool    || exit 1
run_tool        || exit 1

print_info_message "✅ Test list created: $(wc -l < "$out_file" | tr -d ' ') tests -> $out_file"
exit 0
