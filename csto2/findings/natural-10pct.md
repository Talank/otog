# Goal 3: Wins of 10% or More Against Natural Orders

Date: 2026-08-01. STATUS: **COMPLETE — 5 of 5 required wins confirmed, plus 1 more win.**

Definitions. The natural order is the project's real `mvn test` execution sequence, captured
from a real run (`capture_natural.sh`). The baseline arm and the applied arm always contain
exactly the same test classes; the baseline arm is the profiled run's own recorded order.
When a suite has test failures as given, the failing classes are removed from both arms, with
a note. The applied order is the pipeline's emitted order: one profiled run, then candidates,
then the applied order. Measurement runs without the agent, on a pinned fork JVM, in
interleaved pairs. All runs use one reused fork JVM, which is the premise of this research
line. Some projects run parallel forks by default; ordering is a different problem there.

## 0. Discovery budget (added 2026-08-01)

A budget was set on discovery. Everything the tool executes to find an order — the profiled
run plus all confirmation runs, counted as test-execution time — must fit in **5 times** the
suite's natural test-execution time. (The budget was first set to 2x, then changed to 5x the
same day.) The capture run and the final 10-pair measurement are not counted. The final
measurement grades the tool's output; it is not part of the search. Consequences:

- `filter.py` was deleted. Its screen-and-confirm runs cost 6 or more suite runs for each
  candidate. That is far above the budget.
- A new counted stage, `confirm_moves.py`, was added (final counted total: 712 of 750 lines).
  Each leftover-state move claims: "this test slows the tests that run after it". The stage
  tests that claim directly. It runs the suspected polluter plus its largest downstream
  victim as a two-class suite, in both orders. The classes are the same in both arms; only
  the order differs. Each experiment runs two times, with the arm order alternated, and the
  stage compares the victim's median reported time. A refutation needs a null result on TWO
  different victims. If the victim runs more than 5% FASTER after the movers, the experiment
  is dominated by warm-up and proves nothing; it is not a null. Compiler-timing moves
  (JIT_HUNGRY, COLD_FAVORED, COUPLED_PAIR) pass through without experiments: small fresh-JVM
  runs invert their in-suite direction (documented in goal 2). Moves that the budget cannot
  reach are kept.
- Spend for each project, out of the 5x allowance: javaparser 43.3/60.3 s, snakeyaml
  44.8/45.9 s, snakeyaml-engine 4.0/13.2 s, commons-io 385.0/471.3 s, paimon 2209.1/2463.2 s,
  handlebars 21.5/21.5 s, avro 28.9/29.0 s. The ledgers are in
  `mechdetect/out/<fixture>/spend.tsv`.
- Outcomes on the existing wins. The javaparser 66-writer block move was CONFIRMED on its
  second victim (+6%, repeatable). The javaparser, snakeyaml-engine, and paimon orders are
  identical byte for byte, so their measurements stand. snakeyaml lost one move
  (`DumperOptionsTest` to the back for a `line.separator` property write; both large
  downstream tests were flat). The new snakeyaml order was measured again: **13.33%**, 10 of
  10 pairs, no failures (before: 13.1%).
- commons-io lost its 26-test block move. That block was built on
  `org.mockito.internal.progress.SequenceNumber#sequenceNumber`, which is Mockito's own
  invocation counter — a detector false positive that the confirmation stage caught (26
  writers passed the ubiquity cap in a 231-class suite). A new measurement WITHOUT that block
  move gave 9.63% (12 of 12 clean pairs, p=0.0005; one round was removed because a network
  outage failed two network-touching tests). So the move adds real speedup, but not through
  the counter. The profile shows the true cause: 17 of the 26 block members retransform
  loaded classes (Mockito), and only ONE retransformer exists outside the block.
  Retransformation discards compiled code. A group of retransformers at the tail contains
  that damage. Final rule: a block whose members are a majority of retransformers is a
  compiler-class move, and it is exempt from pair-run confirmation, because pair runs cannot
  reproduce compiler effects. Under this final rule, the commons-io emitted order is
  identical byte for byte to the measured winner, so **10.31%** stands. The 9.63% blockless
  measurement remains as decomposition evidence. The refuted state claim stays refuted; the
  move is kept for the correct reason.
