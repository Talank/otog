# Why the code is the way it is

The scripts say what they do. This says why, for the decisions where the
obvious alternative is wrong. Read the section you are about to change.

## The measurement unit

Every run gets exactly 4 CPUs and 16 GB, from a cold JVM, in its own
container. A run with a different budget is not a faster or slower measurement
of the same thing — it is a measurement of something else.

- `cpu_slice()` always pins. An unpinned container quietly takes the whole
  machine and stops being the unit being measured. Docker gets `--cpuset-cpus`;
  apptainer gets `taskset`, whose affinity the test JVM inherits.
- `--cpuset-cpus`, never `--cpus`. A share of every CPU is not four CPUs.
- Apptainer cannot apply a cgroup limit without root, so on a cluster the
  *allocation* is the container. `check_container_size()` refuses a wrong one
  rather than producing timings nothing can be compared with.
- Repetitions are separate containers. Repeating inside one measures a warmed-up
  JVM and a warm page cache.
- One workspace per checkout, locked (`take_workspace()`): two mavens in one
  working tree race in `target/`.

## Orders

An order is one `pkg.Class#method` per line. The 100 orders per module are
generated **once**, at v0, by `scripts/generate_random_test_order.py`:

- classes shuffled, and each class's own methods shuffled
- a class's methods always stay **contiguous** — a suite runs class by class,
  and interleaving would change class setup and teardown cost, which is not the
  variable under study
- deduplicated by md5, so all 100 differ

The generator is **not seeded**, so the files under `orders/` are the only
record of the treatment applied. They cannot be regenerated identically. Never
delete or regenerate them.

Every other version's orders are **adapted** from the v0 orders by
`scripts/order_adapter.py` — drop what the version no longer has, append what
it gained, keep everything else in place. A freshly random order at v50 would
not be "the same order" as order 5 at v0, and nothing could be compared along
the version axis.

Assignment: v0 and each future version get all 100 orders; historical version
-N gets exactly order N.

### Any file works as an order

`order_file()` takes a number as `orders/<module>/<version>/<n>.txt` and
anything else as a path, so a solver's output or a hand-written order runs
through the same machinery. `order_label()` turns it back into a directory
name: a number stays a number, a path becomes its file name. So

    bash run_experiment.sh --one 1685 0 /tmp/arbitrary_order.txt v0

writes `runs/1685/0/order_arbitrary_order/run_{1,2,3}` — three isolated runs
in their own directories, the same as any numbered order, with the same fixes.

## Fix strategies

A fix is a row in `data/fix_registry.csv`, never a change to `fix_helper.sh`.
`apply_fixes` looks the row up under four keys, in this order:

    <slug>   <slug>::<module>   <slug>@<sha>   <slug>::<module>@<sha>

**The order file is not one of them.** Fixes are keyed on the version, so every
order of one module-version pair — numbered, arbitrary, or a rerun — gets
exactly the same fixes. That is what makes two orders comparable at all.

`data/fix_strategies.csv` is the catalogue. A registry key naming a strategy
that is not in the catalogue is an error, not a silent no-op — that is what
catches a typo. `apply_fixes` runs at two stages, `compile` and `runorder`;
most strategies apply to both and ignore the argument.

## Maven flags

`MVN_OPTS` skips everything that is not the tests. Four of them are not obvious:

- `-Djapicmp.skip=true` — mapstruct binds japicmp to the build for 14 straight
  versions, which fail on that goal with no compilation error at all.
- `-s aux/settings.xml` — Central answers 429 for *every* artifact when the
  request comes from a compute node, and maven records that as a compile
  failure, which is exactly what a broken commit looks like. The file mirrors
  Central to Google's byte-for-byte copy. Maven does **not** fall back from a
  mirror, so read it before changing this.
- the `retryHandler` / `rto` / `ttlSeconds` flags — belt and braces for the same
  fault: a transport error is indistinguishable from a broken commit.
- `-Dmaven.legacyLocalRepo=true` — the seeded repo's `_remote.repositories`
  files record every artifact as coming from repo id `central`, but the mirror
  renames that id, so maven calls each seeded artifact "present, but
  unavailable" and re-verifies it over the network: 164 needless round trips per
  run, any one of which can reset and fail the build. A/B'd on 1685 v90 order
  10 — both arms PASS with 247 reports, re-verifications 164 to 0, wall 897s to
  664s.

`-fn` (fail never) is in there too, which is why maven's exit code is never
trusted: `compile_module` looks for `target/test-classes` instead.

`image_for_version()` uses numeric tests, not globs on `"$1:$2"`. A glob has to
spell out every version it covers, and the ones it silently missed (1216
v87-v89, 1305 v19) are versions whose test sources do not compile on the
project's usual JDK. With `-fn` the reactor carries on regardless, so the build
is called OK and the test list comes back EMPTY — a wrong answer rather than a
failure.

## Tests that hang

Two registries drop tests, and they are not interchangeable.

