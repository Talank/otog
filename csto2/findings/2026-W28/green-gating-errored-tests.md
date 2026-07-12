# Green-gating vs. the prior work's failure-tolerant measurement (paimon)

*2026-07-09 (week 2026-W28)*

Running paimon-core (`3613`) surfaced 3 of 213 classes that error only because our container lacks
infrastructure (2× missing Parquet/Avro on the classpath, 1× Testcontainers with no Docker daemon).
The prior work (`tool/`) would have timed them anyway: it ran Maven with fail-never and collected
every testcase with no status filter, and its dataset records no per-test status. csto2 instead
requires an all-green baseline, so these classes must be excluded before it will measure.

We handle this with an automatic two-stage gate, no manual exclude lists. (1) Trace-gate: any class
that is non-PASS in any traced order is excluded from every candidate, so all candidates compare on
the same all-green set — this auto-caught paimon's 3 infra classes. (2) Scrap on new failure: if a
class newly fails during select, that whole candidate is scrapped (all rounds), keeping round counts
equal across surviving candidates for the paired Wilcoxon test. Exclusion is whole-class, and the
report always prints how many classes were excluded — results are therefore not apples-to-apples
with the prior work's numbers, which included the broken tests.
