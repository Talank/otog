#!/bin/bash
#
# usage: source /otog/container/runtime.sh
# e.g.   source /otog/container/runtime.sh; write_status /out PASS
#
# What the container needs, the way lib.sh serves the host. Sourced by
# entrypoint.sh and by scripts/extract_test_list.sh.
#
# in : $tool_dir, and $out_dir for the callers that write there
# out: write_status, get_test_list, remove_known_flaky_tests,
#      remove_known_hanging_tests, check_if_run_passed


# ------------------------------------------------------------------ messages

# On unless config turns them off: defaulting to off once hid every diagnostic.
print_info_message() {
    [ "${print_info:-true}" = true ] && echo "$1"
    return 0
}

print_fail_message() {
    [ "${print_fail:-true}" = true ] && echo "$1"
    return 0
}

# The first line of every run log: what is being built, and when.
print_snapshot_message() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

print_usage_and_exit() {
    print_fail_message "error: usage: $1"
    [ -n "$2" ] && print_fail_message "       e.g.   $2"
    exit 2
}

require_command() {
    if ! command -v "$1" > /dev/null 2>&1; then
        print_fail_message "error: $1 is not installed or not on PATH"
        exit 1
    fi
}


# -------------------------------------------------------------------- status

# Line 1 is the verdict every reader compares against PASS; line 2 is the tool sha.
write_status() {
    local out_dir=$1
    local verdict=$2

    mkdir -p "$out_dir"
    echo "$verdict" > "$out_dir/status"
    [ -n "${OTOG_TOOL_SHA:-}" ] && echo "$OTOG_TOOL_SHA" >> "$out_dir/status"
    return 0
}


# ----------------------------------------------------------------- test list

# The module's test list, by reflecting on its compiled test classes.
get_test_list() {
    local project_dir=$1
    local module=$2
    local test_list_file=$3

    mkdir -p "$(dirname "$test_list_file")"

    # OTOG_MVN_OPTS carries the flags apply_fixes added; the wrapper re-sources
    # config and would otherwise throw them away.
    OTOG_MVN_OPTS="$MVN_OPTS" \
        bash "$tool_dir/scripts/extract_test_list.sh" \
            "$project_dir" "$module" "$test_list_file" || {
        print_fail_message "error: could not extract the test list from $project_dir/$module"
        return 1
    }

    apply_test_list_exclusions "$test_list_file"
    return 0
}

# Drop tests reflection reports but surefire's own includes/excludes would not run.
apply_test_list_exclusions() {
    local test_list_file=$1

    if [ -z "${test_list_exclude_pattern:-}" ]; then
        return 0
    fi

    print_info_message "dropping excluded tests: $test_list_exclude_pattern"
    grep -Ev "$test_list_exclude_pattern" "$test_list_file" > "$test_list_file.filtered"
    mv "$test_list_file.filtered" "$test_list_file"

    print_info_message "test list after exclusions: $(wc -l < "$test_list_file" | tr -d ' ') tests"
    return 0
}

# Remove this project's known flaky tests, from the LIST, before any order exists.
remove_known_flaky_tests() {
    local test_list_file=$1
    local slug=$2

    local flaky_csv="${idoft_flaky_tests_csv:-$tool_dir/data/idoft_flaky_tests.csv}"

    if [ -z "$slug" ]; then
        print_fail_message "error: remove_known_flaky_tests needs a slug (owner/repo)"
        return 1
    fi

    if [ ! -f "$flaky_csv" ]; then
        print_fail_message "error: IDoFT dataset not found at $flaky_csv"
        return 1
    fi

    local before after
    before=$(wc -l < "$test_list_file" | tr -d ' ')

    awk -F',' -v slug="$slug" -v categories="${flaky_categories_to_remove:-}" '
        function normalize(name) {
            gsub(/\[[^]]*\]/, "", name)          # parameterized suffix
            gsub(/^[ \t\r]+|[ \t\r]+$/, "", name)
            return name
        }

        # pass 1: build the flaky set from the IDoFT csv
        NR == FNR {
            if (FNR == 1) next

            url = $1
            sub(/^.*github\.com\//, "", url)
            sub(/\.git$/, "", url)
            sub(/\/+$/, "", url)
            if (tolower(url) != tolower(slug)) next

            # A few rows have a comma inside the test name, which shifts every
            # later field. Require field 4 to LOOK like a fully qualified name
            # rather than writing a CSV parser.
            name = normalize($4)
            if (name !~ /^[A-Za-z_$][A-Za-z0-9_.$]*\.[A-Za-z_$][A-Za-z0-9_$]*$/) next

            if (categories != "" && index(categories, $5) == 0) next

            # last dot becomes the # separating class from method.
            i = length(name)
            while (i > 0 && substr(name, i, 1) != ".") i--
            if (i < 2) next

            flaky[substr(name, 1, i - 1) "#" substr(name, i + 1)] = 1
            next
        }

        # pass 2: filter the test list
        {
            if (normalize($0) in flaky) next
            print
        }
    ' "$flaky_csv" "$test_list_file" > "$test_list_file.deflaked" || {
        print_fail_message "error: could not filter flaky tests out of $test_list_file"
        rm -f "$test_list_file.deflaked"
        return 1
    }

    mv "$test_list_file.deflaked" "$test_list_file"
    after=$(wc -l < "$test_list_file" | tr -d ' ')

    if [ "$before" -eq "$after" ]; then
        print_info_message "no known flaky tests for $slug in this list ($after tests)"
    else
        print_info_message "removed $((before - after)) known flaky test(s) for $slug: $before -> $after tests"
    fi

    return 0
}