`data/idoft_flaky_tests.csv` (IDoFT) is applied to the **test list**, at
extraction time, by `remove_known_flaky_tests` — so no order ever contains a
known flaky test by construction. That works only in prepare mode. An order run
hands the order file straight to `-Dtest=` and never reads `test_list.txt`.

`data/hanging_tests.csv` therefore filters the **order**, at run time, by
`remove_known_hanging_tests`. A row is:

    slug,module,versions,test,status,evidence

- `versions` is a space-separated list, or `*` for every version of the module.
- `test` is `pkg.Class#method`, or a bare `pkg.Class` to drop every method of
  it — a TestNG suite reports one `Running TestSuite` line for a whole run, so
  the class is often all the log can tell you.
- `status` is `observed` or `active`. **Only `active` rows are applied.** A row
  starts as `observed`: recorded with its evidence, changing no test set.

Flipping a row to `active` changes what that module-version measures, and two
orders are only comparable if they contain the same tests. So the practical
rule is: activate a row only for a version with **zero passed runs**, or redo
every run of that version afterwards. Removing a test from some versions and not
others is fine — each version stays internally consistent, which is the
invariant. A version where *some* runs have the test and some do not is not.

The version is **derived from the sha** by `run_once.sh`, not passed in, so the
registry reaches a run started by hand with an order of your own exactly as it
reaches one the campaign scheduled. That is what keeps an arbitrary order
comparable with the numbered ones beside it.

Three files come out of this, and they answer different questions:

| file | what it is |
|---|---|
| `order.txt` | the order as handed over — compared against `orders/<module>/<version>/<n>.txt` |
| `order_effective.txt` | what actually ran, written only when something was removed |
| `removed_tests.txt` | what the registry dropped, written always, usually empty |

## The surefire fork

`-Dsurefire.runOrder=testorder` only imposes the order if two things are
present, and both fail quietly:

1. **The forked `maven-surefire-plugin`**, in the seeded `dependency/` repo,
   built **with PR #15**. Without PR #15 the JUnit 5 provider hands whole
   classes to the Jupiter engine and lets the engine pick method order — so
   class order is imposed and method order is not, silently, on every JUnit 5
   project. `check_surefire_fork()` in `setup.sh` looks for
   `TestOrderMethodOrderer.class` inside the named provider jar.
2. **`surefire-changing-maven-extension`**, passed as
   `-Dmaven.ext.class.path`. Maven ignores a path that does not exist — no
   warning, `BUILD SUCCESS` — and then keeps whatever surefire the project's own
   pom asks for. The run passes having measured nothing.

Two traps in that check, both of which let a bad tree pass:

- The jar is **named, not globbed**. A `-sources` or `-javadoc` jar sorts ahead
  of the real one and names the class in a `.java` or `.html` entry.
- The zip listing is **read before matching**, not piped into `grep -q`. `grep`
  exits on the match, `unzip` dies of SIGPIPE, and `pipefail` reports that as a
  missing class on a few percent of runs.

## Was the order imposed?

`scripts/check_order_imposed.py` compares maven's `Running <class>` lines and
the `<testcase>` sequence in each surefire XML against the order file. Four
differences are expected:

| difference | why | gated? |
|---|---|---|
| maven names the OUTER class for `@Nested` | that is how surefire reports them | compared at outer-class granularity |
| the order file re-enters a class it left | a class's tests always run contiguously | re-entries collapsed to first occurrence |
| a class runs a second time at the end | surefire's `rerunFailingTestsCount` reran a flaky test; the project's pom sets that | collapsed and reported |
| vintage (JUnit 4) method order differs | PR #15 registers a *Jupiter* `MethodOrderer`; the vintage engine has no such hook | reported, not gated |

A mixed-engine module also runs one contiguous block per engine, so its class
order arrives with **one** descent. That single shape is excused; more descents
than that is real scrambling and still fails.

`tests/test_no_regression.py` has a live two-class probe
(`OTOG_PROBE_ORDER=1`): Jupiter honours a reverse-alphabetical order, vintage
does not. If that ever starts passing for vintage, this table is out of date.

## Heap

Two mechanisms overwrite `argLine` and can cap the test JVM below the
container's 16 GB — jacoco's `prepare-agent` rewrites the property mid-build,
and a project's own pom `-Xmx` wins outright.

`otog_jvm_max_ram` is the backstop, and it is **off by default on purpose**:
every timing collected so far was taken without it, and a run only means
something next to the other runs of the same order. Turn it on only for a
campaign that re-runs everything.

It sets `-XX:MaxRAM` *and* a share flag, because `MaxRAM` alone still takes the
default 25% — measured on temurin-17: nothing 29.97g, `MaxRAM=16g` 4.00g,
`MaxRAM=16g MaxRAMPercentage=100` 16.00g. The share flag was renamed in JDK 10
and the wrong one is fatal, not ignored: java 8 answers `MaxRAMPercentage` with
"Could not create the Java Virtual Machine".

Never change a fork flag — `forkCount`, `reuseForks`,
`forkedProcessTimeoutSeconds` — to make a module behave. The fork configuration
is part of what is being measured. Use a wall-clock cap or a recorded gap
instead.

## JFR

