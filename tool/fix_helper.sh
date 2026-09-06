#!/bin/bash
#
# source fix_helper.sh; apply_fixes netty/netty transport <sha> compile /work/repo
#
# Per-project build fixes as reusable strategies. Adding a fix is a row in
# data/fix_registry.csv, not a change to this file.
#
# in : <slug> <module> <sha> <stage:compile|runorder> <project_dir>
# out: the checkout is patched in place


# ------------------------------------------------------------------ catalogue

# strategy name -> what it does, one line. apply_fixes refuses a strategy with
# no entry here, so a typo'd registry key cannot silently do nothing.
declare -A FIX_STRATEGY_DESCRIPTION=()
declare -A PROJECT_FIX_STRATEGIES=()

load_fix_tables() {
    # Pure bash: this runs inside the container, which has no python.
    local strategies_csv="${fix_strategies_csv:-$tool_dir/data/fix_strategies.csv}"
    local registry_csv="${fix_registry_csv:-$tool_dir/data/fix_registry.csv}"
    local key rest

    if [ -r "$strategies_csv" ]; then
        while IFS=, read -r key rest; do
            key=${key%$'\r'}; rest=${rest%$'\r'}
            case "$key" in ''|'#'*|strategy) continue ;; esac
            FIX_STRATEGY_DESCRIPTION["$key"]="$rest"
        done < "$strategies_csv"
    else
        print_fail_message "❌ No fix strategy catalogue at $strategies_csv"
        return 1
    fi

    if [ -r "$registry_csv" ]; then
        while IFS=, read -r key rest; do
            key=${key%$'\r'}; rest=${rest%$'\r'}
            case "$key" in ''|'#'*|key) continue ;; esac
            PROJECT_FIX_STRATEGIES["$key"]="$rest"
        done < "$registry_csv"
    else
        print_fail_message "❌ No fix registry at $registry_csv"
        return 1
    fi

    return 0
}

load_fix_tables || return 1 2> /dev/null || exit 1



# ------------------------------------------------------------------ registry

# key -> space separated strategy names.

# ------------------------------------------------------------------ strategies

fix_strategy_remove_snapshots() {
    # Old commits depend on -SNAPSHOT versions Central has since purged, so the
    # build dies on a dependency that has nothing to do with the code.
    # Stripping -SNAPSHOT pins the release that snapshot became.
    local project_dir=$1
    local module_pom

    print_info_message "🔧 Removing -SNAPSHOT versions from every pom"
    for module_pom in $(find "$project_dir" -name pom.xml); do
        grep -q "<version>.*-SNAPSHOT</version>" "$module_pom" || continue
        sed -i 's/<version>\(.*\)-SNAPSHOT<\/version>/<version>\1<\/version>/' "$module_pom"
        # spring-ai pins its SDK through a property, not a <version>
        sed -i 's|<mcp.sdk.version>\(.*\)-SNAPSHOT</mcp.sdk.version>|<mcp.sdk.version>\1</mcp.sdk.version>|g' "$module_pom"
    done
}

fix_strategy_insecure_ssl() {
    print_info_message "🔧 Allowing untrusted TLS for dependency resolution"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Dmaven.wagon.http.ssl.insecure=true -Dmaven.wagon.http.ssl.allowall=true"
}

fix_strategy_private_develocity_cache() {
    local cache_dir="/tmp/develocity_cache_$$"

    print_info_message "🔧 Pointing the develocity cache at $cache_dir"
    mkdir -p "$cache_dir"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Ddevelocity.cache.local.directory=$cache_dir"
}

fix_strategy_drop_build_extensions() {
    local project_dir=$1

    # .mvn/extensions.xml resolves from Central before the retry settings in
    # MVN_OPTS apply, so rate limiting kills the build before a source file is read.
    local extensions="$project_dir/.mvn/extensions.xml"

    if [ -f "$extensions" ]; then
        print_info_message "🔧 Removing $extensions (build-scan extension, not needed to compile)"
        rm -f "$extensions"
    fi
}

fix_strategy_tolerate_build_failure() {
    print_info_message "🔧 Accepting this build even without BUILD SUCCESS"
    tolerate_failure=true
}