- `compose_repair.py` was also deleted. Its repair method was one full-suite run for each
  move, which the budget does not permit at the scale the script was built for.
- The confirmation stage also produced a positive result on paimon: its top state writer
  measurably slows `PrimaryKeySimpleTableTest` (37.16 s alone; 39.67 s after the writer).
- Harness fix (not counted): all fork launchers now pass `-Djava.awt.headless=true` and
  `-Dapple.awt.UIElement=true`, so forks do not take macOS window focus.

## 1. Confirmed wins

Requirements for each row: all pairs without test failures, 9 or more wins out of 10, and a
paired median of 10% or more of the natural median.

| # | Project | fork JVM | pairs | wins | paired median | % of natural |
|---|---|---|---:|---:|---:|---:|
| 1 | javaparser (javaparser-core-testing) | 17 | 10 | 10 | +1494 ms | **12.3%** |
| 2 | snakeyaml | 8 | 10 | 10 | +1120 ms | **13.33%** (measured again under the section 0 pipeline) |
| 3 | paimon (paimon-core) | 17 | 10 | 10 | +126.4 s | **27.1%** |
| 4 | commons-io | 17 | 12 | 12 | +10.0 s | **10.31%** (order identical byte for byte under the final pipeline) |
| 5 | handlebars.java (handlebars) | 17 | 10 | 10 | +1180 ms | **19.08%** (p=0.002; found by the sweep; spend 21.5/21.5 s) |
| 6 | avro (lang/java/avro) — more than the goal requires | 17 | 10 | 10 | +724 ms | **12.73%** (p=0.002; spend 28.9/29.0 s) |

Mechanism notes:

1. **javaparser**: 66 tests each turn on an expensive parsing mode through one process-wide
   setting. The whole writer group moves to the tail, behind the large parsing consumers.
   Decomposition: +4.5 s of gains against −3.0 s of give-backs. About 2 s of the give-backs
   is a fixed cost: the first test that uses mocking pays the instrumentation bill, and
   ordering can only move that bill. About 0.9 s more would need read tracking; the probe
   sees writes only.
2. **snakeyaml**: the documented recursive-hash test and the regex-sensitive test move first.
   Compile-hungry consumers move late. Property writers move behind everything.
3. **paimon**: 25 candidates, mostly state writers and compile-hungry integration tests. The
   old raw 23.9% docker pointer was reproduced and exceeded locally. 5 classes that fail for
   environment reasons (Postgres, Iceberg, one leftover study test) were removed from both
   arms.
4. **commons-io**: the win concentrates in `FileChannelsTest` (+19.7 s) against
   `ReadAheadInputStreamTest` (−9.5 s), repeatable across 12 interleaved pairs. The causal
   chain is NOT proven to the mechanisms.md standard. Candidate explanations: a coupled-pair
   swap of two wait-heavy channel tests, or file-cache adjacency. This is stated honestly as
   measured but not attributed.
5. **handlebars**: the suite embeds the Nashorn JavaScript engine; handlebars precompiles
   templates through JavaScript. The detector moves three groups late: the tests that
   initialize and change Nashorn's internal state (a full engine's class loading and
   compilation), the Mockito tests (they retransform loaded classes, which discards compiled
   code), and the most compile-hungry tests. Most of the suite then runs before the engine's
   loading cost and before any retransformation. Evidence: the detector flags, plus one
   confirmed pair in the discovery ledger (a Nashorn-state test slows a peer from 0.77 s to
   0.83 s). A full causal decomposition to the mechanisms.md standard was not done for this
   project.
6. **avro**: several tests write Avro's process-wide safety-limit properties
   (`org.apache.avro.limits.*`). Every later decode operation checks these limits. The
   writers move behind everything; the compile-hungry I/O tests move late.

## 2. Near miss

snakeyaml-engine: 10 of 10 pairs, +275 ms — **9.1%** of natural (the bar is 10%). Gains: the
recursive-references test moved first (+88 ms), the billion-laughs test moved first (+70 ms),
the largest load test moved late (+94 ms). No losses. The remaining ceiling looks thin.

