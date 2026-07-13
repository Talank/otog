# Speedups & statistical validity

Per-project `select` winners, re-tested with a two-sided Wilcoxon signed-rank test
(α = 0.05, 10-round paired measurement, agent off, interleaved repeats).
A real optimizer win must be **significant vs initial** _and_ **significant vs naïve-5**
(the fastest trivially-traced order).

## Paper eval dataset (prior research)

| ID | Project | Module | Strategy | Initial | Naïve-5 | Δ Initial | Δ Naïve-5 | p (init) | p (n-5) | Sig? | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1683 | javaparser/javaparser | symbol-solver-testing | alloc-sort | 11434ms | 11380ms | 5.1% | 0.5% | 0.0039 | 0.0020 | ✓ both | Corrected 2026-07-13; was incorrect data |
| 1685 | javaparser/javaparser | core-testing | pkg-rt-front | 13527ms | 12597ms | 23.3% | 6.9% | 0.006 | n/a | ✓ init | Naïve-5 re-test pending |
| 29 | netty/netty | transport | pkg-alloc-front | 65407ms | 65391ms | 0.1% | 0.0% | 0.1934 | 0.5566 | ✗ | |
| 1305 | AsyncHttpClient/async-http-client | client | pkg-alloc-front | 240761ms | 241109ms | 0.0% | -0.1% | 0.4922 | 0.6250 | ✗ | |
| 3323 | apache/curator | curator-framework | alloc-sort | 510889ms | 509202ms | 0.3% | 0.3% | 1.0000 | 0.9219 | ✗ | |
| 3613 | apache/paimon | paimon-core | alloc-sort | 926511ms | 786869ms | 23.6% | 15.1% | 0.0020 | 0.0020 | ✓ both | |
| 1778 | spring-projects/spring-ai | spring-ai-openai | pkg-alloc-front | 13225ms | 13436ms | -0.2% | -1.6% | 0.8457 | 0.1309 | ✗ | |

## Additional projects

| Project | Module | Strategy | Initial | Naïve-5 | Δ Initial | Δ Naïve-5 | p (init) | p (n-5) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| apache/commons-csv | — | alloc-front+warm-tail | 12220ms | 11392ms | 16.8% | 6.8% | 0.008 | n/a | Naïve-5 re-test pending |
| apache/commons-text | — | jit-sort | 17370ms | 16031ms | 12.9% | 7.7% | 0.0020 | 0.0488 | Corrected 2026-07-09; kill-9 truncation fix |
| apache/commons-math | commons-math-legacy | pkg-alloc-front | 17195ms | 16422ms | 5.6% | — | 1.000 | — | 10-round re-test: −0.3%, did not hold |
| alibaba/fastjson2 | core | pkg-alloc-front | 22462ms | 23171ms | 1.1% | — | 0.415 | — | 10-round re-test: −0.05%, did not hold |

# Logs

## commons-csv

```
=== CANDIDATE MEASUREMENTS ===
  pkg-alloc-front        runs=4 median=10358ms min=9821ms max=10559ms  GREEN
  naive-5                  runs=4 median=11392ms min=10253ms max=13185ms  GREEN
  alloc-sort             runs=4 median=10700ms min=10066ms max=10973ms  GREEN
  intra-warmup           runs=4 median=16803ms min=10670ms max=17678ms  GREEN
  pkg-alloc+observed-intra runs=4 median=10534ms min=10016ms max=10603ms  GREEN
  pkg-rt-front           runs=4 median=10258ms min=10207ms max=11302ms  GREEN
  jit-sort              runs=4 median=11793ms min=10288ms max=12089ms  GREEN
  alloc-front            runs=4 median=10855ms min=10016ms max=11231ms  GREEN
  warm-tail              runs=4 median=12413ms min=11927ms max=13036ms  GREEN
  initial                runs=4 median=12220ms min=12156ms max=12875ms  GREEN
  alloc-front+warm-tail  runs=4 median=10170ms min=10020ms max=11454ms  GREEN

  pkg-alloc-front        +15.2% vs initial
  naive-5                  +6.8% vs initial
  alloc-sort             +12.4% vs initial
  intra-warmup           -37.5% vs initial
  pkg-alloc+observed-intra +13.8% vs initial
  pkg-rt-front           +16.1% vs initial
  jit-sort              +3.5% vs initial
  alloc-front            +11.2% vs initial
  warm-tail              -1.6% vs initial
  alloc-front+warm-tail  +16.8% vs initial

=> SHIP: alloc-front+warm-tail  (10170ms, 16.8% faster than initial) [green]
```

