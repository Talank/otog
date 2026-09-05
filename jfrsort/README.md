# jfrsort

Sorts a Maven project's test classes by JFR-measured metrics. The only metric today is
`alloc` (estimated allocated heap bytes per test class); the output order is a stable
sort by the metric, descending, averaged over the collected runs.

## Run

```bash
python3 jfrsort.py collect --project <maven module dir> [--runs 3] [--order FILE ...] [--out DIR]
python3 jfrsort.py sort [--out DIR] [--metric alloc]
```

`collect` runs the suite under JFR and stores recordings and build logs; `sort` parses
them and writes the order. `--order` (repeatable) runs the suite in the order given by
a file with one test class per line, through the surefire testorder fork. Other
options: `--mvn BIN`, `--maven-args "..."`, `--jfr-bin BIN`. The Java agent under
`agent/` is built automatically on first use.

## Requirements

- JDK 17+ with the `jfr` CLI on `PATH`; Maven.
- The target suite must be green (build exit 0) and must run its tests through the
  JUnit Platform (JUnit 5, or JUnit 4 via the vintage engine) with Surefire's
  default `useSystemClassLoader=true`.
- For `--order`: the surefire testorder fork installed (`mvn install -DskipTests
  -Drat.skip -Denforcer.skip`) and its `surefire-changing-maven-extension` jar copied
  into the Maven installation's `lib/ext`, as in the fork's README.
- Parallel test execution is not supported.

## Outputs (under `--out`)

- `collect.json` — what was collected: project, runs, order arms.
- `<arm>/run-<i>/` — per run: `jfr/*.jfr`, `mvn.log`, and after `sort`, `metrics.json`.
  Arms are `default`, or one per `--order` file (named by the file's stem).
- `order-alloc-sort.txt` — sorted class list, one per line.
- `metrics.csv` — per class: mean value and the number of runs with samples.

Measurement decisions are logged in `DECISIONS.md`.
