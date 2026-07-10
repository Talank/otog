# Green-gating vs. the prior work's failure-tolerant measurement (paimon)

*2026-07-09 (week 2026-W28)*

Running paimon-core (`3613`) end-to-end surfaced 3 test classes that **error** in our Docker
container, out of 213:

| Class | Failures | Why it errors here |
|-------|---------:|--------------------|
| `iceberg.migrate.IcebergMigrateTest` | 22 | `NoClassDefFoundError: org/apache/parquet/hadoop/api/WriteSupport` — Parquet/Avro not on the test classpath |
| `iceberg.IcebergCompatibilityTest`  | 14 | same (missing Parquet/Avro) |
| `jdbc.PostgresqlCatalogTest`        | 1  | `Could not find a valid Docker environment` — uses Testcontainers, needs a Docker daemon in the container |

The other 210 classes are green (2,349+ real tests pass). These 3 aren't real regressions — they're
tests that need infrastructure a minimal, Docker-less container doesn't have. On the actual
`ubuntu-latest` runner (which has Docker) the Testcontainers one would pass.

## Why this is a decision, not just a config gap

The **prior research (`tool/`) did not green-gate.** Two facts confirm it:

- `scripts/get_test_list.py` collects **every** `<testcase>` from the Surefire reports as
  `classname#method`, with **no filter on pass/fail/error status**.
- The tool ran Maven with `-Dmaven.test.failure.ignore=true -fn` (fail-never), so a build with
  erroring tests still "succeeded" and its runtimes were recorded.

So the prior work **measured the runtime of tests even when they errored** — those broken Iceberg /
Testcontainers classes are present in `tool/`'s measured paimon orders (e.g. `IcebergMigrateTest`,
`PostgresqlCatalogTest`), and there is **no exclude** for any of them (its only hardcoded excludes are
iotdb `ConfigNodePropertiesTest#TrimPropertiesOnly` and curator `TestWatcherRemovalManager`). The
tool's stored dataset (`results/dataset/3613/*.json`) keeps only `test_order` + `module_times` — no
per-test status was ever recorded, so "which tests errored before" isn't recoverable from `tool/`; our
own run is the authoritative source.

csto2 is deliberately stricter: it requires an **all-green baseline** and aborts on any error, because
that green gate is what makes a shipped speedup trustworthy (a fast order that silently dropped or
broke tests is not a win). So the same tests the tool happily timed, csto2 refuses to measure.

## What we did

Green-gate, and **exclude** the 3 infra-dependent classes for `3613` (in `3613.properties`). csto2
then optimizes the ~210 genuinely-green classes. This is consistent with csto2's design and arguably
*more* valid than the paper's numbers, which included broken tests — at the cost of measuring a subset,
so paimon results are **not apples-to-apples** with the prior work's paimon numbers.

## Open question (unresolved)

Excluding tests to satisfy the green gate might not be the best call. It's only a few tests here, but
it means we optimize a slightly different suite than the one that "officially" defines the project, and
the line between "legitimately infra-dependent" and "inconveniently failing" is a judgment call each
time. I still think **green-gating is the right default** — an untrustworthy baseline poisons every
speedup — so unless someone has a better idea, the working policy is: **manually exclude the tests that
don't work in our environment**, documented per subject, rather than relax the gate.

Alternatives considered and why not (yet):
- *Relax the gate to match the prior work* — no; it's the whole basis of csto2's trustworthiness.
- *Make the tests actually pass* — add Parquet/Avro to the classpath (maybe feasible), but
  Testcontainers needs Docker-in-Docker, which isn't practical in this image.
