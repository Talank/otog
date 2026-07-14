# All Docker runs measured per-class JVMs — no carryover, so no order effect could exist

*2026-07-14 (week 2026-W29)*

Every Docker config's `mvnopts` carried `-DforkCount=1 -DreuseForks=false` (inherited from the prior
researcher's `MVN_OPTS`, whose methodology wanted isolated forks). csto2 threads `mvnopts` into the
measurement `mvn surefire:test`, and the CLI flag overrode the testorder extension's forced single
fork — so every test class ran in a fresh JVM. Cross-class JIT/GC/alloc carryover is the entire
effect csto2 measures; with per-class JVMs all orderings are necessarily identical. This is why
javaparser-core showed +20% natively but exactly 0% in Docker on both the Mac and the x86 box.

Proof: Docker agent facts files contain 1 row per order (each JVM saw one class); native runs show
237 rows with the classic warmup signature. Per-class times ~4× native (each pays its own cold
start); ~50s of per-order wall time was untracked JVM startups.

Fix (verified by injecting the poison flags and observing one-JVM behavior): removed the flags from
all 10 configs; `SurefireOrchestrator.runOrder` now appends `-DforkCount=1 -DreuseForks=true` after
user props (last -D wins) so mvnopts can never break the invariant; a runtime guard warns loudly if
agent rows ≪ order size (fork not reused).

**Consequence: order-comparison numbers produced by the Docker harness before this fix are invalid
for any project whose pom does not pin fork settings** and must be re-measured (the per-class
runtimes themselves are real, just cold-JVM ones).

**Exception — paimon (3613) is unaffected.** Its Flink-derived root pom explicitly configures
`<reuseForks>${flink.reuseForks}</reuseForks>` (= true), and an explicit pom plugin configuration
ignores the CLI `-DreuseForks=false` user property. Its Docker agent facts show 213 rows/order with
the normal warmup signature — real shared-fork carryover — so paimon's +23.6% result stands.

Verified both directions with a controlled A/B on a synthetic project (poison flags injected in
both runs): pre-fix jar -> 7 classes run but 1 agent row (per-class forks, each overwriting the
facts file; surviving row `position:0`, classesLoaded 178); post-fix jar -> 7 rows, one JVM.
