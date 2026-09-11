#!/bin/bash
#
# bash /otog/container/entrypoint.sh          # run_once.sh starts this
#
# Runs INSIDE the container: clone, checkout, fix, build, then either extract
# the test list or run one order.
#
# in : SLUG, MODULE, SHA, and ORDER_FILE when there is an order to run
# out: /out/status, wall_time.txt, mvn.log, surefire-reports/

set -o pipefail

tool_dir=/otog
source "$tool_dir/container/runtime.sh"
source "$tool_dir/config_default.sh"
source "$tool_dir/fix_helper.sh"

# Everything JFR does lives here, and it does nothing unless the run was started
# with --jfr. One file to edit to change what is profiled.
source "$tool_dir/container/jfr.sh"

slug=${SLUG:?SLUG is required}
module=${MODULE:?MODULE is required}
sha=${SHA:?SHA is required}
order_file=${ORDER_FILE:-}

repo_dir="$container_repo_dir"
out_dir="$container_out_dir"

# Fix strategies append to this; every mvn call below picks it up.
# Seeded from OTOG_MVN_EXTRA_OPTS so a caller can inject flags without
# editing config; empty when unset, which is the historical behaviour.
MVN_EXTRA_OPTS="${OTOG_MVN_EXTRA_OPTS:-}"

# -Dmaven.repo.local is explicit because HOME is NOT /root here: apptainer runs
# as the invoking user, so maven's default $HOME/.m2 would be the empty
# per-workspace home and every job would re-download.
MVN_OPTS="$MVN_OPTS $maven_shared_repo_opts -Dmaven.repo.local=$container_m2_dir"

# Reaches every JVM the build starts, surefire's fork included. Not -DargLine:
# jacoco's prepare-agent rewrites that property mid-build and the flag is
# silently lost. No -Xmx here, so a fork that DID receive the argLine keeps
# exactly the heap it was given; this only sizes the ones that did not.
#
# MaxRAM on its own is not enough: the JVM still takes a FRACTION of it, 25% by
# default, so a fork would get 4g of a 16g container. The flag that says "all of
# it" was renamed in JDK 10, and the wrong one is fatal rather than ignored --
# java 8 answers MaxRAMPercentage with "Could not create the Java Virtual
# Machine" and the run dies before maven starts. Measured, both ways: 4.00g with
# MaxRAM alone, 16.00g with the matching share flag, on 8 and on 17.
if [ -n "$otog_jvm_max_ram" ]; then
    java_major=$(java -version 2>&1 | sed -n '/version "/{s/.*version "//;s/^1\.//;s/[^0-9].*//;p;q;}')
    if [ "${java_major:-8}" -ge 10 ] 2> /dev/null; then
        heap_share=-XX:MaxRAMPercentage=100
    else
        heap_share=-XX:MaxRAMFraction=1
    fi
    export JAVA_TOOL_OPTIONS="-XX:MaxRAM=$otog_jvm_max_ram $heap_share"
fi


# METHODS

seed_local_repo() {
    # Fill this lane's private repository from the shared one, once.
    local marker="$container_m2_dir/.otog_seeded"

    if [ -f "$marker" ]; then
        return 0
    fi

    if [ ! -d "$container_m2_shared_dir" ]; then
        print_info_message "ℹ️ No shared repo at $container_m2_shared_dir -- starting with an empty one"
        mkdir -p "$container_m2_dir"
        touch "$marker"
        return 0
    fi

    print_info_message "📦 Seeding $container_m2_dir from $container_m2_shared_dir"
    mkdir -p "$container_m2_dir" || return 1

    # tar rather than cp -r: this is ~100k small files over NFS, and the stream
    # keeps it to one pass with no per-file stat storm on the target.
    local extracted=true
    set +o pipefail
    (cd "$container_m2_shared_dir" && tar -cf - .) 2> /dev/null \
        | (cd "$container_m2_dir" && tar -xf -) || extracted=false
    set -o pipefail

    if [ "$extracted" = false ]; then
        print_fail_message "❌ Could not seed the local maven repository"
        return 1
    fi

    # The one artifact whose absence would not show up until an order run
    # failed: the surefire fork that -Dmaven.ext.class.path forces on every build.
    if [ ! -d "$container_m2_dir/org/apache/maven/plugins/maven-surefire-plugin/$surefire_fork_version" ]; then
        print_fail_message "❌ Seeded repo has no maven-surefire-plugin:$surefire_fork_version"
        print_fail_message "   Run setup.sh on the login node, then retry"
        return 1
    fi

    touch "$marker"
    print_info_message "✅ Local maven repository ready ($(du -sh "$container_m2_dir" 2> /dev/null | cut -f1))"
    return 0
}

