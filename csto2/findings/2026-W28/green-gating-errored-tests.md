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

## What we did — the automatic gate (revised after researcher feedback)

The first cut was a strict green gate + **manual** per-project excludes (add the 3 classes to
`3613.properties`). A fellow researcher pushed back on the strict gate, so we replaced the
manual/strict approach with an **automatic two-stage gate** — no per-project exclude curation:

1. **Trace-gate (before select).** The trace phase now runs all 6 orders even if some classes fail
   (calibration, not a pass/fail decision). Any class that is non-PASS in **any** of those orders is
   collected and **excluded from every candidate order** in select — so all candidates are compared on
   the same all-green class set. This auto-caught paimon's 3 infra classes; no `exclude =` line needed.
2. **Scrap on new failure (during select).** If a class that passed in trace **newly fails** in some
   candidate's order during select, we **scrap that whole candidate** (all rounds) and purge its rows
   from `measure.jsonl`. We do *not* try to retro-exclude the class from the other candidates'
   already-measured rounds — that would need a whole extra measurement pass, which is exactly what we're
   avoiding. This includes `initial`: if the baseline newly fails, it's scrapped and the run reports "no
   baseline to rank against" rather than aborting.

**Why scrap the whole candidate, not just the failing round** (researcher's call): every surviving
candidate must have the **same round count** for a fair paired (Wilcoxon) comparison, and **a test that
failed once is very likely to fail again**, so its remaining rounds would be scrapped anyway. Keeping a
candidate with fewer rounds would bias the paired test.

**Granularity:** exclusion is **whole-class**, not per-method — csto2 orders and measures whole test
classes (per-class Surefire reports), so a class with one failing method is dropped whole. Per-method
exclusion would need surefire `excludedTests` plumbing and per-method measurement; not done.

**Reporting:** the end-of-run report prints an `=== EXCLUSIONS SUMMARY ===` with **how many classes
were excluded** and the split (pre-configured vs auto-excluded during trace), and every failing/scrapped
class is logged to stdout **as it happens** — so if a flood of tests is failing early you can see it and
stop the run before the long select phase.

This measures a subset when tests are excluded, so results are **not apples-to-apples** with the prior
work's numbers (which included broken tests) — but the count of exclusions is always reported.

## Open question (unresolved)

Excluding tests still might not be the best call. It's only a few tests here, but we then optimize a
slightly different suite than the one that "officially" defines the project, and the line between
"legitimately infra-dependent" and "inconveniently failing" is a per-case judgment. I still think
**gating is the right default** — an untrustworthy baseline poisons every speedup — so unless someone
has a better idea, the working policy is: **automatically exclude tests that fail in our environment
(trace-gate), scrap candidates that newly fail, and always report the exclusion count.**

Alternatives considered and why not (yet):
- *No gate at all (match the prior work)* — no; a shipped order that silently broke/dropped tests isn't
  a real win. The gate is the basis of csto2's trustworthiness.
- *Make the tests actually pass* — add Parquet/Avro to the classpath (maybe feasible), but
  Testcontainers needs Docker-in-Docker, which isn't practical in this image (they'd pass on the real
  ubuntu-latest runner, which has Docker).