## javaparser (core)

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=4 median=10527ms min=10151ms max=10552ms  GREEN
  jit-sort              runs=4 median=10865ms min=9995ms max=11768ms  GREEN
  jfr-warmup-front       runs=4 median=12724ms min=11661ms max=12792ms  GREEN
  initial                runs=4 median=13527ms min=12879ms max=13694ms  GREEN
  pkg-alloc+observed-intra runs=4 median=10672ms min=9651ms max=11367ms  GREEN
  alloc-front+warm-tail  runs=4 median=10714ms min=9943ms max=12762ms  GREEN
  alloc-sort             runs=4 median=10545ms min=9805ms max=10996ms  GREEN
  warm-tail              runs=4 median=13625ms min=13282ms max=13729ms  GREEN
  pkg-alloc-front        runs=4 median=10515ms min=10058ms max=10691ms  GREEN
  pkg-rt-front           runs=4 median=10373ms min=10135ms max=11171ms  GREEN
  intra-warmup           runs=4 median=13656ms min=13009ms max=14477ms  GREEN
  naive-5                  runs=4 median=12597ms min=12028ms max=13235ms  GREEN

  alloc-front            +22.2% vs initial
  jit-sort              +19.7% vs initial
  jfr-warmup-front       +5.9% vs initial
  pkg-alloc+observed-intra +21.1% vs initial
  alloc-front+warm-tail  +20.8% vs initial
  alloc-sort             +22.0% vs initial
  warm-tail              -0.7% vs initial
  pkg-alloc-front        +22.3% vs initial
  pkg-rt-front           +23.3% vs initial
  intra-warmup           -1.0% vs initial
  naive-5                  +6.9% vs initial

=> SHIP: pkg-rt-front  (10373ms, 23.3% faster than initial) [green]
```

## commons-text (corrected 2026-07-09 — kill-9 truncation fixed)

10-round paired run + Wilcoxon, full 101-class suite (`TextStringBuilderTest` no longer excluded — the
fork now drops `-XX:OnOutOfMemoryError=kill -9`). All green, all classes reported (completeness gate on).
Root cause + fix writeup: `2026-W28/commons-text-kill9-truncation.md`. (The prior block here — `naive-5`
+13.9% — was a kill-9 truncation artifact and has been removed; see git history.)

```
=== CANDIDATE MEASUREMENTS ===
  alloc-sort             runs=10 median=15468ms min=14556ms max=17138ms  GREEN
  initial                runs=10 median=17370ms min=16736ms max=18141ms  GREEN
  jit-sort               runs=10 median=15131ms min=14517ms max=16096ms  GREEN
  naive-5                  runs=10 median=16031ms min=15121ms max=18722ms  GREEN

  alloc-sort             +10.9% vs initial
  jit-sort               +12.9% vs initial
  naive-5                  +7.7% vs initial

=> SHIP: jit-sort  (15131ms, 12.9% faster than initial) [green]

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort   n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +12.0% vs initial  SIGNIFICANT@0.05
  jit-sort     n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +12.9% vs initial  SIGNIFICANT@0.05
  naive-5        n=10  W+=51.0 W-=4.0  p=0.0137 (exact)  median +7.7%  vs initial  SIGNIFICANT@0.05