workspace_is_ready() {
    # True when this workspace already holds the right commit, built. Only the
    # first unit for a version pays the clone and the compile.
    [ -d "$repo_dir/.git" ] || return 1
    [ "$(git -C "$repo_dir" rev-parse HEAD 2> /dev/null)" = "$sha" ] || return 1
    [ -d "$repo_dir/$module/target/test-classes" ] || return 1

    return 0
}

fetch_sha() {
    # Fetch one commit, with retries, and SAY WHY when it does not work. What
    # this hits is transient -- many jobs cloning one big repo at once.
    local attempt
    local wait_seconds=5

    for attempt in 1 2 3 4; do
        if git fetch --quiet --depth 1 origin "$sha" 2> "$out_dir/git.log"; then
            return 0
        fi

        # Some servers refuse a bare sha; that is not transient, so try the
        # whole repo once in the same attempt rather than burning a retry.
        print_info_message "⬇️ Shallow fetch failed (attempt $attempt), trying the whole repo"
        if git fetch --quiet origin 2>> "$out_dir/git.log"; then
            return 0
        fi

        if [ "$attempt" -lt 4 ]; then
            print_info_message "⏳ Retrying the fetch in ${wait_seconds}s"
            sleep "$wait_seconds"
            wait_seconds=$((wait_seconds * 3))
        fi
    done

    print_fail_message "❌ Failed to fetch $sha from $slug after 4 attempts. git said:"
    tail -n 8 "$out_dir/git.log" 2> /dev/null | sed 's/^/     /'
    return 1
}

clone_and_checkout() {
    # Fetch ONLY this one commit, with no history. A full clone of a big repo
    # costs ~40s and a few hundred MB, and across a 2010-version grid that is
    # about a day of cloning and hundreds of GB.
    if [ ! -d "$repo_dir/.git" ]; then
        print_info_message "⬇️ Fetching $sha from $slug"
        rm -rf "$repo_dir"
        mkdir -p "$repo_dir"
        git -C "$repo_dir" init --quiet
        git -C "$repo_dir" remote add origin "https://github.com/$slug.git"
    fi

    cd "$repo_dir" || return 1

    # fix_helper edits source files, so the tree has to be reset before we trust
    # a checkout -- otherwise a previous attempt's patches survive into this one.
    print_info_message "🧹 Resetting the working tree"
    git checkout --quiet -f 2> /dev/null
    git clean -qxfd 2> /dev/null

    if ! git cat-file -e "${sha}^{commit}" 2> /dev/null; then
        fetch_sha || return 1
    fi

    print_info_message "▶ Checking out $sha"
    git checkout --quiet -f "$sha" || {
        print_fail_message "❌ Failed to check out $sha"
        return 1
    }

    return 0
}

compile_module() {
    # -am builds the module's dependencies in the same reactor; without it a
    # multi-module project cannot resolve its own siblings.
    print_info_message "🛠️ Building $module (mvn install -DskipTests)"

    mvn -B install -DskipTests -pl "$module" -am $MVN_OPTS $MVN_EXTRA_OPTS \
        > "$out_dir/compile.log" 2>&1

    # MVN_OPTS carries -fn (fail never), so maven's exit code cannot be trusted
    # to report a failed build. Look at what it produced instead.
    if [ ! -d "$repo_dir/$module/target/test-classes" ]; then
        print_fail_message "❌ Build produced no test classes. Last lines of compile.log:"
        tail -n 40 "$out_dir/compile.log"
        return 1
    fi

    print_info_message "✅ Build OK"
    return 0
}

extract_test_list() {
    print_info_message "🔍 Extracting the test list by reflection (no tests are run)"

    get_test_list "$repo_dir" "$module" "$out_dir/test_list.txt" || return 1
    remove_known_flaky_tests "$out_dir/test_list.txt" "$slug" || return 1

    if [ ! -s "$out_dir/test_list.txt" ]; then
        print_fail_message "❌ The test list is empty"
        return 1
    fi

    return 0
}

