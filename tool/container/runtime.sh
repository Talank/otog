#
# source /otog/container/runtime.sh
#
# Functions the container needs, taken from the helpers.sh that produced the
# existing dataset. Host-side code uses lib.sh instead.
#
# Moving a function out of here means checking every caller: tests/
# test_shell_symbols.py exists because that split dropped several silently.
#
# in : $out_dir, a built maven module
# out: write_status, get_test_list, remove_known_flaky_tests, check_if_run_passed


write_status() {
    # "run_status", not "status": zsh makes $status a read-only builtin, and
    # these helpers get sourced by hand in a shell often enough to matter.
    local out_dir=$1
    local run_status=$2

    mkdir -p "$out_dir"
    # The status first -- readers take line 1 -- then which version of the tool
    # produced it. A run whose code cannot be identified cannot be reproduced.
    echo "$run_status" > "$out_dir/status"
    [ -n "${OTOG_TOOL_SHA:-}" ] && echo "$OTOG_TOOL_SHA" >> "$out_dir/status"
    return 0
}

read_status() {
    local out_dir=$1

    if [ -f "$out_dir/status" ]; then
        cat "$out_dir/status"
    else
        echo "NOT_RUN"
    fi
}

get_test_list() {
    # The DEFAULT way to get a test list: reflect on the module's compiled test
    # classes. Only the module has to be compiled -- the suite never runs.
    local project_dir=$1
    local module=$2
    local test_list_file=$3

    mkdir -p "$(dirname "$test_list_file")"

    # The wrapper re-sources config for its own use, which would otherwise throw
    # away anything apply_fixes added to MVN_OPTS (the SSL and proxy flags some
    # projects need just to RESOLVE, never mind compile).
    OTOG_MVN_OPTS="$MVN_OPTS" \
        bash "$tool_dir/scripts/extract_test_list.sh" \
            "$project_dir" "$module" "$test_list_file" || {
        print_fail_message "❌ Failed to extract the test list by reflection from $project_dir/$module"
        return 1
    }

    apply_test_list_exclusions "$test_list_file"
    return 0
}

get_test_list_using_surefire_xml() {
    # surefire XMLs -> the executed test list, "pkg.Class#method" per line, in
    # execution order. Test lists now come from reflection instead.
    local surefire_dir=$1
    local test_list_file=$2

    mkdir -p "$(dirname "$test_list_file")"

    python3 "$tool_dir/scripts/get_test_list.py" "$surefire_dir" "$test_list_file" || {
        print_fail_message "❌ Failed to extract the test list from $surefire_dir"
        return 1
    }

    apply_test_list_exclusions "$test_list_file"
    return 0
}

apply_test_list_exclusions() {
    # Reflection reports every test a class DECLARES, while surefire only runs
    # what its includes/excludes allow, most visibly the *IT integration tests.
    local test_list_file=$1

    if [ -z "${test_list_exclude_pattern:-}" ]; then
        return 0
    fi

    print_info_message "🧹 Dropping excluded tests: $test_list_exclude_pattern"
    grep -Ev "$test_list_exclude_pattern" "$test_list_file" > "$test_list_file.filtered"
    mv "$test_list_file.filtered" "$test_list_file"

    print_info_message "✅ Test list after exclusions: $(wc -l < "$test_list_file" | tr -d ' ') tests"
    return 0
}

