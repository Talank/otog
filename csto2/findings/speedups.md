# Speedups & statistical validity

Per-project `select` winners, re-tested with a two-sided Wilcoxon signed-rank test
(α = 0.05, 10-round paired measurement, agent off, interleaved repeats).
A real optimizer win must be **significant vs initial** _and_ **significant vs naïve-5**
(the fastest trivially-traced order).

Initial is the `mvn test` order. Naïve-5 is the best of 5 shuffled orders.

> **Execution Environment**: Every project was run inside a Docker container on a remote Linux server provisioned with 4 CPU cores and 16 GB of RAM.

> **JVM Forking Configuration**: For all measurement runs (Initial, Naïve-5, Optimal candidate orders, and A/B experiment runs), Maven Surefire was executed with `reuseForks=true` (`forkCount=1`) to ensure single-JVM state carryover (warmup, JIT compilation, allocation state across test classes).

## Paper eval dataset (including A/B experiment testing)

| ID | Project | Module | Strategy | Initial Raw Time | Naïve-5 Raw Time | Naïve-100 Raw Time | Optimal Raw Time | % speedup v initial | % speedup v naive-5 | % speedup v naive-100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1683 | javaparser/javaparser | symbol-solver-testing | alloc-front+warm-tail | 31,501ms | 28,496ms | 30,092ms | 26,326ms | 16.4% | 7.6% (p=0.0039) | 9.5% |
| 1685 | javaparser/javaparser | core-testing | pkg-alloc-front | 26,536ms | 25,617ms | 24,852ms | 20,146ms | 24.1% | 21.4% (p=0.0020) | 18.1% |
| 20 | netty/netty | transport-native-epoll | rt-heavy-tail | 631,594ms | 632,314ms | — | 630,518ms | 0.2% | 0.3% (p=0.0645) | — |
| 29 | netty/netty | transport | pkg-rt-front | 56,215ms | 56,034ms | — | 55,592ms | 1.1% | 0.8% (p=0.3750) | — |
| 33 | netty/netty | handler | rt-heavy-tail | 292,800ms | 289,802ms | — | 289,802ms | 1.0% | -0.6% (p=0.1602) | — |
| 1305 | AsyncHttpClient/async-http-client | client | rt-heavy-tail | 202,590ms | 201,482ms | — | 201,362ms | 0.6% | 0.1% (p=0.1602) | — |
| 3320 | apache/curator | curator-recipes | rt-heavy-tail | 1,799,613ms | 1,778,795ms | — | 1,785,998ms | 0.8% | -0.8% (p=1.0000) | — |
| 3323 | apache/curator | curator-framework | pkg-alloc-front | 480,137ms | 481,944ms | — | 478,788ms | 0.3% | 0.7% (p=0.3750) | — |
| 3613 | apache/paimon | paimon-core | alloc-sort | 925,663ms | 779,205ms | 694,421ms | 704,240ms | 23.9% | 9.6% (p=0.0020) | -4.3% |
| 1778 | spring-projects/spring-ai | spring-ai-openai | pkg-rt-front | 5,918ms | 5,804ms | 5,943ms | 5,572ms | 5.9% | 4.0% (p=0.0840) | -10.1% |

*(Note: p-values for naïve-100 are omitted because the A/B testing was capped at 5 runs, making it theoretically impossible to reach statistical significance).*