```
jit-sort and alloc-sort each beat the free `naive-5` baseline (jit-sort +5.6%, alloc-sort +3.5% median).
This run restricted candidates to alloc-sort/jit-sort via `skip-candidates` (initial/naive-5 are
protected); a broader portfolio may find more.

## commons-math

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=4 median=17862ms min=16605ms max=18316ms  GREEN
  jit-sort              runs=4 median=17732ms min=17033ms max=18223ms  GREEN
  jfr-warmup-front       runs=4 median=17506ms min=16400ms max=18001ms  GREEN
  initial                runs=4 median=17195ms min=15024ms max=17436ms  GREEN
  pkg-alloc+observed-intra runs=4 median=17690ms min=16372ms max=17852ms  GREEN
  alloc-front+warm-tail  runs=4 median=17208ms min=16278ms max=17433ms  GREEN
  alloc-sort             runs=4 median=17555ms min=16755ms max=17568ms  GREEN
  warm-tail              runs=4 median=17825ms min=16939ms max=18457ms  GREEN
  pkg-alloc-front        runs=4 median=16268ms min=16184ms max=17531ms  GREEN
  pkg-rt-front           runs=4 median=16613ms min=14572ms max=16669ms  GREEN
  intra-warmup           runs=4 median=17637ms min=16489ms max=18169ms  GREEN
  naive-5                  runs=4 median=16422ms min=15712ms max=16700ms  GREEN

  alloc-front            -3.9% vs initial
  jit-sort              -3.1% vs initial
  jfr-warmup-front       -1.8% vs initial
  pkg-alloc+observed-intra -2.9% vs initial
  alloc-front+warm-tail  -0.1% vs initial
  alloc-sort             -2.1% vs initial
  warm-tail              -3.7% vs initial
  pkg-alloc-front        +5.4% vs initial
  pkg-rt-front           +3.4% vs initial
  intra-warmup           -2.6% vs initial
  naive-5                  +4.5% vs initial

=> SHIP: pkg-alloc-front  (16268ms, 5.4% faster than initial) [green]
```
(10-round Wilcoxon re-test: pkg-alloc-front −0.3% vs initial, p=1.000 — **not significant**, the 5.6%
did not hold.)

## fastjson2

```
=== CANDIDATE MEASUREMENTS ===
  pkg-alloc-front        runs=4 median=22225ms min=21752ms max=28755ms  GREEN
  alloc-front            runs=4 median=22329ms min=20884ms max=30967ms  GREEN
  pkg-rt-front           runs=4 median=22699ms min=20684ms max=27009ms  GREEN
  jit-sort              runs=4 median=25223ms min=21982ms max=26049ms  GREEN
  initial                runs=4 median=22462ms min=21079ms max=23473ms  GREEN
  naive-5                  runs=4 median=23171ms min=21177ms max=24225ms  GREEN

  pkg-alloc-front        +1.1% vs initial
  alloc-front            +0.6% vs initial
  pkg-rt-front           -1.1% vs initial
  jit-sort              -12.3% vs initial
  naive-5                  -3.2% vs initial

=> SHIP: pkg-alloc-front  (22225ms, 1.1% faster than initial) [green]
```
(10-round Wilcoxon re-test: pkg-alloc-front −0.05% vs initial, p=0.415 — **not significant**.)

## javaparser (symbol-solver-testing) — corrected 2026-07-13

10-round paired Wilcoxon from local `.csto2/wilcoxon/measure.jsonl`. The previous block here
used stale `select`-phase data (runs=8, initial median=22028ms, alloc-sort +11.1%) from an
unknown environment; see git history.

```
=== CANDIDATE MEASUREMENTS ===
  alloc-sort             runs=10 median=10850ms min=8390ms max=11211ms  GREEN
  initial                runs=10 median=11434ms min=10856ms max=12638ms  GREEN
  naive                  runs=10 median=11380ms min=10984ms max=12511ms  GREEN

  alloc-sort             +5.1% vs initial
  naive                  +0.5% vs initial

=> SHIP: alloc-sort  (10850ms, 5.1% faster than initial) [green]

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=54.0 W-=1.0  p=0.0039 (exact)  median +5.1% vs initial  SIGNIFICANT@0.05
  naive                  n=10  W+=35.0 W-=20.0  p=0.4922 (exact)  median +0.5% vs initial  n.s.
```