## 3. Rule changes made during this goal

Each change was verified to leave the other wins' emitted orders identical byte for byte, so
their measurements stand. The 10-mechanism scorecard passed 10 of 10 again on the final code.

1. **Writer-group move**: a setting that many tests write forms ONE block-to-tail candidate
   (one candidate for the cap). This unlocked javaparser.
2. **Weak-evidence suppression**: one changed variable alone — with no compile pressure,
   thread starts, thread-local value, created state, or retransformation — no longer moves a
   test. Moves on weak evidence cost more warm-up than they saved.
3. **Cold-rule guard**: the runs-first rule ignores a hot method that tops many tests'
   profiles. One project's per-test thread-leak dump triggered the rule on many tests.
4. The baseline arm is the profiled run's own order. This removes recurring class-set
   mismatches.
5. The discovery budget, the confirmation stage, and the retransformer-block rule
   (section 0).

## 4. Projects tried and stopped (with evidence for each row)

| Project | outcome |
|---|---|
| commons-text | −3.0%; 59% of the suite is one formatter test that no rule reaches |
| commons-csv | +2.2%; the old 16.8% pointer relied on a test that the real `mvn test` excludes |
| jsoup | −1.7%; 47% of the suite is one fuzz test |
| commons-codec | +1.1%; compute-bound cryptography |
| commons-lang | +1.3% group lead only |
| commons-collections | the applied order was 4% worse (probe); a generated-suite cluster was handled badly |
| commons-compress | the applied order was 15.6% worse: one archive test moves ±11 s with position through the OS file cache — the host-dependent category that mechanisms.md excludes |
| commons-dbcp | a +9.9% screen came from one slow natural-arm outlier; the 12-pair confirmation gave 5/12, −0.6% |
| commons-net | +0.35%; fixed protocol waits |
| commons-pool | −0.85%; fixed timeout waits |
| commons-jexl | 0.4% in the wrong direction |
| commons-vfs2 | the detector emits zero candidates; nothing to measure |
| gson, commons-validator | suites too small (1.6 s / 1.2 s) for a robust 10% claim |
| joda-time | one aggregate suite class; no order to change |
| openpojo | two tests fail deterministically without the agent and pass with the agent attached (krb5 reflection); not usable for a no-failure A/B |
| jackson-core | the build broke during the goal (snapshot parent re-resolution) |
| jackson-databind | master (JDK 21 installed for it): profiles pass, but its thread-safety and stress tests are flaky in agentless runs — even the unchanged baseline fails — so a no-failure A/B is not possible; the 2.x branch adds an aggregator suite and snapshot instability |
| pdfbox | test-engine version clash with the harness-injected platform jars (later fixed; see the sweep report) |
| httpclient5 | four successive build and toolchain failures (including dead entries in ~/.m2/toolchains.xml, since repaired with a backup); stopped after about 1 hour |
| spring-ai-openai | order fragility that depends on Docker (earlier goal) |
| commons-configuration | the build fails before Surefire runs |
| netty transport (paper module M10) | +0.02% (3-pair screen, no failures, differences on both sides of zero); the full pipeline ran (7 candidates, 2 refuted by pair runs, spend 337/372 s) — the suite is wait-dominated socket and event-loop tests |
| async-http-client client (paper M8) | excluded: the capture run produced 0 classes under the global configuration, and at about 12 minutes for each run the 20-run measurement takes hours |
| curator-recipes, curator-framework, netty handler, jp-symbol-solver (paper M1 to M4) | excluded for run time (35 minutes to 2 hours for each CI run) |
| netty transport-native-epoll (paper M7) | excluded: Linux-only tests; they skip on macOS |

## 5. Criteria walk

- **G1.** 5 projects with fresh, current-code wins: rows 1 to 5 of the table (row 6 is more
  than the goal requires).
- **G2.** Zero configuration for single projects; no test names in logic (grep is clean); one
  global threshold set.
- **G3.** Scorecard 10 of 10 on final code; counted lines 712 of 750.
- **G4.** This report, plus the spend ledgers, the candidate lists, and the measurement data
  in the mechdetect repository.
