# jfrsort

jfrsort sorts the test classes of a Maven project by a metric that Java Flight
Recorder (JFR) measures. The metric `alloc` is the number of heap bytes that each
test class allocates. The output is the list of test classes in descending order of
the mean metric over all runs.

The recordings come from the tool in `../tool`. The tool runs the suite in a
container with the agent in `../tool/agent` attached. The agent writes one JFR event
for each test class, spanning the class's execution. `sort` gives each metric event
to the test class whose time window contains it.

## Example

```bash
# On the machine that ran the experiment: the recordings of one module version.
python3 ../tool/scripts/export_jfr.py ../tool/runs/1685/0 exports/1685/0

# On any machine with JDK 17 or later.
python3 jfrsort.py sort --out exports/1685/0
```

## Options of `sort`

| Option | Description |
|---|---|
| `--out DIR` | The directory that `export_jfr.py` wrote. Default: `.jfrsort`. |
| `--metric NAME` | The metric to sort by. Default and only value: `alloc`. |
| `--jfr-bin BIN` | The `jfr` binary. Default: `jfr`. |
| `--jobs N` | The number of recordings parsed in parallel. Default: the number of CPUs. |

## The metric

`alloc` is the sum of two JFR events inside the class window: the size of each
buffer that a thread receives (`jdk.ObjectAllocationInNewTLAB`, field `tlabSize`)
and the size of each object too large for a buffer (`jdk.ObjectAllocationOutsideTLAB`,
field `allocationSize`). The sum is a measured amount, rounded to whole buffers at
the edges of the window. The two events exist on every JDK from 8 on.

## The input directory

| File | Content |
|---|---|
| `collect.json` | The list of runs. Each run has a `dir`, relative to the directory. |
| `<run dir>/jfr/*.jfr` | The recordings of one run. A recording without test class events, for example the Maven JVM, is skipped. |
| `<run dir>/order.txt` | The test order of the run, if it had one. |

`sort` uses the order of the first run in the list as the initial order. The sort is
stable, thus classes with equal values keep the initial order.

## Output files

| File | Content |
|---|---|
| `<run dir>/metrics.json` | The per-class values of one run, and which events supplied them. |
| `order-alloc-sort.txt` | The sorted list of test classes, one on each line. |
| `metrics.csv` | The mean value of each test class and the number of runs with samples. |

## Requirements

- JDK 17 or later, with the `jfr` tool on `PATH`, to read the recordings.
- The recorded suite ran its tests through the JUnit Platform (JUnit 5, or JUnit 4
  through the vintage engine), one test class at a time. Tests that run in parallel
  are not supported.

The file `DECISIONS.md` records the measurement decisions.
