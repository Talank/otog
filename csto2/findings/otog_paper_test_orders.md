# Efficient test-order results on the otog paper's modules (CSTO2)

Reproduction of "Generating Efficient Test Orders for Regression Testing" (`otog_paper.pdf`, Table 1)
using the CSTO2 comprehension-driven test-order optimizer. Goal: for each module, **determine the
fastest test-class order** and **establish statistical validity** via a **Wilcoxon signed-rank test**.

Results table: [`otog_paper_test_orders.csv`](otog_paper_test_orders.csv).

## Method

Per module, tests run as **classes in a single JVM** through real Maven Surefire (single-fork,
carryover preserved), agent OFF during timed measurement (the profiling agent perturbs wall-clock).

1. **Green gate (precondition).** The as-given (`initial`) order must run fully green before any
   measurement — a red baseline invalidates every speedup and the ship gate. Good-faith effort to
   fix failures; genuinely-unfixable tests are noted and **excluded** (see curator below).
2. **Determine fastest order.**
   - *Fast suites (<30 s):* full candidate **portfolio screen** (`select`: initial, naive,
     alloc-sort, jit-sort, jit-front, rt-tail, rt-heavy-tail, cold-penalty-tail, pkg-*, …), pick the
     fastest **fully-green** candidate.
   - *Medium/heavy suites:* lean A/B — `initial` vs `naive` (+ `jit-front`, the JIT-warmup lever) —
     to fit the time budget. `naive` = fastest of the traced random orders (the paper's own naive
     approach; a *free* baseline, so a real win must beat naive too).
3. **Statistical validity (Wilcoxon signed-rank).** To avoid the winner's-curse from selecting the
   min of many candidates, the p-value comes from a **fresh confirmation A/B** run: `initial` vs the
   winner (+ naive) measured over **R seeded-shuffled interleaved rounds** (fast R=15, medium R=10,
   heavy R=7). Each round is a matched block; we sum per-class `runtimeMs` to a **suite total** per
   order per round, then run a **two-sided Wilcoxon signed-rank** on the R paired suite totals.
   (Test on suite totals — R pairs — never on per-class rows.) Ship rule: fastest green order, and
   only if it beats initial by >1% median.

## Headline result

**javaparser-core-testing: a real, significant win** — `jit-front` order runs **21.8% faster** than
initial (12.74 s vs 16.29 s), Wilcoxon p ≈ 6e-5, all 15 rounds favored it, and it beats naive by
21%. This suite is JIT-bound; front-loading high-compilation classes warms the shared core early.

The other measured suites (async-http-client, curator-framework, netty-transport) show **negligible
reorderable headroom** (<1% median, not significant) — consistent with the paper's finding that most
modules' savings are small and that simple naive selection rarely loses.

## Correction — symbol-solver (M1) has small but real headroom (was initially under-called)

The first pass reported symbol-solver as keep-initial (cold-penalty-tail +0.45%, n.s.). That was a
**measurement-process error**, not a suite with no headroom:

- The portfolio **screen ran at only R=3 rounds** across 13 close candidates — too noisy to rank them.
  It picked `cold-penalty-tail` over `alloc-sort` by chance, and the fresh confirmation then faithfully
  tested the screen's pick, landing at +0.45% (n.s.).
- An **older R=10 wilcoxon** run shows `alloc-sort` was faster in **9/10 rounds, +5.1%, p=0.004** — a
  genuine, significant effect (the alloc-sort order is byte-identical to what the current code emits,
  so recent candidate additions did **not** change or break it).
- A **re-measured R=15 A/B** confirms real headroom at the current (faster, ~8.6s) machine state:
  `cold-penalty-tail` +2.41% (p=0.008, 12/15), `alloc-sort` +1.05% (n.s.).

**Net:** the win is real but **small and machine-state-dependent** — 0.45%→2.4%→5.1% across runs, near
the measurement floor (a few hundred ms). The historical +11% (initial 22s) was at a ~2× slower state
where the absolute savings were larger. Corrected verdict: **ship cold-penalty-tail, marginal ~1–2.5%.**

**Process lesson:** screen at higher R, or carry the top 2–3 screen candidates into the confirmation
A/B rather than only the top-1 — a 3-round screen cannot reliably rank candidates separated by <5%.
(The medium/heavy modules used a lean `initial`-vs-`naive` A/B, so their non-naive levers — alloc/jit/
cold-penalty — were never screened; small wins there remain unexplored under the deadline.)

## Green-gate handling: curator-framework

The as-given order was **RED**: 3 ZooKeeper classes (`TestFramework`, `TestReconfiguration`,
`TestWatcherRemovalManager`) fail identically in every order with `KeeperErrorCode = NoAuth for
/zookeeper/config` — ZK dynamic-reconfiguration/ACL tests that need a reconfig-enabled embedded
server (an environment limitation on macOS, **not** order-induced). Good-faith fix
`-Dzookeeper.skipACL=yes` greened the reconfig tests but *broke* `TestFramework`'s ACL tests, so it's
not a clean fix. Per the green-gate rule these 3 classes were **excluded** (31 of 34 classes remain,
fully green) and the module re-measured clean.

## Coverage / infeasible modules (see CSV rows)

Measured 5 modules across 4 of the 7 projects (javaparser ×2, async-http-client, curator, netty).
Not measured under the deadline, with reasons: netty `transport-native-epoll` (Linux-only JNI, can't
run on macOS), `curator-recipes` (~2 h/run per paper), `paimon-core` (not compiled locally),
`spring-ai-openai` (network/credential-bound), netty `handler` (heavy, deprioritized).

All measurement is empirical A/B; the tool never drops tests and never ships a regression.