remove_known_flaky_tests() {
    #   remove_known_flaky_tests <test_list_file> <slug>
    local test_list_file=$1
    local slug=$2

    local flaky_csv="${idoft_flaky_tests_csv:-$tool_dir/data/idoft_flaky_tests.csv}"

    if [ -z "$slug" ]; then
        print_fail_message "❌ remove_known_flaky_tests needs a slug (owner/repo)"
        return 1
    fi

    if [ ! -f "$flaky_csv" ]; then
        print_fail_message "❌ IDoFT dataset not found at $flaky_csv"
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

        # ---- pass 1: build the flaky set from the IDoFT csv
        NR == FNR {
            if (FNR == 1) next

            url = $1
            sub(/^.*github\.com\//, "", url)
            sub(/\.git$/, "", url)
            sub(/\/+$/, "", url)
            if (tolower(url) != tolower(slug)) next

            # A handful of rows have a comma inside the test name, which shifts
            # every later field. Rather than write a CSV parser, require field 4
            # to LOOK like a fully qualified name and skip it when it does not.
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

        # ---- pass 2: filter the test list
        {
            if (normalize($0) in flaky) next
            print
        }
    ' "$flaky_csv" "$test_list_file" > "$test_list_file.deflaked" || {
        print_fail_message "❌ Failed to filter flaky tests out of $test_list_file"
        rm -f "$test_list_file.deflaked"
        return 1
    }

    mv "$test_list_file.deflaked" "$test_list_file"
    after=$(wc -l < "$test_list_file" | tr -d ' ')

    if [ "$before" -eq "$after" ]; then
        print_info_message "🔍 No known flaky tests for $slug in this list ($after tests)"
    else
        print_info_message "🧹 Removed $((before - after)) known flaky test(s) for $slug: $before -> $after tests"
    fi

    return 0
}

check_if_run_passed() {
    # Did this run produce usable data? Two things have to be true: maven
    # reached the end without erroring out, and there are actually surefire
    # XMLs to parse.
    local runs_dir=$1   # where the TEST-*.xml were collected
    local log_file=$2   # the maven log for that same run

    # fix_helper.sh sets this for the handful of (project, sha) pairs where the
    # build never reports BUILD SUCCESS but still produces a usable test run.
    if [ "${tolerate_failure:-false}" = true ]; then
        print_info_message "🤖 tolerate_failure is set for this project, accepting the run as-is"
        return 0
    fi

    print_info_message "🔍 Checking if the run was successful or not..."

    if [ ! -d "$runs_dir" ] || [ ! -f "$log_file" ]; then
        print_fail_message "🤕 ❌ Log file or the surefire reports not found."
        return 1
    fi

    # Did the run actually reach the tests? Ask for the evidence rather than for
    # a verbose log: TestNG prints one "Running TestSuite" line for the whole run.
    if ! grep -q "Tests run: [1-9]" "$log_file"; then
        print_fail_message "🤕 ❌ The log has no test results at all."
        return 1
    fi

    # NOT anchored at the start of the line: a profiled run asks maven for
    # timestamped output so JFR events can be placed on a timeline.
    if ! tail -n 30 "$log_file" | grep -Eq '\[INFO\][[:space:]]*BUILD[[:space:]]+SUCCESS[[:space:]]*$' && \
         tail -n 10 "$log_file" | grep -q "\[ERROR\]"; then
        print_fail_message "🤕 ❌ No BUILD SUCCESS, and [ERROR] in the last lines of the log."
        return 1
    fi

    if [ "$(find "$runs_dir" -maxdepth 1 -name 'TEST-*.xml' | wc -l)" -gt 0 ]; then
        print_info_message "🤖 ✅ Build succeeded and there are surefire reports in $runs_dir"
        return 0
    fi

    print_fail_message "🤕 ❌ No surefire reports found in $runs_dir."
    return 1
}

check_if_run_all_tests() {
    # A run can report BUILD SUCCESS and still be truncated by a fork crash, so
    # the test count is checked too.
    local test_list=$1
    local surefire_report_dir=$2

    local expected_tests executed_tests temp_tests_file

    expected_tests=$(wc -l < "$test_list" | tr -d ' ')
    temp_tests_file=$(mktemp "${TMPDIR:-/tmp}/otog_test_list.XXXXXX")

    get_test_list_using_surefire_xml "$surefire_report_dir" "$temp_tests_file" || {
        rm -f "$temp_tests_file"
        return 1
    }

    executed_tests=$(wc -l < "$temp_tests_file" | tr -d ' ')
    rm -f "$temp_tests_file"

    if [ "$expected_tests" -eq "$executed_tests" ]; then
        print_info_message "🤖 ✅ All $expected_tests tests were executed"
        return 0
    fi

    print_fail_message "🤕 ❌ Not all tests were executed. Expected: $expected_tests, Executed: $executed_tests"
    return 1
}

# On unless config turns them off. Defaulting to off once made every
# diagnostic in the container disappear, which is the worst way to find out.
print_info_message() {
    [ "${print_info:-true}" = true ] && echo "$1"
    return 0
}

print_fail_message() {
    [ "${print_fail:-true}" = true ] && echo "$1"
    return 0
}

print_snapshot_message() {
    # The first line of every run log: what is being built, and when.
    local message=$1

    echo "🧹 [$(date +'%Y-%m-%d %H:%M:%S')] $message"
}

print_usage_and_exit() {
    local usage=$1
    local example=$2

    print_fail_message "❌ usage: $usage"
    [ -n "$example" ] && print_fail_message "        e.g. $example"
    exit 2
}

require_command() {
    local command_name=$1

    if ! command -v "$command_name" &> /dev/null; then
        print_fail_message "❌ $command_name is not installed or not on PATH"
        exit 1
    fi
}