*(For additional non-paper eval projects, see [additional_projects.md](file:///Users/gabriel/Development/Research/otog/csto2/findings/additional_projects.md)).*

# Logs

## javaparser (symbol-solver-testing)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=31501ms min=29766ms max=35217ms  GREEN
  alloc-front+warm-tail  runs=10 median=26326ms min=25454ms max=31235ms  GREEN
  naive                  runs=10 median=28496ms min=26247ms max=32469ms  GREEN
  rt-heavy-tail          runs=10 median=27148ms min=26074ms max=32639ms  GREEN
  pkg-alloc-front        runs=10 median=29410ms min=27485ms max=33920ms  GREEN

  alloc-front+warm-tail  +16.4% vs initial
  naive                  +9.5% vs initial
  rt-heavy-tail          +13.8% vs initial
  pkg-alloc-front        +6.6% vs initial

=> SHIP: alloc-front+warm-tail  (26326ms, 16.4% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-rt-front           discarded after 2 rounds (not in top 3) (60997ms over 2 rounds, top-3 cutoff 57527ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (57955ms over 2 rounds, top-3 cutoff 57527ms)
  jit-sort               discarded after 2 rounds (not in top 3) (63512ms over 2 rounds, top-3 cutoff 57527ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +16.4% vs initial  SIGNIFICANT@0.05
  naive                  n=10  W+=53.0 W-=2.0  p=0.0059 (exact)  median +9.5% vs initial  SIGNIFICANT@0.05
  rt-heavy-tail          n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +13.8% vs initial  SIGNIFICANT@0.05
  pkg-alloc-front        n=10  W+=54.0 W-=1.0  p=0.0039 (exact)  median +6.6% vs initial  SIGNIFICANT@0.05
```

## javaparser (core)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=26536ms min=25222ms max=27803ms  GREEN
  alloc-front+warm-tail  runs=10 median=21558ms min=20185ms max=22740ms  GREEN
  pkg-rt-front           runs=10 median=20272ms min=19478ms max=20773ms  GREEN
  naive                  runs=10 median=25617ms min=23862ms max=26879ms  GREEN
  pkg-alloc-front        runs=10 median=20146ms min=19741ms max=20468ms  GREEN

  alloc-front+warm-tail  +18.8% vs initial
  pkg-rt-front           +23.6% vs initial
  naive                  +3.5% vs initial
  pkg-alloc-front        +24.1% vs initial

=> SHIP: pkg-alloc-front  (20146ms, 24.1% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  jit-sort               new failure - com.github.javaparser.ast.visitor.TreeVisitorTest
  rt-heavy-tail          discarded after 2 rounds (not in top 3) (59149ms over 2 rounds, top-3 cutoff 41955ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (43226ms over 2 rounds, top-3 cutoff 41955ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +18.8% vs initial  SIGNIFICANT@0.05
  pkg-rt-front           n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +23.6% vs initial  SIGNIFICANT@0.05
  naive                  n=10  W+=52.0 W-=3.0  p=0.0098 (exact)  median +3.5% vs initial  SIGNIFICANT@0.05
  pkg-alloc-front        n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +24.1% vs initial  SIGNIFICANT@0.05
```

## netty (transport-native-epoll)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=631594ms min=630227ms max=635907ms  GREEN
  alloc-front+warm-tail  runs=10 median=635673ms min=631544ms max=638555ms  GREEN
  pkg-rt-front           runs=10 median=632303ms min=631255ms max=635788ms  GREEN
  naive                  runs=10 median=632314ms min=630250ms max=634246ms  GREEN
  rt-heavy-tail          runs=10 median=630518ms min=628701ms max=633798ms  GREEN

  alloc-front+warm-tail  -0.6% vs initial
  pkg-rt-front           -0.1% vs initial
  naive                  -0.1% vs initial
  rt-heavy-tail          +0.2% vs initial

=> SHIP: initial  (631594ms, 0.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-alloc-front        discarded after 2 rounds (not in top 3) (1266007ms over 2 rounds, top-3 cutoff 1263262ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (1476398ms over 2 rounds, top-3 cutoff 1263262ms)
  jit-sort               discarded after 2 rounds (not in top 3) (1456493ms over 2 rounds, top-3 cutoff 1263262ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=11.0 W-=44.0  p=0.1055 (exact)  median -0.6% vs initial  n.s.
  pkg-rt-front           n=10  W+=26.0 W-=29.0  p=0.9219 (exact)  median -0.1% vs initial  n.s.
  naive                  n=9  W+=26.0 W-=19.0  p=0.7344 (exact)  median -0.1% vs initial  n.s.
  rt-heavy-tail          n=10  W+=48.0 W-=7.0  p=0.0371 (exact)  median +0.2% vs initial  SIGNIFICANT@0.05
```

## netty (transport)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=56215ms min=55105ms max=56468ms  GREEN
  alloc-sort             runs=10 median=56032ms min=55112ms max=56330ms  GREEN
  alloc-front+warm-tail  runs=10 median=56044ms min=55880ms max=56337ms  GREEN
  pkg-rt-front           runs=10 median=55592ms min=54978ms max=56309ms  GREEN
  naive                  runs=10 median=56034ms min=54998ms max=56186ms  GREEN

  alloc-sort             +0.3% vs initial
  alloc-front+warm-tail  +0.3% vs initial
  pkg-rt-front           +1.1% vs initial
  naive                  +0.3% vs initial

=> SHIP: pkg-rt-front  (55592ms, 1.1% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-alloc-front        discarded after 2 rounds (not in top 3) (112455ms over 2 rounds, top-3 cutoff 112324ms)
  rt-heavy-tail          discarded after 2 rounds (not in top 3) (112737ms over 2 rounds, top-3 cutoff 112324ms)
  jit-sort               discarded after 2 rounds (not in top 3) (113033ms over 2 rounds, top-3 cutoff 112324ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=53.0 W-=2.0  p=0.0059 (exact)  median +0.3% vs initial  SIGNIFICANT@0.05
  alloc-front+warm-tail  n=10  W+=32.0 W-=23.0  p=0.6953 (exact)  median +0.3% vs initial  n.s.
  pkg-rt-front           n=10  W+=45.0 W-=10.0  p=0.0840 (exact)  median +1.1% vs initial  n.s.
  naive                  n=10  W+=36.0 W-=19.0  p=0.4316 (exact)  median +0.3% vs initial  n.s.
```

## netty (handler)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=292800ms min=289815ms max=296368ms  GREEN
  alloc-sort             runs=10 median=292398ms min=286970ms max=311772ms  GREEN
  alloc-front+warm-tail  runs=10 median=293204ms min=289071ms max=300601ms  GREEN
  naive                  runs=10 median=289802ms min=281622ms max=290940ms  GREEN
  rt-heavy-tail          runs=10 median=291412ms min=283853ms max=294010ms  GREEN

  alloc-sort             +0.1% vs initial
  alloc-front+warm-tail  -0.1% vs initial
  naive                  +1.0% vs initial
  rt-heavy-tail          +0.5% vs initial

=> SHIP: naive  (289802ms, 1.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-alloc-front        discarded after 2 rounds (not in top 3) (585274ms over 2 rounds, top-3 cutoff 581446ms)
  pkg-rt-front           discarded after 2 rounds (not in top 3) (581682ms over 2 rounds, top-3 cutoff 581446ms)
  jit-sort               discarded after 2 rounds (not in top 3) (582617ms over 2 rounds, top-3 cutoff 581446ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=29.0 W-=26.0  p=0.9219 (exact)  median +0.1% vs initial  n.s.
  alloc-front+warm-tail  n=10  W+=16.0 W-=39.0  p=0.2754 (exact)  median -0.1% vs initial  n.s.
  naive                  n=10  W+=52.0 W-=3.0  p=0.0098 (exact)  median +1.0% vs initial  SIGNIFICANT@0.05
  rt-heavy-tail          n=10  W+=42.0 W-=13.0  p=0.1602 (exact)  median +0.5% vs initial  n.s.
```

## async-http-client (client)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=202590ms min=199894ms max=204631ms  GREEN
  alloc-front+warm-tail  runs=10 median=201484ms min=200229ms max=202433ms  GREEN
  naive                  runs=10 median=201482ms min=200594ms max=204508ms  GREEN
  rt-heavy-tail          runs=10 median=201362ms min=199995ms max=204097ms  GREEN
  pkg-alloc-front        runs=10 median=203048ms min=200909ms max=205225ms  GREEN

  alloc-front+warm-tail  +0.5% vs initial
  naive                  +0.5% vs initial
  rt-heavy-tail          +0.6% vs initial
  pkg-alloc-front        -0.2% vs initial

=> SHIP: initial  (202590ms, 0.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-rt-front           discarded after 2 rounds (not in top 3) (405181ms over 2 rounds, top-3 cutoff 403470ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (409483ms over 2 rounds, top-3 cutoff 403470ms)
  jit-sort               discarded after 2 rounds (not in top 3) (406547ms over 2 rounds, top-3 cutoff 403470ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=43.0 W-=12.0  p=0.1309 (exact)  median +0.5% vs initial  n.s.
  naive                  n=10  W+=32.0 W-=23.0  p=0.6953 (exact)  median +0.5% vs initial  n.s.
  rt-heavy-tail          n=10  W+=42.0 W-=13.0  p=0.1602 (exact)  median +0.6% vs initial  n.s.
  pkg-alloc-front        n=10  W+=11.0 W-=44.0  p=0.1055 (exact)  median -0.2% vs initial  n.s.
```

## curator (curator-recipes)

```
=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=1799613ms min=1728007ms max=1811774ms  GREEN
  alloc-sort             runs=10 median=1809609ms min=1743331ms max=1833250ms  GREEN
  rt-heavy-tail          runs=10 median=1785998ms min=1697780ms max=1800058ms  GREEN

  alloc-sort             -0.6% vs initial
  rt-heavy-tail          +0.8% vs initial

=> SHIP: initial  (1785998ms, 0.8% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-alloc-front        discarded after 2 rounds (not in top 3)
  pkg-rt-front           discarded after 2 rounds (not in top 3)
  jit-sort               discarded after 2 rounds (not in top 3)
  naive                  new failure*
  alloc-front+warm-tail  new failure*

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=20.0 W-=35.0  p=0.4922 (exact)  median +0.0% vs initial  n.s.
  rt-heavy-tail          n=10  W+=40.0 W-=15.0  p=0.2324 (exact)  median +1.1% vs initial  n.s.
```

\* Not test failures — no test failed in any round. Both were crashed forks on that candidate's final
round (`alloc-front+warm-tail` produced 19 of 53 classes, `naive` 34 of 53), consistent with the
ZooKeeper port race seen on 3323. Recovering their green rounds from `select/logs/` does not change the
verdict: `alloc-front+warm-tail` +0.91% (p=0.5469, n=8), `naive` -0.28% (p=1.0000, n=6). Nothing here is
measurable anyway — `initial` varies 4.7% across its own rounds, so a ~1% effect is inside the noise.

## curator (curator-framework)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=480137ms min=473833ms max=484103ms  GREEN
  alloc-front+warm-tail  runs=10 median=479610ms min=475879ms max=482796ms  GREEN
  naive                  runs=10 median=481944ms min=478893ms max=489596ms  GREEN
  rt-heavy-tail          runs=10 median=479722ms min=477703ms max=490318ms  GREEN
  pkg-alloc-front        runs=10 median=478788ms min=471820ms max=490319ms  GREEN

  alloc-front+warm-tail  +0.1% vs initial
  naive                  -0.4% vs initial
  rt-heavy-tail          +0.1% vs initial
  pkg-alloc-front        +0.3% vs initial

=> SHIP: initial  (480137ms, 0.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  pkg-rt-front           discarded after 2 rounds (not in top 3) (964602ms over 2 rounds, top-3 cutoff 959186ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (960123ms over 2 rounds, top-3 cutoff 959186ms)
  jit-sort               discarded after 2 rounds (not in top 3) (964834ms over 2 rounds, top-3 cutoff 959186ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=28.0 W-=27.0  p=1.0000 (exact)  median +0.1% vs initial  n.s.
  naive                  n=10  W+=8.0 W-=47.0  p=0.0488 (exact)  median -0.4% vs initial  SIGNIFICANT@0.05
  rt-heavy-tail          n=10  W+=18.0 W-=37.0  p=0.3750 (exact)  median +0.1% vs initial  n.s.
  pkg-alloc-front        n=10  W+=28.0 W-=27.0  p=1.0000 (exact)  median +0.3% vs initial  n.s.
```

## paimon (paimon-core)

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=925663ms min=862272ms max=981795ms  GREEN
  alloc-sort             runs=10 median=704240ms min=628160ms max=734611ms  GREEN
  alloc-front+warm-tail  runs=10 median=941659ms min=851597ms max=978736ms  GREEN
  pkg-rt-front           runs=10 median=740302ms min=683120ms max=873810ms  GREEN
  naive                  runs=10 median=779205ms min=738443ms max=831151ms  GREEN
  jit-sort               runs=10 median=734419ms min=702534ms max=763427ms  GREEN
  rt-heavy-tail          runs=10 median=927903ms min=864407ms max=1013744ms  GREEN
  pkg-alloc-front        runs=10 median=755952ms min=711734ms max=855275ms  GREEN

  alloc-sort             +23.9% vs initial
  alloc-front+warm-tail  -1.7% vs initial
  pkg-rt-front           +20.0% vs initial
  naive                  +15.8% vs initial
  jit-sort               +20.7% vs initial
  rt-heavy-tail          -0.2% vs initial
  pkg-alloc-front        +18.3% vs initial

=> SHIP: alloc-sort  (704240ms, 23.9% faster than initial) [green]

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +23.9% vs initial  SIGNIFICANT@0.05
  alloc-front+warm-tail  n=10  W+=19.0 W-=36.0  p=0.4316 (exact)  median -1.7% vs initial  n.s.
  pkg-rt-front           n=10  W+=54.0 W-=1.0  p=0.0039 (exact)  median +20.0% vs initial  SIGNIFICANT@0.05
  naive                  n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +15.8% vs initial  SIGNIFICANT@0.05
  jit-sort               n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +20.7% vs initial  SIGNIFICANT@0.05
  rt-heavy-tail          n=10  W+=29.0 W-=26.0  p=0.9219 (exact)  median -0.2% vs initial  n.s.
  pkg-alloc-front        n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +18.3% vs initial  SIGNIFICANT@0.05
```

## spring-ai

```

=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=5918ms min=5388ms max=6512ms  GREEN
  pkg-rt-front           runs=10 median=5572ms min=5085ms max=6003ms  GREEN
  naive                  runs=10 median=5804ms min=5409ms max=6348ms  GREEN
  rt-heavy-tail          runs=10 median=5859ms min=5285ms max=6357ms  GREEN
  pkg-alloc-front        runs=10 median=5658ms min=5235ms max=6049ms  GREEN

  pkg-rt-front           +5.9% vs initial
  naive                  +1.9% vs initial
  rt-heavy-tail          +1.0% vs initial
  pkg-alloc-front        +4.4% vs initial

=> SHIP: pkg-rt-front  (5572ms, 5.9% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  alloc-front+warm-tail  discarded after 2 rounds (not in top 3) (12689ms over 2 rounds, top-3 cutoff 11085ms)
  alloc-sort             discarded after 2 rounds (not in top 3) (11551ms over 2 rounds, top-3 cutoff 11085ms)
  jit-sort               discarded after 2 rounds (not in top 3) (12315ms over 2 rounds, top-3 cutoff 11085ms)


=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  pkg-rt-front           n=10  W+=48.0 W-=7.0  p=0.0371 (exact)  median +5.9% vs initial  SIGNIFICANT@0.05
  naive                  n=10  W+=32.0 W-=23.0  p=0.6953 (exact)  median +1.9% vs initial  n.s.
  rt-heavy-tail          n=10  W+=30.0 W-=25.0  p=0.8457 (exact)  median +1.0% vs initial  n.s.
  pkg-alloc-front        n=10  W+=46.0 W-=9.0  p=0.0645 (exact)  median +4.4% vs initial  n.s.
```
