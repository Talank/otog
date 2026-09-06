# jfrsort

Sorts a Maven project's test classes by JFR-measured metrics. The only metric today is
`alloc` (estimated allocated heap bytes per test class); the output order is a stable
sort by the metric, descending, averaged over the collected runs.

## Run

```bash
python3 jfrsort.py collect --project <maven module dir> [--runs 3] [--order FILE ...] \
                           [--random K] [--seed S] [--clean] [--out DIR]
python3 jfrsort.py sort [--out DIR] [--metric alloc]
```

`collect` runs the suite under JFR and stores recordings and build logs; `sort` parses
them and writes the order. Every `collect` appends to the output directory (run numbers
continue, `collect.json` logs each run), so it can be called repeatedly, e.g. by an outer
script feeding its own orders, and `sort` aggregates everything collected so far;
`--clean` wipes the directory first. `--order` (repeatable) runs the suite in the order
given by a file with one test class per line, through the surefire testorder fork;
`--random K` generates K shuffled orders (from a default-order run, collected first if
needed; `--seed` for reproducibility) and runs them the same way; `--runs` is the number
of repeats per order. Other options: `--mvn BIN`, `--maven-args "..."`, `--jfr-bin BIN`,
`--surefire-ext JAR`. The Java agent under `agent/` is built automatically on first use.

## Requirements

- JDK 17+ with the `jfr` CLI on `PATH`; Maven.
- The target suite must be green (build exit 0) and must run its tests through the
  JUnit Platform (JUnit 5, or JUnit 4 via the vintage engine) with Surefire's
  default `useSystemClassLoader=true`.
- For `--order`/`--random`: the surefire testorder fork installed into `~/.m2`
  (`mvn install -DskipTests -Drat.skip -Denforcer.skip` in the fork); its extension is
  loaded per ordered invocation, so plain builds are unaffected.
- A clean `target/test-classes`: leftovers from other tools (e.g. a `junit-platform.properties`
  with a class orderer) silently override the requested order. `mvn clean` first if in doubt.
- Parallel test execution is not supported.

## Outputs (under `--out`)

- `collect.json` — the project and a log of every collected run (arm, order file, directory).
- `<arm>/run-<i>/` — per run: `jfr/*.jfr`, `mvn.log`, `order.txt` (for ordered runs), and
  after `sort`, `metrics.json`. Arms are `default`, one per `--order` file (named by its
  stem), or `random-<k>`; generated orders are kept under `orders/`.
- `order-alloc-sort.txt` — sorted class list, one per line.
- `metrics.csv` — per class: mean value and the number of runs with samples.

Measurement decisions are logged in `DECISIONS.md`.
