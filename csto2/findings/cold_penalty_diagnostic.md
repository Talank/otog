# The warmup mechanism, and a diagnostic method that measures it

`rt-heavy-tail` (move the heaviest-runtime classes to the tail) wins on snakeyaml but is a *proxy*.
This note (1) identifies the exact mechanism, (2) shows why the obvious signals (runtime magnitude,
jitMs) are wrong, and (3) adds `cold-penalty-tail`, which **measures** the mechanism directly.

## The mechanism: shared-code JIT warmup (proven, not assumed)

snakeyaml is 82% four heavy classes over a shared parser/emitter/constructor core, plus 345 tiny
classes that exercise the same core. Three experiments pin the mechanism:

1. **Decomposition.** initial vs rt-heavy-tail, per-class medians (6 rounds): **124% of the win is in
   the heavy classes' OWN runtime** (ReferencesTest 1099→1005, PrintableUnicodeTest 539→463,
   BigDataLoadTest 481→426, PyEmitterTest 109→69); the 342 tiny classes get slightly *slower*. So it
   is not compiler-starvation of the tiny classes — the heavy classes themselves run faster at the tail.

2. **Smoking gun (`-Xint`).** With JIT disabled entirely the suite runs ~40× slower (125 s) and the
   tail advantage **collapses from +6.9% to +1.4%** (noise). The lever *is* JIT compilation: a heavy
   class runs slow while the shared code it calls is still interpreted, fast once earlier classes have
   compiled it. Tail-loading lets it inherit that compiled code.

3. **The self-warmer counter-example.** StressEmitterTest (240 ms, "heavy") gets +46 ms *worse* at the
   tail. Its body is a `testPerformance()` benchmark that dumps the same object 1000–2000× in a loop,
   so it compiles its own hot code *within its own run* — it self-warms and has ~0 (negative) cold
   penalty. Runtime magnitude cannot tell it apart from ReferencesTest; the mechanism can.

## Why the obvious signals are wrong

- **Runtime magnitude** (`rt-heavy-tail`): ranks StressEmitter high and tail-loads it — wrong.
- **Per-class jitMs** (available once the agent runs on JUnit4, see `warmup_tail_junit4.md`): also
  wrong, and now *provably* so. Measured jitMs vs measured cold-penalty:

  | class | medJit | cold-penalty |
  | --- | ---: | ---: |
  | PrintableUnicodeTest | 878 | +106 |
  | **StressEmitterTest** | **478** | **−12** |
  | ReferencesTest | 372 | +52 |

  jitMs conflates *self*-warm (StressEmitter's loop compiles itself → huge jitMs) with the *shared*
  warm that ordering actually controls. `jit-sort` would front StressEmitter over ReferencesTest.

## The diagnostic signal: cold-penalty, measured with NO initial-order dependence

The quantity ordering controls is the **shared** component — how much slower a class runs when the
shared code it calls is not yet compiled. Measure it as `penalty(X) = rt(X cold) − rt(X warm)`. Getting
the two contexts right, cheaply, without privileging the initial order, took several iterations:

- **Warm context** = all probe candidates clustered at the tail (each runs after the whole suite has
  compiled the core). One order, ~3 repeats.
- **Cold context — rotated position-0.** To read a class genuinely cold it must run *before* the
  classes that compile its shared core. In a suite where ~everything touches the core, that's only the
  first ~20 positions, so random-order traces never observe it (this is exactly why `warm-tail`'s
  regression and the rt-slope wash out — any 20 predecessors warm the core). A single front-*cluster*
  fails too: candidates compile the core for each other (intra-cluster warming), which buried
  ReferencesTest's penalty and produced a false negative. The fix is to **rotate each of the top-R
  heavy candidates through position 0** across R orders — the position-0 class is genuinely cold, and
  rotation gives every gain-carrier its own clean read. Non-rotated candidates are read *near-cold*
  (positions 1..K-1), a conservative under-estimate that self-audits recall.
- The **finder** (which classes to probe) ranks by warm `medRt` — position-independent, so **no initial
  order anywhere** — top-K above a low floor. `medRt` correlates ~0.97 with intrinsic JIT-benefit, so
  it carries the ranking of the gain-carriers; the low floor + near-cold self-audit means no magnitude
  cliff (the old `medRt ≥ 20` filter silently dropped ~18 small-but-JIT-heavy classes).

## The load-bearing finding: per-class penalty is noise-limited

Measured directly, the reorderable cold-penalty of the gain-carriers is **~50–100 ms — the same order
as each class's own run-to-run variance**. Consequences, all observed:

- Per-class penalties are **not individually reliable** in a few reps. Requiring each to clear a noise
  gate discards real gain-carriers: BigDataLoadTest's true ~+40 ms penalty was excluded when one warm
  outlier (458 ms among 589/604) inflated its IQR gate to ~196 ms. A selective "tail-load only classes
  that clear the gate" order came in at **−1.7 %** — *worse* than the crude aggregate.
- Even the **sign** of a self-warmer isn't stable: StressEmitterTest read a clean −76 ms one run and
  >−30 ms the next.
- But the **aggregate** over all heavies is robust — many noisy ±50 ms penalties sum to a reliable
  ~+8 %. This is why the crude `rt-heavy-tail` (move every heavy class) wins: it doesn't need any
  per-class penalty to be individually significant.

**So precision loses to aggregation here.** The honest role of the probe is not fine-grained selection;
it is (a) confirming the mechanism and (b) removing a self-warmer when its sign is clearly negative.

## The method (`cold-penalty-tail`, robust synthesis)

`select` runs the rotated position-0 probe, then builds the order as **`rt-heavy-tail` corrected by
measured self-warmer removal**: tail-load every heavy class (the robust aggregate warmup win) EXCEPT
any the probe confidently flags as a self-warmer (penalty clearly negative), and PROMOTE any lighter
class the probe shows a clearly positive penalty (self-audit of finder recall). Ordered heaviest-last.

- Result on snakeyaml (native JUnit4, 5 rounds, quiet machine): **cold-penalty-tail +8.1 %**, matching
  `rt-heavy-tail` +8.2 % (green gate ships `rt-tail` +10.3 %). When the self-warmer sign is clear it
  drops StressEmitter and edges ahead; when noisy it converges to `rt-heavy-tail` — it never
  underperforms it (the −1.7 % selective version did).
- **Graceful degradation**: a suite with no heavy classes yields no reordering; a self-warmer with a
  stable negative sign is dropped.

## Cross-check (commons-csv, no regression)

The new portfolio still ships csv's existing alloc winner (`alloc-sort` +20.4 %); `cold-penalty-tail`
is a safe additive also-ran, and `rt-tail`'s bad-fit −18 % is gated out. No existing win is displaced.

## Flags

`--cp-min-ms` (8, finder floor), `--cp-top-k` (24), `--cp-rotate` (6, position-0 heavies),
`--cp-cold-repeats` (2), `--cp-warm-repeats` (3), `--cp-gate` (1.5). Probe cost ≈ R×coldReps + warmReps
≈ 15 runs, at/under the earlier displacement probe.