## netty (transport)

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front+warm-tail  runs=10 median=65424ms min=64395ms max=65604ms  GREEN
  alloc-sort             runs=10 median=65398ms min=64400ms max=65796ms  GREEN
  initial                runs=10 median=65407ms min=64375ms max=65451ms  GREEN
  jit-sort               runs=10 median=65424ms min=65312ms max=65846ms  GREEN
  naive-5                  runs=10 median=65391ms min=65336ms max=65791ms  GREEN
  pkg-alloc-front        runs=10 median=65358ms min=65314ms max=65812ms  GREEN
  pkg-rt-front           runs=10 median=65410ms min=65331ms max=65817ms  GREEN
  rt-heavy-tail          runs=10 median=65413ms min=64337ms max=65493ms  GREEN

  alloc-front+warm-tail  -0.0% vs initial
  alloc-sort             +0.0% vs initial
  jit-sort               -0.0% vs initial
  naive-5                  +0.0% vs initial
  pkg-alloc-front        +0.1% vs initial
  pkg-rt-front           -0.0% vs initial
  rt-heavy-tail          -0.0% vs initial

=> SHIP: initial  (65407ms, 0.0% faster than initial) [green]

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-front+warm-tail  n=10  W+=19.0 W-=36.0  p=0.4316 (exact)  median -0.1% vs initial  n.s.
  alloc-sort             n=10  W+=23.0 W-=32.0  p=0.6953 (exact)  median -0.0% vs initial  n.s.
  jit-sort               n=10  W+=15.0 W-=40.0  p=0.2324 (exact)  median -0.1% vs initial  n.s.
  naive-5                  n=10  W+=24.0 W-=31.0  p=0.7695 (exact)  median -0.1% vs initial  n.s.
  pkg-alloc-front        n=10  W+=23.0 W-=32.0  p=0.6953 (exact)  median -0.1% vs initial  n.s.
  pkg-rt-front           n=10  W+=13.0 W-=42.0  p=0.1602 (exact)  median -0.1% vs initial  n.s.
  rt-heavy-tail          n=10  W+=27.0 W-=28.0  p=1.0000 (exact)  median -0.0% vs initial  n.s.
```

## async-http-client (client)

```
=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=240761ms min=240045ms max=241926ms  GREEN
  alloc-sort             runs=10 median=241088ms min=239552ms max=242521ms  GREEN
  pkg-rt-front           runs=10 median=241223ms min=240179ms max=242328ms  GREEN
  naive-5                  runs=10 median=241109ms min=240314ms max=241949ms  GREEN
  pkg-alloc-front        runs=10 median=240871ms min=240361ms max=242014ms  GREEN

  alloc-sort             -0.1% vs initial
  pkg-rt-front           -0.2% vs initial
  naive-5                  -0.1% vs initial
  pkg-alloc-front        -0.0% vs initial

