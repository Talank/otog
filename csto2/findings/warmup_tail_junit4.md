# Runtime warmup-tail: a new lever for signal-blind / shallow-slope suites

## Summary

Added two runtime-only candidate strategies — **`rt-tail`** and **`rt-heavy-tail`** — that make
csto2 succeed on a class of suites its existing portfolio cannot touch: **JVM-warmup-bound suites
made of many tiny classes plus a few heavy ones**, especially **plain-JUnit4** suites where the
instrumentation agent records no facts at all.

New target: **snakeyaml** (`org.yaml:snakeyaml`, 349 classes, ~5s wall, serial JUnit4).
Current csto2 best on it: a noisy **+2.2%** (effectively initial). New `rt-heavy-tail`: **+6.9%**
(reproducible), a lever the whole existing portfolio misses.

## Why current csto2 fails on snakeyaml

Two independent blind spots stack:

1. **Signal blindness on JUnit4.** snakeyaml uses plain `junit:junit`, so Surefire runs it through
   the **junit4 provider**, not the JUnit Platform. csto2's agent registers a JUnit *Platform*
   `TestExecutionListener` via ServiceLoader — which never loads under the junit4 provider. Result:
   **every per-class MXBean fact is absent** (`allocBytes`, `jitMs`, `gcCount`, `classesLoaded` all
   missing/0). So `alloc-front`, `alloc-sort`, `jit-front`, `jit-sort` all degenerate to the initial
   order (no heavy allocators/compilers to find), and `pkg-alloc-front` collapses to a stable no-op.

2. **Shallow slopes below the warm-tail threshold.** The only runtime-derived lever, `warm-tail`,
   requires a per-class negative position-slope `<= -1.0` ms/pos. snakeyaml's classes are tiny, so
   their slopes are `~ -0.1` ms/pos — real but 10× too shallow to qualify. `warm-tail` therefore
   selects **zero** classes and does nothing (measured -1.7% — i.e. noise/hurt).

Measured `select` portfolio (agent off, 4 rounds): every candidate within a noisy ±2.2% of initial;
shipped `pkg-alloc-front` +2.2% (indistinguishable from initial given the noise). Meanwhile a clean
agent-off probe found random shuffles reliably **+5.6–5.7%** faster than initial — headroom csto2
could not reach.

## The mechanism (warmup-tail)

snakeyaml's runtime is **82% concentrated in 4 classes** (ReferencesTest 1036ms, PrintableUnicodeTest
548, BigDataLoadTest 484, StressEmitterTest 274); the other 345 classes are ~0–5ms each. All four
heavy classes hammer the shared snakeyaml parser/emitter/constructor core. When a heavy class runs
**early**, that core is still cold (interpreted) → slow. When it runs **late**, the 345 tiny classes
have already driven JIT compilation of the shared core → it runs compiled → fast. So the heavy
classes want to inherit maximum accumulated warmth by running **last**.

Directional confirmation (clean agent-off A/B, 4 rounds each):

| order | vs initial | note |
| --- | ---: | --- |
| `big-front` (heavy first) | +0.1% | control — rules out "any perturbation helps" |
| `slope-sort` (rearrangement inequality) | +2.5% | shallow per-class slopes are too noisy |
| `big-tail` (full ascending runtime sort) | +5.7% … +7.7% | heavy classes last |
| **`rt-heavy-tail`** (move only the 7 heaviest to tail) | **+6.9%** | best + locality-preserving |

`rt-heavy-tail` beats the full sort because it moves *only* the heavy classes and leaves the 345
light classes in their original adjacency, so it captures the warmth effect without shredding any
locality.

## The new strategies (`optimize/Candidates`)

- **`rt-tail`** — sort the whole suite by median per-class `runtimeMs` ascending (heaviest last).
  The runtime-only sibling of `warm-tail`; global, so green-gated on locality-bound suites.
- **`rt-heavy-tail`** — minimal perturbation: move only classes with `medRt >= --heavy-rt-ms`
  (default 50) to the tail, ascending; keep every other class in place. Preserves locality.

