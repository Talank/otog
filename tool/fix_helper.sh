#!/bin/bash
#
# usage: source fix_helper.sh; apply_fixes <slug> <module> <sha> <stage> <project_dir>
# e.g.   source fix_helper.sh; apply_fixes netty/netty transport abc1234 compile /work/repo
#
# Per-project build fixes as reusable strategies. Adding a fix is a row in
# data/fix_registry.csv, not a change to this file.
#
# in : <stage> is compile or runorder; the registry keys on slug, module and sha
# out: the checkout is patched in place
#
# Fixes are keyed on the VERSION, never on the order, so every order of one
# module-version gets exactly the same ones. See docs/design.md.

fix_strategies_csv="${fix_strategies_csv:-$tool_dir/data/fix_strategies.csv}"
fix_registry_csv="${fix_registry_csv:-$tool_dir/data/fix_registry.csv}"


# ------------------------------------------------------------------- tables

# The strategies registered under one key, space separated. Empty if none.
strategies_for() {
    awk -F, -v want="$1" '$1 == want { sub(/^[^,]*,/, ""); sub(/\r$/, ""); print; exit }' \
        "$fix_registry_csv" 2> /dev/null
}

# What one strategy does, in a line. Empty if it is not in the catalogue.
strategy_description() {
    awk -F, -v want="$1" '$1 == want { sub(/^[^,]*,/, ""); sub(/\r$/, ""); print; exit }' \
        "$fix_strategies_csv" 2> /dev/null
}

# Both CSVs have to be readable, or every lookup would silently find nothing.
check_fix_tables() {
    [ -r "$fix_strategies_csv" ] || {
        print_fail_message "error: no fix strategy catalogue at $fix_strategies_csv"
        return 1
    }
    [ -r "$fix_registry_csv" ] || {
        print_fail_message "error: no fix registry at $fix_registry_csv"
        return 1
    }
}


# --------------------------------------------------------------- strategies

# Strip -SNAPSHOT so a purged snapshot resolves to the release it became.
fix_strategy_remove_snapshots() {
    local project_dir=$1
    local module_pom

    print_info_message "fix: removing -SNAPSHOT versions from every pom"
    for module_pom in $(find "$project_dir" -name pom.xml); do
        grep -q "<version>.*-SNAPSHOT</version>" "$module_pom" || continue
        sed -i 's/<version>\(.*\)-SNAPSHOT<\/version>/<version>\1<\/version>/' "$module_pom"
        # spring-ai pins its SDK through a property, not a <version>
        sed -i 's|<mcp.sdk.version>\(.*\)-SNAPSHOT</mcp.sdk.version>|<mcp.sdk.version>\1</mcp.sdk.version>|g' "$module_pom"
    done
}

# Accept untrusted TLS when a repository's certificate chain no longer validates.
fix_strategy_insecure_ssl() {
    print_info_message "fix: allowing untrusted TLS for dependency resolution"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Dmaven.wagon.http.ssl.insecure=true -Dmaven.wagon.http.ssl.allowall=true"
}

# Give the build its own develocity cache so parallel containers cannot collide.
fix_strategy_private_develocity_cache() {
    local cache_dir="/tmp/develocity_cache_$$"

    print_info_message "fix: pointing the develocity cache at $cache_dir"
    mkdir -p "$cache_dir"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Ddevelocity.cache.local.directory=$cache_dir"
}

# Delete .mvn/extensions.xml, which resolves from Central before our retry flags apply.
fix_strategy_drop_build_extensions() {
    local project_dir=$1
    local extensions="$project_dir/.mvn/extensions.xml"

    if [ -f "$extensions" ]; then
        print_info_message "fix: removing $extensions (build-scan extension, not needed to compile)"
        rm -f "$extensions"
    fi
}

# Accept a run whose build never reports BUILD SUCCESS but still produces usable XML.
fix_strategy_tolerate_build_failure() {
    print_info_message "fix: accepting this build even without BUILD SUCCESS"
    tolerate_failure=true
}