run_the_order() {
    # Surefire writes its XMLs straight into the bind-mounted /out, so nothing
    # has to be moved after the run and nothing can be half moved.
    local reports_dir="$out_dir/surefire-reports"
    local start_time end_time maven_pid

    rm -rf "$reports_dir"
    mkdir -p "$reports_dir"

    cd "$repo_dir" || return 1

    print_info_message "▶ Running the order: $(wc -l < "$order_file" | tr -d ' ') tests"

    # The extension is loaded ONLY here. With it active but no -Dtest order to
    # impose, the forked surefire NPEs on a plain `mvn test`, which is why the
    # compile above runs vanilla.
    jfr_before_mvn "$out_dir"

    # Backgrounded only so its pid is knowable: the mvn script execs the JVM,
    # so $! is maven's own JVM, the one recording JFR must throw away.
    start_time=$(date +%s.%N)
    mvn -B -Dmaven.ext.class.path="$surefire_extension_jar" \
        test -pl "$module" \
        -Dtest="$order_file" \
        -Dsurefire.runOrder=testorder \
        -Dsurefire.reportsDirectory="$reports_dir" \
        $MVN_OPTS $MVN_EXTRA_OPTS \
        > "$out_dir/mvn.log" 2>&1 &
    maven_pid=$!
    wait "$maven_pid"
    end_time=$(date +%s.%N)

    jfr_after_mvn "$out_dir" "$maven_pid" "$module"

    echo "$start_time $end_time" > "$out_dir/wall_time.txt"
    print_info_message "⏱️ Wall time: $(echo "$end_time $start_time" | awk '{ printf "%.1f", $1 - $2 }')s"

    # Fall back to surefire's default location if the reportsDirectory override
    # did not take: better a copy than an empty result we cannot explain.
    if [ -z "$(find "$reports_dir" -maxdepth 1 -name 'TEST-*.xml' -print -quit)" ]; then
        print_info_message "📋 No reports at the override path, copying from the module target dir"
        cp "$repo_dir/$module/target/surefire-reports/"*.xml "$reports_dir/" 2> /dev/null
    fi

    # Surefire's crash dumps, which are the ONLY evidence when a fork dies.
    for dump_src in "$reports_dir" "$repo_dir/$module/target/surefire-reports"; do
        [ -d "$dump_src" ] || continue
        find "$dump_src" -maxdepth 1 \( -name '*.dump' -o -name '*.dumpstream' \) \
            -exec cp {} "$reports_dir/" \; 2> /dev/null
    done

    check_if_run_passed "$reports_dir" "$out_dir/mvn.log" || return 1

    return 0
}


# LOGIC

print_snapshot_message "$slug :: $module @ $sha"

mkdir -p "$out_dir"

seed_local_repo || {
    write_status "$out_dir" "FAIL:M2_SEED_FAILED"
    exit 1
}

if workspace_is_ready; then
    print_info_message "✅ Workspace already built at $sha -- skipping clone and compile"
else
    clone_and_checkout || {
        write_status "$out_dir" "FAIL:CHECKOUT_FAILED"
        exit 1
    }

    apply_fixes "$slug" "$module" "$sha" "compile" "$repo_dir" || {
        write_status "$out_dir" "FAIL:FIX_FAILED"
        exit 1
    }

    compile_module || {
        write_status "$out_dir" "FAIL:COMPILE_FAILED"
        exit 1
    }
fi

if [ -z "$order_file" ]; then
    extract_test_list || {
        write_status "$out_dir" "FAIL:TEST_LIST_FAILED"
        exit 1
    }

    write_status "$out_dir" "PASS"
    print_info_message "✅ Prepared $slug :: $module @ $sha -- $(wc -l < "$out_dir/test_list.txt" | tr -d ' ') tests"
    exit 0
fi

apply_fixes "$slug" "$module" "$sha" "runorder" "$repo_dir" || {
    write_status "$out_dir" "FAIL:FIX_FAILED"
    exit 1
}

run_the_order || {
    write_status "$out_dir" "FAIL:ORDER_RUN_FAILED"
    exit 1
}

write_status "$out_dir" "PASS"
print_info_message "✅ Ran the order for $slug :: $module @ $sha"
exit 0