Off by default: profiling costs about 8%, and a profiled run is not comparable
with an unprofiled one, so each gets its own `jfr_run_<n>` directory.
`jfr_eligible()` limits it to v0 and historical — the future versions exist to
confirm an order still applies, not to profile it again.

`jfr_before_mvn` asks maven for timestamped output. Surefire prints
`Running <class>` when a class starts and `Tests run: ... - in <class>` when it
ends; with timestamps those pairs become class windows on the same clock JFR
stamps its events with. They are a check on the windows that the agent in
`aux/jfrsort-agent.jar` writes as `jfrsort.TestClass` events, one per test
class, which jfrsort attributes events with.

The recording settings are the same on every JDK. Event settings on the
command line exist only from JDK 17 on, so `jfr_write_settings` copies the
JVM's own `profile` preset into the run directory and changes the settings
listed in `JFR_EVENT_RULES`. The allocation of a test class comes from the
two TLAB events, the buffers handed out plus the objects too large for one,
which exist on JDK 8 and give a measured amount. The allocation sample event
of JDK 16 and later would give an estimate of the same amount and is turned
off so that nothing is counted twice. The agent is built for JDK 8 for the
same reason: nine of the sixteen modules run on it.

## Engines

`container/engine.sh` is the only file that knows which engine is in use.

- `engine_image_exists` uses `docker images -q`, not `inspect`: under docker's
  containerd image store, `inspect` resolves only fully qualified refs and would
  call every short tag missing.
- Apptainer images are written as a `.sif` file, never a `--sandbox` directory.
  A sandbox is thousands of files, and on shared storage its ELF files have been
  seen disappearing, which breaks every later run with "executable file not
  found".
- Docker runs as `--user $(id -u):$(id -g)`. Without it everything written into
  `runs/` is owned by root, on a machine where you cannot chown it back.
- A relative bind source is a *named volume* to docker, so `engine_run` refuses
  one.
- `OTOG_ENGINE_DRYRUN=1` prints the argv and runs nothing. It needs no engine
  installed, which is how you read what a run would do before committing to it.

## Setup

`setup.sh` **compiles nothing on the host**. The surefire fork arrives prebuilt
in `dependency.zip`, and the two small jars in `aux/` are committed. A machine
whose JDK is newer than those sources expect still sets up, and the artifacts
stay the JDK 8 build that produced the existing data.

`quietly()` sends a step's output to a file and prints it only on failure —
image pulls and builds are hundreds of lines. It runs the step with stdin from
`/dev/null`: with the output hidden, a step that stopped to ask something would
wait forever behind a single `build ...` line, which is exactly what apptainer
does when an interrupted build left a `.sif.tmp` behind.

The native images bake in the C toolchain rather than installing it at run time,
because installing needs root and a writable `/usr` — true under docker, false
under apptainer, which runs as the calling user on a read-only image. Building
one needs `--fakeroot` (uid 0, or dpkg cannot unpack), no preset binds (with
`--writable`, apptainer cannot create a missing mountpoint) and
`APT::Sandbox::User=root` (apt drops to `_apt` to fetch, and a root-mapped
namespace with no subuid range has no second uid to drop to).

`clone_and_checkout` fetches **one commit with no history**. A full clone of a
big repo costs ~40s and a few hundred MB; across a 201-version grid that is
about a day of cloning and hundreds of GB.

## Running on a cluster

`slurm_run_experiment.sh` submits one job per repetition. Two ways it differs
from the local runner:

- **6 CPU and 24 G for a 4 CPU, 16 g container.** The extra is for the shell and
  apptainer around the container, not for the tests; `cpu_slice()` still pins
  the container to exactly 4.
- **`--constraint=amd`, always.** The `normal` partition mixes 64 amd nodes with
  28 intel ones, and the same order measures 20.3 s on amd against 25.2 s on
  hop — a 24% gap, twice the ~12% spread between the fastest and slowest order,
  which is the thing being measured. Letting the scheduler choose would make
  hardware the loudest variable in the experiment.
- **4 h plain, 6 h profiled.** Against 42,598 collected runs the longest run that
  ever passed took 2h30m and p99.9 took 70m, while every run over 3h failed. A
  job that hits the wall has hung, not merely been slow.

The feeder snapshots the queue once at the start: `run_passed()` only sees
*finished* work, so a feeder restarted while hundreds of jobs are still running
would submit every one of them again. It re-checks `STOP` every order, because
stopping a feeder must not mean waiting for it to finish.

`slurm_experiment_watchdog.sh` restarts the feeder, and takes a `flock` rather
than checking `pgrep`: a command line that mentions the feeder is not a feeder,
and that false positive once let the queue drain unnoticed for hours.

## Editing a script while runs are live

Write a temp file in the same directory and `mv` it over the target. Rename
swaps the inode, so processes already executing the script keep reading the
original. `run_once.sh` binds the tool read-only into the container and runs
`bash /otog/container/entrypoint.sh`; bash reads a script incrementally, holding
a byte offset, so an in-place rewrite leaves every running container's offset
pointing into different bytes and the tail executes as garbage.