# curator-client shades guava in, then excludes three classes its own code calls.
fix_strategy_curator_shade_keep_guava_base() {
    local project_dir=$1
    local pom="$project_dir/curator-client/pom.xml"

    if [ ! -f "$pom" ]; then
        print_fail_message "error: no curator-client/pom.xml under $project_dir"
        return 1
    fi

    if ! grep -q "com/google/common/base/Predicate.class" "$pom"; then
        print_info_message "fix: curator-client already keeps the guava base classes"
        return 0
    fi

    print_info_message "fix: removing the three guava <exclude> lines from curator-client/pom.xml"
    sed -i \
        -e '/<exclude>com\/google\/common\/base\/Function\.class<\/exclude>/d' \
        -e '/<exclude>com\/google\/common\/base\/Predicate\.class<\/exclude>/d' \
        -e '/<exclude>com\/google\/common\/reflect\/TypeToken\.class<\/exclude>/d' \
        "$pom" || {
        print_fail_message "error: could not edit $pom"
        return 1
    }

    if grep -q "com/google/common/base/Predicate.class" "$pom"; then
        print_fail_message "error: the guava <exclude> lines are still in $pom"
        return 1
    fi

    return 0
}

# Install the C toolchain the maven image lacks, for a reactor with a native library.
fix_strategy_native_build_toolchain() {
    if command -v make > /dev/null 2>&1 && command -v gcc > /dev/null 2>&1; then
        print_info_message "fix: C toolchain already present"
        return 0
    fi

    print_info_message "fix: installing the C build toolchain (make, gcc, autotools)"

    local attempt
    for attempt in 1 2 3; do
        if DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null 2>&1 \
        && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
               build-essential autoconf automake libtool > /dev/null 2>&1; then
            print_info_message "fix: C toolchain installed ($(make --version | head -1))"
            return 0
        fi
        print_info_message "warning: apt attempt $attempt failed, retrying"
        sleep 5
    done

    print_fail_message "error: could not install the C build toolchain"
    return 1
}

# Declare the mockito-core test dependency the module's tests import but its pom omits.
fix_strategy_curator_mockito_test_dependency() {
    local project_dir=$1
    local module=$2
    local pom="$project_dir/$module/pom.xml"

    if [ ! -f "$pom" ]; then
        print_fail_message "error: no pom at $pom"
        return 1
    fi

    if grep -q "<artifactId>mockito-core</artifactId>" "$pom"; then
        print_info_message "fix: mockito-core already declared in $module/pom.xml"
        return 0
    fi

    print_info_message "fix: adding the mockito-core test dependency to $module/pom.xml"

    # No <version>: the parent's dependencyManagement pins 1.9.5, the version
    # upstream used and the last one that still has Whitebox.
    sed -i '0,/<dependencies>/s|<dependencies>|<dependencies>\n        <dependency>\n            <groupId>org.mockito</groupId>\n            <artifactId>mockito-core</artifactId>\n            <scope>test</scope>\n        </dependency>|' "$pom" || return 1

    grep -q "<artifactId>mockito-core</artifactId>" "$pom" || {
        print_fail_message "error: failed to insert mockito-core into $pom"
        return 1
    }

    return 0
}

# Upstream's own next-commit fix for SharedValue's ctor taking the wrong client type.
fix_strategy_curator_shared_value_watcher_types() {
    local project_dir=$1
    local shared_value="$project_dir/curator-recipes/src/main/java/org/apache/curator/framework/recipes/shared/SharedValue.java"
    local test_shared_count="$project_dir/curator-recipes/src/test/java/org/apache/curator/framework/recipes/shared/TestSharedCount.java"

    if [ ! -f "$shared_value" ]; then
        print_fail_message "error: no SharedValue.java at $shared_value"
        return 1
    fi

    print_info_message "fix: retyping SharedValue's @VisibleForTesting ctor to WatcherRemoveCuratorFramework"

    sed -i 's|protected SharedValue(CuratorFramework client, String path, byte\[\] seedValue, CuratorWatcher watcher)|protected SharedValue(WatcherRemoveCuratorFramework client, String path, byte[] seedValue, CuratorWatcher watcher)|' \
        "$shared_value" || return 1

    grep -q "protected SharedValue(WatcherRemoveCuratorFramework client" "$shared_value" || {
        print_fail_message "error: failed to retype the SharedValue constructor"
        return 1
    }

    # The only caller is a local class in the tests, which must wrap its client
    # the same way upstream's fix does.
    if [ -f "$test_shared_count" ]; then
        print_info_message "fix: wrapping the test caller's client in newWatcherRemoveCuratorFramework()"
        sed -i 's|super(client, path, seedValue, fautlyWatcher);|super(client.newWatcherRemoveCuratorFramework(), path, seedValue, fautlyWatcher);|' \
            "$test_shared_count" || return 1
    fi

    return 0
}

