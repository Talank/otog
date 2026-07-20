# Sort-granularity experiment (Docker, through Surefire)

Measures how the **sort level** (package / class / method), sorting tests by allocation, changes suite
wall-clock. Runs entirely through Maven Surefire and the testorder fork, so timing, JVM flags, and
single-fork carryover match a real `mvn test`.

## The seven arms

Every arm keeps a class's methods contiguous (no cross-class interleaving). They differ only in class
order and intra-class method order:

| arm | packages sorted | classes sorted | methods sorted |
| --- | --- | --- | --- |
| initial | – | – | – |
| mth | – | – | ✓ (within class) |
| pkg | ✓ | – | – |
| pkg-cls | ✓ | ✓ (within package) | – |
| pkg-cls-mth | ✓ | ✓ (within package) | ✓ |
| cls | – (global) | ✓ | – |
| cls-mth | – (global) | ✓ | ✓ |

Method-level arms need the surefire fork's method-order commit (a Jupiter `MethodOrderer` that honors
`-Dtest` method order on JUnit 5). The base image must be built from that fork.

## Run

```bash
# builds base (csto2-runner) from ../docker_template if missing, then the sort image, then runs each ID
./run.sh --build-base --rounds 10 1683 1685 3613 1778
tail -f results_sort_1685/run.log
```

Results land in `results_sort_<ID>/`: `summary.txt` (Wilcoxon per arm vs initial), `results.tsv`
(raw per-round timings), `orders/` (the seven order files), `alloc.jsonl` (per-method allocation
trace), `excluded.txt` (classes dropped by the green gate).

## How it works (entrypoint.sh)

1. Clone, checkout, build the module with its configured JDK.
2. `csto2 project` / `discover` produce the classpath and csto2's test suite.
3. Compile `MethodAllocListener` into `target/test-classes` with a `META-INF/services` entry — the
   JUnit Platform auto-discovers it, so one Surefire run records per-method allocation.
4. `gen_orders.py` builds the seven order files from that allocation.
5. Green gate: run `initial` once; drop any class that fails from every arm (same all-green set).
6. Measure `ROUNDS` rounds x 7 arms, arm order shuffled each round, agent off.
7. `analyze.py` reports the paired Wilcoxon result.

## Cost

Per-run wall-clock roughly matches the module's `mvn test`. A full 10-round, 7-arm run is ~70 suite
runs plus one trace:

| ID | module | ~1 suite run | ~full run (10 rounds) |
| --- | --- | --- | --- |
| 1685 | javaparser-core-testing | 15 s | ~20 min |
| 1683 | javaparser-symbol-solver | 35 s | ~45 min |
| 1778 | spring-ai-openai | ~1 min | ~1.5 h |
| 3613 | paimon-core | ~18 min | ~21 h |

paimon is very expensive; lower its rounds with `--rounds 4` if needed. Each module is independent, so
launch them in parallel.

## Notes

- Uses csto2's suite (reflection discovery, which includes `@SlowTest` classes), matching the
  numbers in `csto2/findings/speedups.md`. This is not identical to what `mvn test` runs.
- The trace listener records allocation across all threads (some tests allocate on worker pools).
  It runs only during the trace, never during a timed round.
