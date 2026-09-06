# jfrsort

jfrsort sorts the test classes of a Maven project by a metric that Java Flight
Recorder (JFR) measures. The metric `alloc` is the estimated number of heap bytes that
each test class allocates. The output is the list of test classes in descending order of
the mean metric over all collected runs.

## Example

```bash
# Collect three runs in the default order, then sort.
python3 jfrsort.py collect --project ~/Development/Research/commons-csv --out ./csv
python3 jfrsort.py sort --out ./csv

# Add ten runs in random orders to the same directory, then sort again.
python3 jfrsort.py collect --project ~/Development/Research/commons-csv --out ./csv --random 10 --runs 1
python3 jfrsort.py sort --out ./csv
```

Each `collect` adds runs to the output directory. `sort` uses all runs in the directory.

## Options of `collect`

| Option | Description |
|---|---|
| `--project DIR` | The Maven module directory. Required. One output directory holds one project. |
| `--out DIR` | The output directory. Default: `.jfrsort`. |
| `--runs N` | The number of repeats of each order. Default: 3. |
| `--order FILE` | A test order to run: one fully qualified test class on each line. You can give this option more than one time. |
| `--random K` | Make K random orders from the class list and run each of them `--runs` times. If the directory has no default-order run, `collect` does one first to get the class list. |
| `--seed S` | The seed for `--random`. Default: a random seed, which `collect` prints. |
| `--clean` | Delete the output directory before you collect. |
| `--mvn BIN` | The Maven binary. Default: `mvn`. |
| `--maven-args "..."` | Extra arguments for the `mvn` command line. |
| `--surefire-ext JAR` | The extension jar of the surefire testorder fork. Default: the newest jar in `~/.m2`. |
| `--jfr-bin BIN` | The `jfr` binary. Default: `jfr`. |

## Options of `sort`

| Option | Description |
|---|---|
| `--out DIR` | The output directory that `collect` filled. Default: `.jfrsort`. |
| `--metric NAME` | The metric to sort by. Default and only value: `alloc`. |
| `--jfr-bin BIN` | The `jfr` binary. Default: `jfr`. |

## Requirements

- JDK 17 or later, with the `jfr` tool on `PATH`, and Maven.
- The test suite must be green. The tests must run through the JUnit Platform (JUnit 5,
  or JUnit 4 through the vintage engine) with the Surefire default
  `useSystemClassLoader=true`.
- For `--order` and `--random`: the surefire testorder fork must be installed in `~/.m2`
  (`mvn install -DskipTests -Drat.skip -Denforcer.skip` in the fork).
- The directory `target/test-classes` of the project must be clean. Files from other
  tools, for example a `junit-platform.properties` with a class orderer, change the
  test order. Run `mvn clean` if you are not sure.
- Tests that run in parallel are not supported.

## Output files

| File | Content |
|---|---|
| `collect.json` | The project and a record of each collected run. |
| `<arm>/run-<i>/jfr/*.jfr` | The JFR recordings of one run. |
| `<arm>/run-<i>/mvn.log` | The Maven log of one run. |
| `<arm>/run-<i>/order.txt` | The test order of one run, if the run had an order. |
| `<arm>/run-<i>/metrics.json` | The per-class values of one run. `sort` writes this file. |
| `orders/random-<k>.txt` | The orders that `--random` made. |
| `order-alloc-sort.txt` | The sorted list of test classes, one on each line. |
| `metrics.csv` | The mean value of each test class and the number of runs with samples. |

An arm is `default`, the stem of an `--order` file, or `random-<k>`.

The file `DECISIONS.md` records the measurement decisions.
