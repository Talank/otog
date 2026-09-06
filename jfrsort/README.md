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

## Example workflow with an outer script

`collect` keeps all runs, thus an outer script can call it many times with its own
orders. This script makes 100 random orders from the class list and collects one run
of each. You can stop the script at any time; the finished runs stay in the directory.

```bash
#!/bin/sh
PROJECT=~/Development/Research/commons-csv
OUT=./csv

# One default-order run gives the class list.
python3 jfrsort.py collect --project $PROJECT --out $OUT --runs 1

# The class list (metrics.csv has one class on each line after the header).
python3 jfrsort.py sort --out $OUT > /dev/null
CLASSES=$(cut -d, -f1 $OUT/metrics.csv | tail -n +2)

for i in $(seq 1 100); do
    echo "$CLASSES" | sort -R > /tmp/order-$i.txt
    python3 jfrsort.py collect --project $PROJECT --out $OUT --runs 1 --order /tmp/order-$i.txt
done

python3 jfrsort.py sort --out $OUT
```

`--random K` is a macro for this workflow: `collect` makes the K random orders itself
and runs each of them as with `--order`. It saves each order as
`<out>/orders/random-<k>.txt` and also copies it to `<out>/random-<k>/run-<i>/order.txt`.

## The first run

jfrsort has no class scanner. It reads the class list from the recording of a run,
thus the output directory must have at least one run before `--random` can make an
order. If the directory is empty, `collect --random` does one run in the default order
first. Any run gives the class list; the order of that run is not important.

`sort` uses the order of the earliest run as the initial order. The sort is stable,
thus classes with equal values keep the initial order.

## Options of `collect`

| Option | Description |
|---|---|
| `--project DIR` | The Maven module directory. Required. One output directory holds one project. |
| `--out DIR` | The output directory. Default: `.jfrsort`. |
| `--runs N` | The number of repeats of each order. Default: 3. |
| `--order FILE` | A test order to run: one fully qualified test class on each line. You can give this option more than one time. |
| `--random K` | A macro: `collect` makes K random orders from the class list, saves them as `<out>/orders/random-<k>.txt`, and runs each of them `--runs` times, as if you gave K `--order` files. The class list comes from an existing run; if the directory has no run, `collect` does one default-order run first. |
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
| `orders/random-<k>.txt` | The random orders that `--random` made (one class on each line). |
| `order-alloc-sort.txt` | The sorted list of test classes, one on each line. |
| `metrics.csv` | The mean value of each test class and the number of runs with samples. |

An arm is `default`, the stem of an `--order` file, or `random-<k>`.

The file `DECISIONS.md` records the measurement decisions.
