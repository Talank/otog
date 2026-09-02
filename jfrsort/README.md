# jfrsort

Sorts a Maven project's test classes by JFR-measured metrics. The only metric today is
`alloc` (estimated allocated heap bytes per test class); the output order is a stable
sort by the metric, descending, averaged over N profiled `mvn test` runs.

## Run

```bash
python3 jfrsort.py --project <maven module dir> [--runs 3] [--out DIR]
```

Options: `--metric alloc`, `--out DIR` (default `.jfrsort`), `--mvn BIN`,
`--jfr-bin BIN`, `--maven-args "..."`. The Java agent under `agent/` is built
automatically on first use.

## Requirements

- JDK 17+ with the `jfr` CLI on `PATH`; Maven.
- The target suite must be green (`mvn test` exit 0) and must run its tests through
  the JUnit Platform (JUnit 5, or JUnit 4 via the vintage engine) with Surefire's
  default `useSystemClassLoader=true`.
- Parallel test execution is not supported.

## Outputs (under `--out`)

- `order-alloc-sort.txt` — sorted class list, one per line.
- `metrics.csv` — per class: mean and per-run values.
- `run-<i>/` — per-run raw data: `metrics.json`, `mvn.log`, `jfr/*.jfr`.

Measurement decisions are logged in `DECISIONS.md`.