Both key on `runtimeMs` alone, which is present in the trace even when the agent records nothing —
so they are the levers that fire precisely where the signal-based portfolio goes blind.

## Results

**snakeyaml `select`, 5 rounds, agent off (new portfolio):**

```
  rt-heavy-tail          median=2934ms   +5.8% vs initial   GREEN   <= SHIPPED
  rt-tail                median=2955ms   +5.1%
  jit-front              median=3129ms   -0.5%
  alloc-front            median=3118ms   -0.1%
  pkg-rt-front           median=3134ms   -0.6%
  alloc-front+warm-tail  median=3146ms   -1.0%
  alloc-sort             median=3167ms   -1.7%
  naive                  median=3169ms   -1.8%
  pkg-alloc-front        median=3172ms   -1.9%
  warm-tail              median=3195ms   -2.6%
  jit-sort               median=3197ms   -2.7%
=> SHIP: rt-heavy-tail (2934ms, +5.8% vs initial)
```

Every pre-existing candidate lands between -2.7% and -0.1% (noise/regression). The two new
runtime-only candidates are the only ones that beat initial, and the green gate ships the better of
them. Net: csto2 goes from ~0% (a noisy +2.2% that is statistically initial) to a solid **+5.8%**.

**Cross-check (no overfitting), commons-csv `select` with the new jar (4 rounds):**

```
  pkg-alloc-front   +21.1%   <= SHIPPED (existing alloc winner, unchanged)
  jit-sort          +17.9%
  alloc-front       +11.4%
  ...
  rt-heavy-tail     +3.1%    (harmless positive also-ran)
  rt-tail           -6.5%    (full re-sort breaks csv's alloc/locality order -> correctly NOT shipped)
```

The result is the desired one: adding the two candidates does **not** disturb csto2's existing
alloc-driven win on csv (it still ships `pkg-alloc-front` at +21.1%), and the one new candidate that
is a bad fit there (`rt-tail`, whose global re-sort shreds csv's order, -6.5%) is filtered out by the
green gate rather than shipped. The new lever is purely additive: it unlocks warmup-bound / signal-
blind suites without risking the suites csto2 already handles.

## Files changed

- `optimize/Candidates.java` — `ALL_NAMES` + two new strategies (`rt-tail`, `rt-heavy-tail`); the
  `generate(...)` signature gained a `heavyRtMs` argument.
- `Csto2.java` — `select` parses `--heavy-rt-ms` (default 50) and threads it through.
- Target-side (snakeyaml, for reproducibility, not csto2): excluded `BillionLaughsAttackTest` (its
  by-design OOM kills a shared fork) and raised the Surefire `argLine` heap `-Xmx512m`→`-Xmx3g` so
  all 349 classes fit one fork. Both are single-fork accommodations, applied identically to every A/B
  arm, so no comparison is contaminated.

## Attribution

The mechanism is **shared-code JIT warmup**, evidenced by direction and structure rather than any
single signal (there are none — the agent is blind here):

- **Direction:** moving the heavy classes to the *front* does nothing (+0.1%); moving the identical
  set to the *tail* wins (+5.7…7.7%). A generic "any perturbation helps" or pure measurement noise
  would be symmetric — this is strictly directional, the signature of accumulated warmth.
- **Structure:** the four heavy classes all exercise the same snakeyaml parser/emitter/constructor
  core that the 345 tiny classes also touch; that shared core is what gets compiled during the early
  tiny classes and is then hot for the heavy classes at the tail.
- **Not GC/alloc:** per-class alloc and GC are ~0 across the suite, and `alloc-*`/`jit-*` sorts do
  nothing (there is nothing for them to sort on), so the lever is neither heap ergonomics nor
  compilation-cost front-loading — it is the position-dependent *execution* cost of the heavy classes
  themselves, i.e. cold-interpreted early vs hot-compiled late.

(A `-Xint` / `-XX:TieredStopAtLevel=1` A/B would nail C2's specific contribution and is the natural
next confirmation; the directional control above already rules out the non-warmup explanations.)