fix_strategy_curator_shade_keep_guava_base() {
    # curator-client 5.0.0-SNAPSHOT shades guava in, then excludes three of its
    # classes again, so anything needing them fails to link.
    local project_dir=$1
    local pom="$project_dir/curator-client/pom.xml"

    if [ ! -f "$pom" ]; then
        print_fail_message "❌ No curator-client/pom.xml under $project_dir"
        return 1
    fi

    if ! grep -q "com/google/common/base/Predicate.class" "$pom"; then
        print_info_message "🔧 curator-client already keeps the guava base classes -- nothing to do"
        return 0
    fi

    print_info_message "🔧 Removing the three guava <exclude> lines from curator-client/pom.xml"
    sed -i \
        -e '/<exclude>com\/google\/common\/base\/Function\.class<\/exclude>/d' \
        -e '/<exclude>com\/google\/common\/base\/Predicate\.class<\/exclude>/d' \
        -e '/<exclude>com\/google\/common\/reflect\/TypeToken\.class<\/exclude>/d' \
        "$pom" || {
        print_fail_message "❌ Could not edit $pom"
        return 1
    }

    if grep -q "com/google/common/base/Predicate.class" "$pom"; then
        print_fail_message "❌ The guava <exclude> lines are still in $pom"
        return 1
    fi

    return 0
}

fix_strategy_native_build_toolchain() {
    # The image has a JDK and maven and nothing else; netty's antrun step needs
    # `make`, so without it the build and everything downstream fails.
    if command -v make > /dev/null 2>&1 && command -v gcc > /dev/null 2>&1; then
        print_info_message "🔧 C toolchain already present -- nothing to install"
        return 0
    fi

    print_info_message "🔧 Installing the C build toolchain (make, gcc, autotools)"

    local attempt
    for attempt in 1 2 3; do
        if DEBIAN_FRONTEND=noninteractive apt-get update -qq > /dev/null 2>&1 \
        && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
               build-essential autoconf automake libtool > /dev/null 2>&1; then
            print_info_message "✅ C toolchain installed ($(make --version | head -1))"
            return 0
        fi
        print_info_message "⚠️ apt attempt $attempt failed, retrying"
        sleep 5
    done

    print_fail_message "❌ Could not install the C build toolchain"
    return 1
}


fix_strategy_curator_mockito_test_dependency() {
    local project_dir=$1
    local module=$2
    local pom="$project_dir/$module/pom.xml"

    if [ ! -f "$pom" ]; then
        print_fail_message "❌ No pom at $pom"
        return 1
    fi

    if grep -q "<artifactId>mockito-core</artifactId>" "$pom"; then
        print_info_message "🔧 mockito-core already declared in $module/pom.xml"
        return 0
    fi

    print_info_message "🔧 Adding the mockito-core test dependency to $module/pom.xml"

    # No <version>: the parent's dependencyManagement pins 1.9.5, which is the
    # version upstream itself used and the last one that still has Whitebox.
    sed -i '0,/<dependencies>/s|<dependencies>|<dependencies>\n        <dependency>\n            <groupId>org.mockito</groupId>\n            <artifactId>mockito-core</artifactId>\n            <scope>test</scope>\n        </dependency>|' "$pom" || return 1

    grep -q "<artifactId>mockito-core</artifactId>" "$pom" || {
        print_fail_message "❌ Failed to insert mockito-core into $pom"
        return 1
    }

    return 0
}

fix_strategy_curator_shared_value_watcher_types() {
    local project_dir=$1
    local shared_value="$project_dir/curator-recipes/src/main/java/org/apache/curator/framework/recipes/shared/SharedValue.java"
    local test_shared_count="$project_dir/curator-recipes/src/test/java/org/apache/curator/framework/recipes/shared/TestSharedCount.java"

    if [ ! -f "$shared_value" ]; then
        print_fail_message "❌ No SharedValue.java at $shared_value"
        return 1
    fi

    print_info_message "🔧 Retyping SharedValue's @VisibleForTesting ctor to WatcherRemoveCuratorFramework"

    # Edit 1: the ctor takes the type the field actually is. The import for
    # WatcherRemoveCuratorFramework is already present in this file.
    sed -i 's|protected SharedValue(CuratorFramework client, String path, byte\[\] seedValue, CuratorWatcher watcher)|protected SharedValue(WatcherRemoveCuratorFramework client, String path, byte[] seedValue, CuratorWatcher watcher)|' \
        "$shared_value" || return 1

    grep -q "protected SharedValue(WatcherRemoveCuratorFramework client" "$shared_value" || {
        print_fail_message "❌ Failed to retype the SharedValue constructor"
        return 1
    }

    # Edit 2: the only caller of that ctor is a local class in the tests, which
    # must now wrap its plain client the same way upstream's fix does.
    if [ -f "$test_shared_count" ]; then
        print_info_message "🔧 Wrapping the test caller's client in newWatcherRemoveCuratorFramework()"
        sed -i 's|super(client, path, seedValue, fautlyWatcher);|super(client.newWatcherRemoveCuratorFramework(), path, seedValue, fautlyWatcher);|' \
            "$test_shared_count" || return 1
    fi

    return 0
}