# Skip the spring-javaformat validate goal, a style linter.
fix_strategy_skip_spring_javaformat() {
    print_info_message "fix: skipping spring-javaformat validation"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Dspring-javaformat.skip=true"
}

# Relax StandardListenerManager's ctor, made private before its one caller was updated.
fix_strategy_curator_listener_manager_ctor_access() {
    local project_dir=$1
    local f="$project_dir/curator-framework/src/main/java/org/apache/curator/framework/listen/StandardListenerManager.java"

    if [ ! -f "$f" ]; then
        print_fail_message "error: no StandardListenerManager.java at $f"
        return 1
    fi

    print_info_message "fix: relaxing StandardListenerManager's ctor to package-private"

    sed -i 's/private StandardListenerManager(ListenerManager<T, T> container)/StandardListenerManager(ListenerManager<T, T> container)/' "$f" || return 1

    grep -q 'private StandardListenerManager(ListenerManager<T, T> container)' "$f" && {
        print_fail_message "error: failed to relax the constructor's access modifier"
        return 1
    }

    return 0
}

# Rewrite the -Xmx inside a pom argLine, which otherwise wins over the container heap.
fix_strategy_force_test_heap() {
    local project_dir=$1
    local heap="${otog_jvm_heap:-16g}"
    local touched=0
    local pom

    while IFS= read -r pom; do
        grep -q '<argLine>' "$pom" || continue
        grep -qE '<argLine>[^<]*-Xmx' "$pom" || continue
        sed -i -E "/<argLine>/ s/-Xmx[0-9]+[kmgKMG]?/-Xmx$heap/g" "$pom"
        touched=$((touched + 1))
    done < <(find "$project_dir" -name pom.xml -not -path '*/target/*')

    if [ "$touched" -eq 0 ]; then
        print_fail_message "warning: force_test_heap found no <argLine> with -Xmx -- pom changed upstream?"
        return 0
    fi

    print_info_message "fix: forced the surefire fork heap to $heap in $touched pom(s)"
}

# Skip the japicmp API-compatibility gate, a release-process check.
fix_strategy_skip_japicmp() {
    print_info_message "fix: skipping japicmp"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Djapicmp.skip=true"
}


# -------------------------------------------------------------- entry point

# Drop the project's OWN artifacts from the local repo before a build.
purge_project_artifacts() {
    local project_dir=$1
    local group group_dir

    group=$(awk '
        /<parent>/   { p = 1 }
        /<\/parent>/ { p = 0; next }
        p            { next }
        /<dependenc/ { exit }
        match($0, /<groupId>[^<]+/) { print substr($0, RSTART + 9, RLENGTH - 9); exit }
    ' "$project_dir/pom.xml" 2> /dev/null)

    # No dot means we matched some other tag's text, not a groupId.
    case "$group" in *.*) ;; *) return 0 ;; esac

    group_dir="$container_m2_dir/${group//.//}"

    # org.apache would take maven's own plugins with it, the surefire fork included.
    [ -d "$group_dir/maven/plugins" ] && return 0

    rm -rf "$group_dir"
    print_info_message "dropped seeded $group artifacts -- this build installs its own"
}

# Apply every strategy registered for this slug, module and sha, in that order.
apply_fixes() {
    local slug=$1
    local module=$2
    local sha=$3
    local stage=$4
    local project_dir=$5

    local applied=0
    local key strategy description

    check_fix_tables || return 1

    if [ "$stage" = compile ]; then
        purge_project_artifacts "$project_dir"
    fi

    for key in "$slug" "$slug::$module" "$slug@$sha" "$slug::$module@$sha"; do
        for strategy in $(strategies_for "$key"); do
            description=$(strategy_description "$strategy")
            if [ -z "$description" ]; then
                print_fail_message "error: unknown fix strategy '$strategy' registered under '$key'"
                return 1
            fi

            print_info_message "fix: [$key] $strategy -- $description"
            "fix_strategy_$strategy" "$project_dir" "$module" "$sha" "$stage" || {
                print_fail_message "error: fix strategy '$strategy' failed for $slug@$sha"
                return 1
            }
            applied=$((applied + 1))
        done
    done

    if [ "$applied" -eq 0 ]; then
        print_info_message "no fixes registered for $slug ($module) at $sha -- building as upstream shipped it"
    else
        print_info_message "applied $applied fix(es) for stage '$stage'"
    fi

    return 0
}
