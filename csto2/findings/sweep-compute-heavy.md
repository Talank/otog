# Sweep: Compute-Heavy Subjects (30 s to 2 m Suites)

Started 2026-08-01, evening. The sweep ran until interrupted. Target: compute-bound Maven
modules with a local suite run time of 30 seconds to 2 minutes. For each subject, the
pipeline ran these steps: capture the natural order, run the profiled run, run the budgeted
confirmation (5x total or less), emit the order, and screen with 3 pairs. A screen of about
5% or more got the full measurement of 10 or more pairs. Gradle-only projects are out of
scope, because the harness uses Maven Surefire. Wins of 10% or more graduate to
findings/natural-10pct.md, section 1.

## Results table

| # | Subject | local suite | verdict |
|---|---------|------------|---------|
| 1 | jgrapht-core (JDK 21, JUnit 6) | 157 s | PARKED: screen −1.45% (3 pairs, no failures; differences on both sides of zero: +4.1 s / −6.4 s / −2.3 s) |
| 2 | commons-imaging | 17.8 s | PARKED: screen +2.25% (3 of 3 pairs positive: +400/+447/+81 ms) — real but small |
| 3 | zxing core (JUnit 4, vintage engine injected) | 51 s | PARKED: screen −0.02%, flat — uniform CPU-bound decoding, no carry-over asymmetry |
| 4 | jts-core (Surefire 2.15, vintage) | 2.1 s | PARKED: suite too small for a robust claim; screen +4.33% (3 of 3 positive, +91 ms). This subject forced two harness fixes: the old-Surefire capture format, and a build-tools install |
| 5 | hipparchus-core | 93 s | PARKED: screen −0.21%, flat. This subject forced one harness fix: remove unresolved jacoco argument-line placeholders (KP_REMOVE_ARGS=jacoco, now global) |
| 6 | JSqlParser | 13.4 s | CONFIRMED REAL, UNDER THE BAR: +5.15% (10 of 10 pairs, no failures, p=0.002, +687 ms). Compile-hungry parser tests moved late, and the Mockito group moved to the tail — the winning-category structure at half the necessary size |
| 7 | velocity-engine-core | 0.3 s | PARKED: the replayed suite collapses to about 300 ms — not measurable |
| 8 | mvel (mvel3) | 6.0 s | PARKED: screen +4.35% (3 of 3 positive) — consistent, but the suite and the effect are small. MVELTranspilerTest was removed from both arms (no report under replay) |
| 9 | janino (commons-compiler-tests) | — | PARKED: the module installs fail (no aggregator pom; the parent build fails); two attempts |
| 10 | ognl | 1.4 s | PARKED: suite too small; screen flat (−1.59%) |
| 11 | commons-bcel | 16.3 s | PARKED: screen +0.71% median, flat (one +1.9 s outlier pair) |
| 12 | johnzon-core | — | PARKED: the vintage engine fails test discovery under ordered runs, with the project's engine set and with the injected engine set |
| 13 | xstream | — | PARKED: fork errors under ordered replay with both engine setups (JUnit 3-style suites); two attempts |
| 14 | woodstox | 3.5 s | PARKED: +3.04% median, mixed pair signs, small suite |
| 15 | tika-core | 5.3 s | PARKED: flat (−0.83%); the suite is much smaller locally than in CI |
| 16 | jackson-dataformat-xml (release tag 2.19.2) | 0.7 s | PARKED: suite too small, flat. A clone at a release tag avoids the jackson snapshot-parent problem — a reusable method |
| 17 | antlr4 tool-testsuite | 0.1 s | PARKED: the replayed suite collapses — a custom test driver; not measurable under plain Surefire replay |
| 18 | pdfbox (second attempt) | 3.3 s replayed | PARKED: the engine clash from the earlier run is FIXED by the current harness; but the replayed suite is a 3.3 s subset, flat (−0.27%) |
| 19 | javassist | — | PARKED: one aggregate suite class; no order to change |
| 20 | commonmark | 6.7 s | PARKED: flat and noisy (median −4.62%; pairs on both sides of ±1 s) |
| 21 | thymeleaf | — | PARKED: aggregator root; the tests live in a separate custom harness tree, not in the library module |
| 22 | jinjava | 3.5 s | CONFIRMED REAL, UNDER THE BAR: +5.21% (9 of 10 pairs, p=0.022). AstFilterChainPerformanceTest was removed from both arms: it asserts its own micro-benchmark speedup and is timing-flaky. This subject added the basepom skip flag to the harness |
| 23 | pebble | 4.0 s | PARKED: flat (+0.63%) |
| 24 | handlebars.java | 6.2 s | **WIN 5: +19.08% CONFIRMED** (10 of 10 pairs, no failures, p=0.002, +1180 ms) — moved to natural-10pct.md, section 1. Goal 3 complete |
| 25 | mustache.java (compiler) | 184 s | PARKED: flat (0.02%); fixed-length concurrency tests dominate the suite |
| 26 | libphonenumber | 0.9 s | PARKED: too small; the applied order is consistently WORSE (−10.76%, 3 of 3) — the pipeline probably moved a shared-metadata-cache builder late, which penalizes every later reader |
| 27 | stringtemplate4 | 0.4 s | PARKED: test failures as given under replay (classpath-dependent import tests), and a sub-second suite |
| 28 | rome | 1.0 s | PARKED: suite too small; also one locale-sensitive date test fails under replay |
| 29 | joni | 4.1 s | PARKED: flat (+0.43%) |
| 30 | kryo | — | PARKED: the tests compile to a newer class-file version than the measurement JVMs (17/21) can load, also after a rebuild with a matched JAVA_HOME; three attempts |
| 31 | msgpack-java | — | PARKED: sbt build, not Maven — out of scope |
| 32 | jackson-databind (release 2.19.2, JDK 21) | 6.6 s replayed | PARKED: the release tag plus JDK 21 removes the master-branch agentless flakiness (a useful fact), but the replay collapses to a 6.6 s subset (aggregator suites); screen +1.64% |
| 33 | batik | — | PARKED: aggregator root; the tests spread across modules with a custom regression-test framework |
| 34 | fory-core | — | PARKED: TestNG suite-file execution — one aggregate entry; no order to change |
| 35 | guice (core) | 12.9 s | PARKED: +1.31% (3 of 3 positive, small) |
| 36 | byte-buddy-dep | 9.2 s replayed | PARKED: +1.37% median, mixed pairs |
| 37 | opennlp-tools (JDK 21) | 8.2 s | PARKED: flat and noisy (−2.75% median, mixed) |
| 38 | fastjson2 (core) | 24.5 s | PARKED: flat and noisy (−1.39% median; pairs ±1.3 s) |
| 39 | avro (lang/java/avro) | 5.7 s | **WIN 6 (more than the goal requires): +12.73% CONFIRMED** (10 of 10, no failures, p=0.002, +724 ms). Tests that write Avro's process-wide decoder safety-limit properties move behind everything; compile-hungry I/O tests move late. Spend 28.9/29.0 s |
| 40 | checkstyle | — | PARKED: test dependencies compiled for a JDK newer than 21 (Cacio); the measurement JVMs stop at 21 |
| 41 | pmd-core | — | PARKED: the project's Surefire configuration cannot be parsed by the forked 3.0.0-M8 plugin |
| 42 | jfreechart | 1.2 s replayed | PARKED: display tests skip in headless mode; the subset is flat (+1.21%, mixed) |
| 43 | commons-math-core | — | PARKED: the module holds one test class after the project's modularization |
| 44 | jackson-dataformat-yaml (release tag) | 0.3 s | PARKED: suite too small, flat |
| 45 | yamlbeans | — | PARKED: no Maven Surefire test execution (legacy build layout) |
| 46 | commons-beanutils | 13.5 s | PARKED: +4.27% median, mixed pairs (−0.2 s / +0.9 s / +0.6 s) |
| 47 | commons-digester3-core | 0.5 s | PARKED: suite too small, flat |
| 48 | classgraph | — | PARKED: the capture produces no test executions under plain `mvn test` |
| 49 | junit4 | 0.5 s replayed | PARKED: the suite runs through an aggregate; the replay collapses; a +55 ms median has no meaning at this scale |
| 50 | commons-rng, commons-statistics, commons-numbers | — | PARKED: module capture empty (parent resolution); numeric category |
| 51 | commons-fileupload2-core | 0.2 s | PARKED: suite too small |
| 52 | santuario-xml-security | 0.4 s replayed | PARKED: the tests live in submodules; the root replay is a 5-class stub with failures |
| 53 | picocli | — | PARKED: Gradle is the primary build (the root pom is a stub) |

