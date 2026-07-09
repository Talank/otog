# commons-text: the "~0 improvement" was a kill-9 fork-truncation artifact

*2026-07-09 (week 2026-W28)*

commons-text appeared to have **no orderable headroom**: the shipped winner was `naive` at +13.9% vs
initial (a *free* baseline, not an optimizer win), and every engineered strategy landed at or below it.
The earlier statistical re-test (with `TextStringBuilderTest` excluded as a workaround) put the naive
"win" at only +1.7% (p=0.067, not significant). Both readings were wrong for the same reason.

## Root cause

`TextStringBuilderTest.testEnsureCapacityOutOfMemoryError()` does
`assertThrows(OutOfMemoryError.class, () -> sb.ensureCapacity(Integer.MAX_VALUE))` — a **legitimately
green** test that provokes and catches an expected OOM. But the testorder fork ran with
`-XX:OnOutOfMemoryError=kill -9 %p`, which fires the instant the OOM is *constructed*, before
`assertThrows` can catch it, and kill-9's the single reused fork.

Whatever position that class occupied in an order, the classes before it reported PASS and
**everything after silently vanished** — no FAIL, just missing Surefire reports. So an order's measured
total was really *"time to run however many classes precede the killer."* Front-loading heavy
allocators moved the killer earlier → fewer classes ran → smaller total → a **phantom speedup**.

The smoking gun: in the old runs `naive.order` was byte-identical to `initial.order`, yet "won" +13.9%.
An order cannot beat itself; the delta was pure truncation noise (kill-9 timing). Excluding
`TextStringBuilderTest` dodged the kill but discarded a real, compute-heavy class, leaving no
exploitable signal (+1.7%, p=0.067) — masking, not fixing, the problem.

## Fix (both sides)

1. **Surefire fork** (`Archonic944/maven-surefire`, `modifiedRunOrder-ext`): drop
   `-XX:OnOutOfMemoryError=kill -9 %p` from the fork argLine, so a caught OOM no longer nukes the JVM.
   Stock Surefire handles OOMs without it.
2. **csto2 completeness gate**: `SurefireOrchestrator.runOrder` reconciles the requested class set
   against produced reports and emits a `status:"MISSING"` non-PASS sentinel for any class with no
   report; `select` throws `OrderFailedException` and disqualifies any incomplete/truncated order. A
   crashed fork can no longer pass the green gate as a fast win, on any subject.

Verified: the full 100-class order now runs to completion — all green, `TextStringBuilderTest` reports,
mvn exit 0, no kill-9.

## Re-measurement (full suite, 10 paired rounds vs `initial`, agent off)

| Strategy | Median initial | Median winner | Δ median | p-value (exact) | Significant? |
| --- | --- | --- | --- | --- | --- |
| jit-sort | 17370 ms | 15131 ms | +12.9% | 0.0020 | Yes — W+=55, W−=0 (every round favored it) |
| alloc-sort | 17370 ms | 15468 ms | +12.0% | 0.0020 | Yes — W+=55, W−=0 |
| naive | 17370 ms | 16031 ms | +7.7% | 0.0137 | Yes |

`jit-sort` and `alloc-sort` each **beat the free `naive` baseline** (jit-sort +5.6%, alloc-sort +3.5%
median) — a genuine optimizer win, not just a naive win. commons-text is both JIT- and alloc-heavy, so
the two are within noise of each other. Result: commons-text moves from "no headroom" to a robust
statistically-significant ~12–13%.

## Gotcha when reproducing

Clear any stale `skip-candidates` (`config.properties` + `skip-candidates.txt`). A pre-fix session had
disabled `alloc-sort`/`jit-sort`/`pkg-*`/etc.; leaving that list in place suppresses the actual winners
and reproduces a fake ~0. Also note this 10-round run restricted candidates to `alloc-sort`/`jit-sort`
(initial/naive are protected) — a full-portfolio pass may find more.
