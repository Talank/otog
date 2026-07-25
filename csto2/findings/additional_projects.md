# Additional Projects (Beyond Paper Eval Dataset)

All runs executed with `reuseForks=true` (`forkCount=1`).

## Additional projects table

| Project | Module | Strategy | Initial | Naïve-5 | Optimal V. Initial | Optimal V. Naive-5 | p (init v. optimal) | p (n-5 v. optimal) | Notes |
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
