#!/usr/bin/env bash
#
# usage: bash jfr_setup.sh
# e.g.   bash jfr_setup.sh
#
# Finds the installed JDK, verifies its jfr command and puts it on the PATH of
# future shells -- some machines have a JDK whose bin/ was never exported.
#
# in : nothing, or JFR_SHELL_RC to write somewhere other than ~/.zshrc
# out: JAVA_HOME and PATH exported, and appended to the shell rc once

set -euo pipefail

shell_rc="${JFR_SHELL_RC:-$HOME/.zshrc}"

die() {
    printf 'jfr setup: %s\n' "$1" >&2
    exit 1
}

find_java_home() {
    if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        printf '%s\n' "$JAVA_HOME"
        return 0
    fi

    if [ -x /usr/libexec/java_home ]; then
        /usr/libexec/java_home 2>/dev/null && return 0
    fi

    local java_path
    java_path=$(command -v java 2>/dev/null || true)
    [ -n "$java_path" ] || return 1
    java_path=$(readlink -f "$java_path" 2>/dev/null || printf '%s' "$java_path")
    dirname "$(dirname "$java_path")"
}

java_home=$(find_java_home) || die "could not locate an installed JDK"
jfr_path="$java_home/bin/jfr"

[ -x "$jfr_path" ] || die "JFR was not found at $jfr_path"
jfr_version=$("$jfr_path" --version)

mkdir -p "$(dirname "$shell_rc")"
touch "$shell_rc"

if ! grep -Fq '# OTOG JFR setup' "$shell_rc"; then
    {
        printf '\n# OTOG JFR setup\n'
        printf 'export JAVA_HOME="%s"\n' "$java_home"
        printf 'export PATH="$JAVA_HOME/bin:$PATH"\n'
    } >> "$shell_rc"
fi

export JAVA_HOME="$java_home"
export PATH="$JAVA_HOME/bin:$PATH"

printf 'JFR %s is available at %s\n' "$jfr_version" "$jfr_path"
printf 'Configured %s\n' "$shell_rc"
printf 'Run: source %s\n' "$shell_rc"