# --------------------------------------------------------------- hanging tests

# Drop the tests that hang here, setting $effective_order_file to what runs.
remove_known_hanging_tests() {
    local order_file=$1
    local slug=$2
    local module=$3
    local version=$4
    local out_dir=$5

    local csv="${hanging_tests_csv:-$tool_dir/data/hanging_tests.csv}"

    # Always defined, so a caller can use it unconditionally.
    effective_order_file="$order_file"

    # Written even when empty: the test set a run used is then a fact on disk,
    # not something re-derived later from a csv that has moved on since.
    : > "$out_dir/removed_tests.txt"

    [ -f "$csv" ] || return 0

    awk -F',' -v slug="$slug" -v module="$module" -v version="$version" \
        -v removed="$out_dir/removed_tests.txt" '
        # pass 1: what does the registry say hangs in this module-version?
        NR == FNR {
            if (FNR == 1) next
            if ($1 != slug || $2 != module) next
            if ($5 != "active") next

            # "*" is every version of this module -- the consistent removal.
            # Anything else is a version list, which removes the test from
            # those versions only and leaves them incomparable to the rest.
            if ($3 == "*") { drop[$4] = 1; next }

            n = split($3, want, " ")
            for (i = 1; i <= n; i++)
                if (want[i] == version) { drop[$4] = 1; break }
            next
        }

        # pass 2: filter the order, recording what went
        {
            hash = index($0, "#")
            cls = hash ? substr($0, 1, hash - 1) : $0
            if ($0 in drop || cls in drop) { print > removed; next }
            print
        }
    ' "$csv" "$order_file" > "$out_dir/order_effective.txt" || {
        print_fail_message "error: could not filter hanging tests out of $order_file"
        rm -f "$out_dir/order_effective.txt"
        return 1
    }

    local dropped
    dropped=$(wc -l < "$out_dir/removed_tests.txt" | tr -d ' ')

    if [ "$dropped" -eq 0 ]; then
        rm -f "$out_dir/order_effective.txt"
        print_info_message "no active hanging tests for $slug :: $module at version $version"
        return 0
    fi

    if [ ! -s "$out_dir/order_effective.txt" ]; then
        print_fail_message "error: removing hanging tests left the order empty"
        rm -f "$out_dir/order_effective.txt"
        return 1
    fi

    effective_order_file="$out_dir/order_effective.txt"
    print_info_message "removed $dropped hanging test(s): $(wc -l < "$order_file" | tr -d ' ') -> $(wc -l < "$effective_order_file" | tr -d ' ') tests"
    return 0
}


# ------------------------------------------------------------------- verdict

# Did this run produce usable data? Maven reached the end, and there are XMLs.
check_if_run_passed() {
    local reports_dir=$1
    local log_file=$2

    # fix_helper.sh sets this for the versions whose build never reports BUILD
    # SUCCESS but still produces a usable test run.
    if [ "${tolerate_failure:-false}" = true ]; then
        print_info_message "tolerate_failure is set for this project, accepting the run as-is"
        return 0
    fi

    if [ ! -d "$reports_dir" ] || [ ! -f "$log_file" ]; then
        print_fail_message "error: no log file or no surefire reports"
        return 1
    fi

    # Ask for the evidence, not for a verbose log: TestNG prints one
    # "Running TestSuite" line for a whole run.
    if ! grep -q "Tests run: [1-9]" "$log_file"; then
        print_fail_message "error: the log has no test results at all"
        return 1
    fi

    # Not anchored at the start of the line: a profiled run asks maven for
    # timestamped output so JFR events can be placed on a timeline.
    if ! tail -n 30 "$log_file" | grep -Eq '\[INFO\][[:space:]]*BUILD[[:space:]]+SUCCESS[[:space:]]*$' && \
         tail -n 10 "$log_file" | grep -q "\[ERROR\]"; then
        print_fail_message "error: no BUILD SUCCESS, and [ERROR] in the last lines of the log"
        return 1
    fi

    if [ "$(find "$reports_dir" -maxdepth 1 -name 'TEST-*.xml' | wc -l)" -gt 0 ]; then
        print_info_message "build succeeded and there are surefire reports in $reports_dir"
        return 0
    fi

    print_fail_message "error: no surefire reports found in $reports_dir"
    return 1
}
