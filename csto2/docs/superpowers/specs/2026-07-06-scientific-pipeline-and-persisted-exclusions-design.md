# Scientific full-pipeline REPL option + persisted exclusions

Date: 2026-07-06

Two independent changes to `com.csto2.cli.Repl`, shipped as **separate commits**.

## Commit 1 — Persist exclusions to disk (test classes + candidate strategies)

Today two exclusion mechanisms live only in the in-memory `cfg` map and are lost on REPL exit:

- `cfg["exclude"]` — accumulated excluded **test-class** FQCNs (drives `tests.included`).
- `cfg["skip-candidates"]` — disabled **candidate strategy** names (passed to `select` as
  `--skip-candidates`).

Persist both under the base out dir (`<out>`, default `.csto2`):

- `<out>/exclude.txt` — excluded test-class FQCNs, one per line. Rewritten whenever `exclude`
  resolves names (full deduped set, not append-only).
- `<out>/skip-candidates.txt` — disabled candidate strategy names, one per line. Rewritten whenever
  `approaches` toggles the disabled set.

**Auto-load / re-apply.** A `loadPersistedExclusions()` helper runs (a) once at REPL startup and
(b) after a project or test list is (re)loaded (`loadProject`, `discover`):

- Reads `skip-candidates.txt` into `cfg["skip-candidates"]` (intersected with `Candidates.ALL_NAMES`,
  protected names dropped, matching the `approaches` invariants).
- Reads `exclude.txt` and re-applies it to the **current** test list: any listed FQCN present in the
  list is filtered out and a fresh `tests.included` is written with `tests` re-pointed at it. Names no
  longer present are **silently skipped** (the test list can legitimately change between launches — no
  abort, unlike the interactive `exclude` which aborts on any unresolved token). `cfg["exclude"]` is
  set to the union actually applied.

**Reporting.** `state` marks both lines as `(persisted)` when the on-disk files exist.

Writes go through a single `saveExclusions()` / `saveSkipCandidates()` pair so the interactive
`exclude` and `approaches` paths and the auto-loader stay in sync. Files are created lazily (base dir
is created on demand, as elsewhere).

## Commit 2 — Scientific full-pipeline REPL option

New menu item `S) scientific` (protected letter key like `e`/`a`/`p`). It runs the full pipeline with
rigor:

1. `discover → trace → select`, but with `repeats` forced to **10** for the `select` stage (restores
   the user's configured `repeats` afterward so it is a one-shot override, not a config mutation).
2. After `select` writes `<out>/select/measure.jsonl`, run a **Wilcoxon signed-rank test** of the
   shipped winner (and every other green candidate) vs `initial`, paired by round.

### `optimize/WilcoxonSignedRank.java` (new, pure)

- Input: paired samples `initial[r]`, `candidate[r]` for r = 0..n-1 (per-round suite totals).
- Computes signed-rank statistic W on the nonzero paired differences, average-ranking ties.
- Two-sided p-value:
  - **Exact** for small n (nonzero-diff count ≤ 20): enumerate all `2^m` sign assignments over the
    `m` nonzero-difference ranks, count the tail ≥ observed |W_+ − W_−|. At n=10 this is ≤1024 cases.
  - **Normal approximation** with continuity + tie correction for larger n.
- Returns `{ n, wPlus, wMinus, pValue, exact }`. No external deps; standalone `main`-free helper.

### `Csto2.signedRankReport(Path measure, String incumbent)` (new static, package-visible)

- Reuses the same parse as `selectReport`: per `orderId` (`name#r`) sum `runtimeMs` to a round total,
  and track non-PASS counts for the green gate.
- For each **green** candidate ≠ incumbent, pair its round totals with the incumbent's by round index
  and print `W`, `n`, exact/approx flag, two-sided p-value, and median delta.
- `select`'s own default output (`selectReport`) is **unchanged**; the scientific option calls
  `select` then layers this report on top by reading the deterministic `measure.jsonl` path.

The REPL `scientific()` method computes that path as `baseDir().resolve("select/measure.jsonl")`
(matching what `select()` in the REPL passes as `--out`).

## Out of scope / YAGNI

- No change to the non-scientific `full pipeline` (item 8) or to `select`'s default report.
- No new statistical machinery beyond the one paired test requested.
- Method-level exclusions (clarified to mean candidate strategies, already covered above).