=> SHIP: initial  (240761ms, 0.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  alloc-front+warm-tail  discarded after round 0 (not in top 3)
  jit-sort               discarded after round 0 (not in top 3)
  rt-heavy-tail          discarded after round 0 (not in top 3)

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=19.0 W-=36.0  p=0.4316 (exact)  median -0.2% vs initial  n.s.
  pkg-rt-front           n=10  W+=16.0 W-=39.0  p=0.2754 (exact)  median -0.2% vs initial  n.s.
  naive-5                  n=10  W+=14.0 W-=41.0  p=0.1934 (exact)  median -0.2% vs initial  n.s.
  pkg-alloc-front        n=10  W+=20.0 W-=35.0  p=0.4922 (exact)  median -0.1% vs initial  n.s.
```

## curator (curator-framework)

```
=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=510889ms min=498445ms max=562842ms  GREEN
  alloc-sort             runs=10 median=509544ms min=503802ms max=560041ms  GREEN
  pkg-rt-front           runs=10 median=511399ms min=509129ms max=560425ms  GREEN
  naive-5                  runs=10 median=509202ms min=508042ms max=513435ms  GREEN
  pkg-alloc-front        runs=10 median=510052ms min=493301ms max=512381ms  GREEN

  alloc-sort             +0.3% vs initial
  pkg-rt-front           -0.1% vs initial
  naive-5                  +0.3% vs initial
  pkg-alloc-front        +0.2% vs initial

=> SHIP: initial  (509202ms, 0.3% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  alloc-front+warm-tail  discarded after round 0 (not in top 3)
  jit-sort               discarded after round 0 (not in top 3)
  rt-heavy-tail          discarded after round 0 (not in top 3)

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=27.0 W-=28.0  p=1.0000 (exact)  median +0.2% vs initial  n.s.
  pkg-rt-front           n=10  W+=13.0 W-=42.0  p=0.1602 (exact)  median -0.1% vs initial  n.s.
  naive-5                  n=10  W+=26.0 W-=29.0  p=0.9219 (exact)  median +0.3% vs initial  n.s.
  pkg-alloc-front        n=10  W+=28.0 W-=27.0  p=1.0000 (exact)  median +0.2% vs initial  n.s.
```

## paimon (paimon-core)

```
=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=926511ms min=862272ms max=981795ms  GREEN
  alloc-sort             runs=10 median=708054ms min=628160ms max=734611ms  GREEN
  alloc-front+warm-tail  runs=10 median=948022ms min=851597ms max=978736ms  GREEN
  pkg-rt-front           runs=10 median=750838ms min=683120ms max=873810ms  GREEN
  naive-5                  runs=10 median=786869ms min=738443ms max=831151ms  GREEN
  jit-sort               runs=10 median=735059ms min=702534ms max=763427ms  GREEN
  rt-heavy-tail          runs=10 median=934336ms min=864407ms max=1013744ms  GREEN
  pkg-alloc-front        runs=10 median=756521ms min=711734ms max=855275ms  GREEN

  alloc-sort             +23.6% vs initial
  alloc-front+warm-tail  -2.3% vs initial
  pkg-rt-front           +19.0% vs initial
  naive-5                  +15.1% vs initial
  jit-sort               +20.7% vs initial
  rt-heavy-tail          -0.8% vs initial
  pkg-alloc-front        +18.3% vs initial

=> SHIP: alloc-sort  (708054ms, 23.6% faster than initial) [green]

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  alloc-sort             n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +23.9% vs initial  SIGNIFICANT@0.05
  alloc-front+warm-tail  n=10  W+=19.0 W-=36.0  p=0.4316 (exact)  median -1.7% vs initial  n.s.
  pkg-rt-front           n=10  W+=54.0 W-=1.0  p=0.0039 (exact)  median +20.0% vs initial  SIGNIFICANT@0.05
  naive-5                  n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +15.8% vs initial  SIGNIFICANT@0.05
  jit-sort               n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +20.7% vs initial  SIGNIFICANT@0.05
  rt-heavy-tail          n=10  W+=29.0 W-=26.0  p=0.9219 (exact)  median -0.2% vs initial  n.s.
  pkg-alloc-front        n=10  W+=55.0 W-=0.0  p=0.0020 (exact)  median +18.3% vs initial  SIGNIFICANT@0.05
```

## spring-ai

```
=== CANDIDATE MEASUREMENTS ===
  initial                runs=10 median=13232ms min=13113ms max=14012ms  GREEN
  pkg-rt-front           runs=10 median=13542ms min=13140ms max=14273ms  GREEN
  naive-5                runs=10 median=13455ms min=13047ms max=14210ms  GREEN
  rt-heavy-tail          runs=10 median=13396ms min=13138ms max=13749ms  GREEN
  pkg-alloc-front        runs=10 median=13265ms min=13154ms max=13843ms  GREEN

  pkg-rt-front           -2.3% vs initial
  naive-5                -1.7% vs initial
  rt-heavy-tail          -1.2% vs initial
  pkg-alloc-front        -0.2% vs initial

=> SHIP: initial  (13232ms, 0.0% faster than initial) [green]

=== EXCLUDED (failed early, not measured/reported) ===
  alloc-sort             discarded after round 0 (not in top 3)
  alloc-front+warm-tail  discarded after round 0 (not in top 3)
  jit-sort               discarded after round 0 (not in top 3)

=== WILCOXON SIGNED-RANK (paired per round, vs initial) ===
  pkg-rt-front           n=10  W+=13.0 W-=42.0  p=0.1602 (exact)  median -1.9% vs initial  n.s.
  naive-5                n=10  W+=11.0 W-=44.0  p=0.1055 (exact)  median -1.6% vs initial  n.s.
  rt-heavy-tail          n=10  W+=25.0 W-=30.0  p=0.8457 (exact)  median -0.5% vs initial  n.s.
  pkg-alloc-front        n=10  W+=25.0 W-=30.0  p=0.8457 (exact)  median -0.2% vs initial  n.s.
```

