# Javaparser Core Testing Order Experiment Results

## Front vs Back Allocation Experiment (3 Repeats)

### Overall Suite Runtime (Sum of Test Classes)

| Metric | Front Order (ms) | Back Order (ms) | Change (Back vs Front) |
|---|---|---|---|
| Run 1 | 10294.00 | 12867.00 | +2573.00 ms (+25.00%) |
| Run 2 | 10092.00 | 13147.00 | +3055.00 ms (+30.27%) |
| Run 3 | 10006.00 | 12512.00 | +2506.00 ms (+25.04%) |
| **Median** | **10092.00** | **12867.00** | **+2775.00 ms (+27.50%)** |

### Specific Runtimes for Top 3 Allocators (Median across 3 Runs)

| Test Class | Front Position (ms) | Back Position (ms) | Change (ms) | Change (%) |
|---|---|---|---|---|
| `JavadocExtractorTest` | 3823.00 | 6025.00 | +2202.00 | +57.60% |
| `BulkParseTest` | 1074.00 | 1532.00 | +458.00 | +42.64% |
| `Issue2627Test` | 351.00 | 880.00 | +529.00 | +150.71% |



## Measurement Procedure

1. Test execution was managed using Maven Surefire runs on the `javaparser-core-testing` module with a custom core classpath extension (`fun.jvm.surefire.flaky:surefire-changing-maven-extension:1.0-SNAPSHOT`) loaded to support the `-Dsurefire.runOrder=testorder` flag.
2. Two order files (`top3-front.order` and `top3-back.order`) representing the target sequences were dynamically passed via the `-Dtest` property to run against a base population of 230 test classes.
3. Surefire was configured with `forkCount=1` and `reuseForks=true` to run all classes in a single JVM lifecycle, preserving cross-class warmup, class-loading, and GC memory carryover state.
4. No instrumentation agent or Java Flight Recorder tracing was attached to ensure timing measurements reflect clean wall-clock execution without profiling overhead.
5. The experiment executed 3 interleaved A/B iterations to minimize background environmental interference such as file caching or thermal throttling.
6. Previous report XML files under `target/surefire-reports` were deleted before each run, and the class runtimes were extracted from the newly generated XML reports.