## Findings

- **Category.** Order headroom concentrates in parser, serializer, and template libraries
  that keep mutable process-wide state: a global configuration, an embedded engine, or global
  limit properties. All six wins and all confirmed under-bar results (JSqlParser +5.15%,
  jinjava +5.21%) are in this category. Pure-compute suites (mathematics, codecs, regular
  expressions, geometry, NLP) were flat in every case.
- **Rates.** Nine subjects in the full study have a proven significant speedup (10 or more
  pairs, no failures, p <= 0.05): the six wins, snakeyaml-engine (9.1%), JSqlParser, and
  jinjava. That is about 20% of the roughly 45 subjects that could be measured, and about
  13% of all subjects tried. About another 7% show consistent small positives that were
  never escalated, because they cannot reach 10%. Three subjects (about 7%) show a clear,
  repeatable slowdown: commons-compress (OS file cache), commons-collections (generated-suite
  cluster), and libphonenumber (a cache builder moved late). The slowdown cases are the
  reason for the measurement gate: no order ships without beating its baseline.
- **Environment.** About one third of the subjects fail before measurement: wrong JDK level,
  Gradle or sbt builds, aggregator suites, custom test drivers, or Surefire configuration
  clashes.
- **Detector feedback.** The libphonenumber slowdown shows a missing capability. A test that
  creates global data always moves late under the current rules. A cache that later tests
  read should move early instead. To separate the two cases, the probe must track reads. The
  javaparser decomposition points at the same missing capability (about 0.9 s).