fix_strategy_skip_spring_javaformat() {
    print_info_message "🔧 Skipping spring-javaformat validation (style linter, not a compile/test concern)"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Dspring-javaformat.skip=true"
}


fix_strategy_curator_listener_manager_ctor_access() {
    local project_dir=$1
    local f="$project_dir/curator-framework/src/main/java/org/apache/curator/framework/listen/StandardListenerManager.java"

    if [ ! -f "$f" ]; then
        print_fail_message "❌ No StandardListenerManager.java at $f"
        return 1
    fi

    print_info_message "🔧 Relaxing StandardListenerManager's ctor from private to package-private"

    sed -i 's/private StandardListenerManager(ListenerManager<T, T> container)/StandardListenerManager(ListenerManager<T, T> container)/' "$f" || return 1

    grep -q 'private StandardListenerManager(ListenerManager<T, T> container)' "$f" && {
        print_fail_message "❌ Failed to relax the constructor's access modifier"
        return 1
    }

    return 0
}


fix_strategy_force_test_heap() {
    local project_dir=$1

    # A project that writes its own <argLine> wins the heap argument.
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
        print_fail_message "⚠️  force_test_heap found no <argLine> with -Xmx -- pom changed upstream?"
        return 0
    fi

    print_info_message "🔧 Forced the surefire fork heap to $heap in $touched pom(s)"
}

fix_strategy_skip_japicmp() {
    print_info_message "🔧 Skipping japicmp (binary/source API-compatibility gate, not a compile/test concern)"
    MVN_EXTRA_OPTS="$MVN_EXTRA_OPTS -Djapicmp.skip=true"
}


# ------------------------------------------------------------------ entry point

purge_project_artifacts() {
    # Drop the project's OWN artifacts from the local repo before a build.
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

    # org.apache would take maven's own plugins with it, the surefire fork
    # included, and nothing under test publishes that high in the tree.
    [ -d "$group_dir/maven/plugins" ] && return 0

    rm -rf "$group_dir"
    print_info_message "🧹 Dropped seeded $group artifacts -- this build installs its own"
}


apply_fixes() {
    # apply_fixes <slug> <module> <sha> <stage> <project_dir>
    # <stage> is compile or runorder; most strategies apply to both.
    local slug=$1
    local module=$2
    local sha=$3
    local stage=$4
    local project_dir=$5

    local applied=0
    local key
    local strategy

    if [ "$stage" = compile ]; then
        purge_project_artifacts "$project_dir"
    fi

    for key in "$slug" "$slug::$module" "$slug@$sha" "$slug::$module@$sha"; do
        for strategy in ${PROJECT_FIX_STRATEGIES[$key]:-}; do
            if [ -z "${FIX_STRATEGY_DESCRIPTION[$strategy]:-}" ]; then
                print_fail_message "❌ Unknown fix strategy '$strategy' registered under '$key'"
                return 1
            fi

            print_info_message "🔧 [$key] $strategy -- ${FIX_STRATEGY_DESCRIPTION[$strategy]}"
            "fix_strategy_$strategy" "$project_dir" "$module" "$sha" "$stage" || {
                print_fail_message "❌ Fix strategy '$strategy' failed for $slug@$sha"
                return 1
            }
            applied=$((applied + 1))
        done
    done

    if [ "$applied" -eq 0 ]; then
        print_info_message "🔍 No fixes registered for $slug ($module) at $sha -- building as upstream shipped it"
    else
        print_info_message "✅ Applied $applied fix(es) for stage '$stage'"
    fi

    return 0
}
