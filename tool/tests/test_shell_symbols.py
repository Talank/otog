"""Every function a script calls has to be defined by something it sources.

Two bugs shipped this way already: print_fail_message and
print_snapshot_message were called on paths nothing had defined them on, and
both only showed up once a real container ran.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The roots. Libraries are reached through them, which is the only context in
# which "is this name available here?" has an answer.
SCRIPTS = [REPO / n for n in ("setup.sh", "run_once.sh", "run_experiment.sh",
                              "container/entrypoint.sh")]
SHELL = sorted(REPO.glob("*.sh")) + sorted((REPO / "container").glob("*.sh")) \
        + sorted((REPO / "scripts").glob("*.sh"))

KEYWORDS = {
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
    "case", "esac", "in", "function", "return", "exit", "local", "export",
    "readonly", "declare", "source", "eval", "exec", "trap", "shift", "set",
    "unset", "break", "continue", "time", "select", "echo", "printf", "cd",
    "test", "read", "wait", "true", "false", "command", "type", "hash", "umask",
    "pwd", "kill", "jobs", "alias", "let", "mapfile", "ulimit", "getopts",
}


def strip_noise(text):
    out = []
    for line in text.splitlines():
        line = re.sub(r'(^|\s)#.*$', '', line)
        line = re.sub(r'"[^"]*"|\'[^\']*\'', '""', line)
        out.append(line)
    return "\n".join(out)


def strip_comments(text):
    return "\n".join(re.sub(r'(^|\s)#.*$', '', l) for l in text.splitlines())


def defined_in(path):
    return set(re.findall(r'^\s*(?:function\s+)?([a-z_][a-z0-9_]*)\s*\(\)',
                          path.read_text(), re.M))


def sourced_by(path):
    """Files this script sources, plus what those source, transitively.

    Both spellings appear: "$tool_dir/container/runtime.sh" inside the
    container, "$(dirname "${BASH_SOURCE[0]}")/lib.sh" on the host. Match the
    path that ends the line either way.
    """
    seen, queue = set(), [path]
    while queue:
        f = queue.pop()
        if f in seen or not f.exists():
            continue
        seen.add(f)
        for line in re.findall(r'^\s*(?:source|\.)\s+.*$', f.read_text(), re.M):
            m = re.search(r'([\w.-]+\.sh)"?\s*$', line)
            if m:
                queue += [f for f in SHELL if f.name == m.group(1)]
    return seen


def assigned_in(path):
    text = path.read_text()
    names = set(re.findall(r'^\s*(?:local\s+|export\s+)?([a-z_][a-z0-9_]*)=', text, re.M)) \
          | set(re.findall(r'\bfor\s+([a-z_][a-z0-9_]*)\s+in\b', text))
    # "local a b c" and "read -r a b c" declare all of them, not just the first
    for line in re.findall(r'\b(?:local|read(?:\s+-r)?)\s+([a-z_][a-z0-9_ ]*)', text):
        names |= set(line.split())
    return names


def called_in(path):
    """First token of each statement -- where a function call would be."""
    calls = set()
    for frag in re.split(r'[\n;|&]+|\$\(|\breturn\b|\bthen\b|\bdo\b|\belse\b',
                         strip_noise(path.read_text())):
        token = frag.strip().split(" ")[0].strip("({) ")
        if re.fullmatch(r'[a-z_][a-z0-9_]*', token or "") and token not in KEYWORDS:
            calls.add(token)
    return calls - assigned_in(path)


def test_no_script_calls_a_function_it_never_sources():
    known = set()
    for f in SHELL:
        known |= defined_in(f)

    missing = {}
    for script in SCRIPTS:
        available = set()
        for f in sourced_by(script):
            available |= defined_in(f)
        # A name defined nowhere in the repo is an external command, not ours.
        gap = sorted((called_in(script) & known) - available)
        if gap:
            missing[script.name] = gap

    assert not missing, f"called but never sourced: {missing}"


def test_no_script_calls_a_function_that_does_not_exist():
    # The other test only sees names defined somewhere. A name defined nowhere
    # looks like an external command to it -- and to bash, which prints
    # "command not found" into the run log and carries on.
    import shutil

    known = set()
    for f in SHELL:
        known |= defined_in(f)

    ghosts = {}
    for script in SHELL:
        # config variables are set in the file that gets sourced, not this one
        variables = set()
        for f in sourced_by(script):
            variables |= assigned_in(f)
        gap = sorted(c for c in called_in(script) - variables
                     if "_" in c and c not in known and not shutil.which(c))
        if gap:
            ghosts[script.name] = gap

    assert not ghosts, f"called but defined nowhere: {ghosts}"


def test_every_sourced_file_exists():
    # scripts/extract_test_list.sh sourced a helpers.sh that the split into
    # runtime.sh and lib.sh had already deleted. Nothing noticed until it ran.
    broken = []
    for script in SHELL:
        for line in re.findall(r'^\s*(?:source|\.)\s+.*$', script.read_text(), re.M):
            m = re.search(r'([\w.-]+\.sh)"?\s*$', line)
            if m and not any(f.name == m.group(1) for f in SHELL):
                broken.append(f"{script.name} -> {m.group(1)}")
    assert not broken, f"sources a file that does not exist: {broken}"


def test_the_container_still_says_what_it_is_doing():
    # print_info/print_fail were never set, so every diagnostic in every
    # container run was silently dropped. They default to on now.
    import subprocess
    r = subprocess.run(
        ["bash", "-c",
         f'source "{REPO}/container/runtime.sh"; print_info_message hello; print_fail_message oops'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert "hello" in r.stdout and "oops" in r.stdout, f"container logging is silent: {r!r}"


def test_a_muted_message_does_not_look_like_a_failure():
    # These get called as the last statement of a function often enough that
    # returning 1 when muted would turn a good run into a failed one.
    import subprocess
    r = subprocess.run(
        ["bash", "-c",
         f'source "{REPO}/container/runtime.sh"; print_info=false; '
         'print_info_message quiet; echo "rc=$?"'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert "rc=0" in r.stdout, r.stdout


CONTAINER = [REPO / "container" / n for n in ("entrypoint.sh", "runtime.sh", "jfr.sh")] \
            + [REPO / "fix_helper.sh", REPO / "config_default.sh"]

# Set by run_once.sh through --env, or by the shell itself.
FROM_OUTSIDE = {
    "slug", "module", "sha", "order_file", "tool_dir", "otog_root",
    "image", "jfr", "out", "n", "status",
}


def test_no_container_script_reads_a_variable_nobody_sets():
    # config_default.sh renamed surefire_extension_jar to surefire_jar while
    # entrypoint.sh still read the old name, so -Dmaven.ext.class.path was
    # empty and the order was never imposed. The run still passed.
    assigned = set(FROM_OUTSIDE)
    for f in CONTAINER:
        assigned |= assigned_in(f)

    ghosts = {}
    for f in CONTAINER:
        text = strip_comments(f.read_text())
        # ${x:-default} is a deliberate default, not a hole. $x and ${x} are.
        guarded = set(re.findall(r'\$\{([a-z][a-z0-9_]{3,})[:#%/^,-]', text))
        used = set(re.findall(r'\$\{?([a-z][a-z0-9_]{3,})\}?', text)) - guarded
        gap = sorted(used - assigned)
        if gap:
            ghosts[f.name] = gap

    assert not ghosts, f"read but never set: {ghosts}"
