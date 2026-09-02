# jfrsort

Sorts a Maven project's test classes by metrics measured with Java Flight Recorder (JFR).
It is the JFR-based successor to csto2's MXBean-based metric sorts. The only metric today
is `alloc` — estimated allocated heap bytes per test class — and the sort reproduces
csto2's `alloc-sort` rule: a full, stable sort of the initial order by the metric, descending.

## Pipeline

1. **Profile.** Run `mvn test` N times (default 3). Each run sets `JAVA_TOOL_OPTIONS` so
   every JVM the build starts — including every Surefire fork — records a JFR file
   (`settings=profile`, `dumponexit=true`) into `out/run-<i>/jfr/`. The project's own
   `argLine` and Surefire configuration stay untouched.
2. **Discover.** After each run, read the Surefire XML reports (`TEST-*.xml`) to get the
   list of test classes that actually ran. Nested (`$`) classes collapse to their
   top-level class. Ascending report-file mtime gives the initial (execution) order.
3. **Attribute.** Parse each recording with `jfr print --json`. Every
   `jdk.ObjectAllocationSample` event is attributed to the first stack frame, innermost
   first, whose top-level class is a known test class; its `weight` (estimated bytes)
   is added to that class. Recordings with no test-class frames at all (e.g. the Maven
   launcher JVM, which `JAVA_TOOL_OPTIONS` also reaches) are dropped.
4. **Average.** Per class, take the arithmetic mean of the attributed bytes over the N
   runs. A class with no samples in a run contributes 0 for that run.
5. **Sort.** Stable-sort the initial order by mean bytes, descending. Ties keep their
   initial relative order — the same rule as csto2's `alloc-sort`.

## Usage

```bash
python3 jfrsort.py --project ~/Development/Research/commons-csv --runs 3
```

Options: `--metric alloc` (only metric so far), `--out DIR` (default `.jfrsort`),
`--mvn BIN`, `--jfr-bin BIN`, `--maven-args "..."`.

## Outputs (under `--out`)

- `order-alloc-sort.txt` — the sorted class list, one per line, largest mean allocator first.
- `metrics.csv` — per class: mean and per-run attributed bytes, in sorted order.
- `run-<i>/metrics.json` — raw per-run data: per-class sums, unattributed weight,
  which recordings were kept/dropped, suite wall seconds.
- `run-<i>/mvn.log`, `run-<i>/jfr/*.jfr` — the build log and raw recordings.

## Requirements and limits

- JDK 16+ (for `jdk.ObjectAllocationSample`) and the `jfr` CLI on `PATH`; the target
  suite must be green (`mvn test` exit 0), or jfrsort aborts.
- Allocation is **sampled**, not exact: `weight` values are statistical estimates of
  bytes allocated, throttled by JFR. Averaging over N runs reduces the variance; the
  per-run attributed percentage is printed so you can see how much weight had no
  test-class frame (JVM/framework/coverage-agent threads, stacks deeper than 1024
  frames, allocations on threads a test spawned).
- Attribution needs the test class itself on the sample's stack. Allocations made in a
  shared base class that is not itself a discovered test class go to unattributed.
- `jfr print --json` output is held in memory per recording; use small/medium suites.

## Validation

On commons-csv (2 runs, ~90% of sample weight attributed), jfrsort's ranking matches
csto2's MXBean-measured allocation trace: CSVPrinterTest 6.79 GB (JFR) vs 7.18 GB
(MXBean), JiraCsv198Test 45.2 vs 45.4 MB, identical top-allocator order. csto2's
trace additionally contains `perf.PerformanceTest` only because its test discovery
bypassed the pom's Surefire excludes; jfrsort runs plain `mvn test`, which honors them.

See `DECISIONS.md` for the logged measurement decisions.
