# Cost of per-method vs per-class allocation tracing

*2026-07-16 (week 2026-W29)*

Sampling allocation once per test method instead of once per test class costs 1.6 ms on
javaparser-core-testing (2720 methods, 274 classes, ~12.8 s suite), or 0.012%. The probe is
`com.sun.management.ThreadMXBean.getThreadAllocatedBytes` summed over all live threads, measured
directly at 0.32 us/call with 6 live threads; per-class tracing spends 0.2 ms on probes and
per-method tracing spends 1.7 ms. A suite-level A/B cannot resolve this, because the difference is
about 1500x smaller than the run-to-run noise (+/- 2500 ms), so the microbenchmark is the only way to
measure it.

The probe is O(live threads), so a suite with many threads and many methods would pay more: at 100
live threads the probe costs roughly 5 us, which for 10,000 methods is about 100 ms. That is still
negligible against any suite large enough to have those properties. Granularity is therefore not a
cost argument for or against per-method tracing. Note that `getCurrentThreadAllocatedBytes` is
10x cheaper (0.03 us/call) but only counts the test thread, which undercounts tests that allocate on
a worker pool (BulkParseTest reports 0.4 MB instead of 3.8 GB).
