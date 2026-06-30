| Project | Fastest Strategy | Initial Median Time | Naïve Median Time | Speedup Vs. Initial | Naïve Speedup Vs. Initial | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| apache/commons-csv | alloc-front+warm-tail | 12220ms | 11392ms | 16.8% | 6.8% | |
| javaparser/javaparser | pkg-rt-front | 13527ms | 12597ms | 23.3% | 6.9% | module: `javaparser-core-testing`; alloc-front and pkg-alloc-front are the same speedup |
| apache/commons-text | naive | 18185ms | 15657ms | 13.9% | 13.9% | Second best was jit-front with 13.6%
| apache/commons-math | pkg-alloc-front | 17195ms | 16422ms | 5.6% | 4.5% | Ran `commons-math-legacy`; Excluded 3 RNG-dependent tests (simplex optimizers) |
| alibaba/fastjson2 | pkg-alloc-front | 22462ms | 23171ms | 1.1% | -3.2% | Ran `core`; did not run with all approaches |
| javaparser/javaparser | alloc-sort | 22028ms | 22092ms | 11.1% | -0.3% | module: `symbol-solver-testing`; more measurement runs; alloc-front+warm-tail was close second |

# Logs

## commons-csv

```
=== CANDIDATE MEASUREMENTS ===
  pkg-alloc-front        runs=4 median=10358ms min=9821ms max=10559ms  GREEN
  naive                  runs=4 median=11392ms min=10253ms max=13185ms  GREEN
  alloc-sort             runs=4 median=10700ms min=10066ms max=10973ms  GREEN
  intra-warmup           runs=4 median=16803ms min=10670ms max=17678ms  GREEN
  pkg-alloc+observed-intra runs=4 median=10534ms min=10016ms max=10603ms  GREEN
  pkg-rt-front           runs=4 median=10258ms min=10207ms max=11302ms  GREEN
  jit-front              runs=4 median=11793ms min=10288ms max=12089ms  GREEN
  alloc-front            runs=4 median=10855ms min=10016ms max=11231ms  GREEN
  warm-tail              runs=4 median=12413ms min=11927ms max=13036ms  GREEN
  initial                runs=4 median=12220ms min=12156ms max=12875ms  GREEN
  alloc-front+warm-tail  runs=4 median=10170ms min=10020ms max=11454ms  GREEN

  pkg-alloc-front        +15.2% vs initial
  naive                  +6.8% vs initial
  alloc-sort             +12.4% vs initial
  intra-warmup           -37.5% vs initial
  pkg-alloc+observed-intra +13.8% vs initial
  pkg-rt-front           +16.1% vs initial
  jit-front              +3.5% vs initial
  alloc-front            +11.2% vs initial
  warm-tail              -1.6% vs initial
  alloc-front+warm-tail  +16.8% vs initial

=> SHIP: alloc-front+warm-tail  (10170ms, 16.8% faster than initial) [green]
```

## javaparser (core)

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=4 median=10527ms min=10151ms max=10552ms  GREEN
  jit-front              runs=4 median=10865ms min=9995ms max=11768ms  GREEN
  jfr-warmup-front       runs=4 median=12724ms min=11661ms max=12792ms  GREEN
  initial                runs=4 median=13527ms min=12879ms max=13694ms  GREEN
  pkg-alloc+observed-intra runs=4 median=10672ms min=9651ms max=11367ms  GREEN
  alloc-front+warm-tail  runs=4 median=10714ms min=9943ms max=12762ms  GREEN
  alloc-sort             runs=4 median=10545ms min=9805ms max=10996ms  GREEN
  warm-tail              runs=4 median=13625ms min=13282ms max=13729ms  GREEN
  pkg-alloc-front        runs=4 median=10515ms min=10058ms max=10691ms  GREEN
  pkg-rt-front           runs=4 median=10373ms min=10135ms max=11171ms  GREEN
  intra-warmup           runs=4 median=13656ms min=13009ms max=14477ms  GREEN
  naive                  runs=4 median=12597ms min=12028ms max=13235ms  GREEN

  alloc-front            +22.2% vs initial
  jit-front              +19.7% vs initial
  jfr-warmup-front       +5.9% vs initial
  pkg-alloc+observed-intra +21.1% vs initial
  alloc-front+warm-tail  +20.8% vs initial
  alloc-sort             +22.0% vs initial
  warm-tail              -0.7% vs initial
  pkg-alloc-front        +22.3% vs initial
  pkg-rt-front           +23.3% vs initial
  intra-warmup           -1.0% vs initial
  naive                  +6.9% vs initial

=> SHIP: pkg-rt-front  (10373ms, 23.3% faster than initial) [green]
```
## commons-text

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=4 median=15980ms min=15049ms max=16180ms  GREEN
  jit-front              runs=4 median=15719ms min=15057ms max=15884ms  GREEN
  jfr-warmup-front       runs=4 median=17420ms min=17110ms max=18086ms  GREEN
  initial                runs=4 median=18185ms min=17333ms max=18532ms  GREEN
  pkg-alloc+observed-intra runs=4 median=17685ms min=17018ms max=18026ms  GREEN
  alloc-front+warm-tail  runs=4 median=16012ms min=14738ms max=16945ms  GREEN
  alloc-sort             runs=4 median=15772ms min=15065ms max=16024ms  GREEN
  warm-tail              runs=4 median=16225ms min=15235ms max=16836ms  GREEN
  pkg-alloc-front        runs=4 median=18169ms min=17479ms max=18361ms  GREEN
  pkg-rt-front           runs=4 median=18026ms min=17424ms max=18609ms  GREEN
  intra-warmup           runs=4 median=18354ms min=17045ms max=18599ms  GREEN
  naive                  runs=4 median=15657ms min=15566ms max=16307ms  GREEN

  alloc-front            +12.1% vs initial
  jit-front              +13.6% vs initial
  jfr-warmup-front       +4.2% vs initial
  pkg-alloc+observed-intra +2.7% vs initial
  alloc-front+warm-tail  +11.9% vs initial
  alloc-sort             +13.3% vs initial
  warm-tail              +10.8% vs initial
  pkg-alloc-front        +0.1% vs initial
  pkg-rt-front           +0.9% vs initial
  intra-warmup           -0.9% vs initial
  naive                  +13.9% vs initial

=> SHIP: naive  (15657ms, 13.9% faster than initial) [green]
```

## commons-math

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=4 median=17862ms min=16605ms max=18316ms  GREEN
  jit-front              runs=4 median=17732ms min=17033ms max=18223ms  GREEN
  jfr-warmup-front       runs=4 median=17506ms min=16400ms max=18001ms  GREEN
  initial                runs=4 median=17195ms min=15024ms max=17436ms  GREEN
  pkg-alloc+observed-intra runs=4 median=17690ms min=16372ms max=17852ms  GREEN
  alloc-front+warm-tail  runs=4 median=17208ms min=16278ms max=17433ms  GREEN
  alloc-sort             runs=4 median=17555ms min=16755ms max=17568ms  GREEN
  warm-tail              runs=4 median=17825ms min=16939ms max=18457ms  GREEN
  pkg-alloc-front        runs=4 median=16268ms min=16184ms max=17531ms  GREEN
  pkg-rt-front           runs=4 median=16613ms min=14572ms max=16669ms  GREEN
  intra-warmup           runs=4 median=17637ms min=16489ms max=18169ms  GREEN
  naive                  runs=4 median=16422ms min=15712ms max=16700ms  GREEN

  alloc-front            -3.9% vs initial
  jit-front              -3.1% vs initial
  jfr-warmup-front       -1.8% vs initial
  pkg-alloc+observed-intra -2.9% vs initial
  alloc-front+warm-tail  -0.1% vs initial
  alloc-sort             -2.1% vs initial
  warm-tail              -3.7% vs initial
  pkg-alloc-front        +5.4% vs initial
  pkg-rt-front           +3.4% vs initial
  intra-warmup           -2.6% vs initial
  naive                  +4.5% vs initial

=> SHIP: pkg-alloc-front  (16268ms, 5.4% faster than initial) [green]
```

## fastjson2

```
=== CANDIDATE MEASUREMENTS ===
  pkg-alloc-front        runs=4 median=22225ms min=21752ms max=28755ms  GREEN
  alloc-front            runs=4 median=22329ms min=20884ms max=30967ms  GREEN
  pkg-rt-front           runs=4 median=22699ms min=20684ms max=27009ms  GREEN
  jit-front              runs=4 median=25223ms min=21982ms max=26049ms  GREEN
  initial                runs=4 median=22462ms min=21079ms max=23473ms  GREEN
  naive                  runs=4 median=23171ms min=21177ms max=24225ms  GREEN

  pkg-alloc-front        +1.1% vs initial
  alloc-front            +0.6% vs initial
  pkg-rt-front           -1.1% vs initial
  jit-front              -12.3% vs initial
  naive                  -3.2% vs initial

=> SHIP: pkg-alloc-front  (22225ms, 1.1% faster than initial) [green]
```

## javaparser (symbol-solver-testing)

```
=== CANDIDATE MEASUREMENTS ===
  alloc-front            runs=8 median=20223ms min=18357ms max=21403ms  GREEN
  jit-front              runs=8 median=20091ms min=18682ms max=21415ms  GREEN
  jfr-warmup-front       runs=8 median=21261ms min=18638ms max=22825ms  GREEN
  initial                runs=8 median=22028ms min=19649ms max=24125ms  GREEN
  pkg-alloc+observed-intra runs=8 median=21409ms min=19064ms max=22399ms  GREEN
  alloc-front+warm-tail  runs=8 median=19869ms min=18205ms max=21675ms  GREEN
  alloc-sort             runs=8 median=19593ms min=18516ms max=21517ms  GREEN
  warm-tail              runs=8 median=20768ms min=18838ms max=22793ms  GREEN
  pkg-alloc-front        runs=8 median=21095ms min=18840ms max=22593ms  GREEN
  pkg-rt-front           runs=8 median=20873ms min=18911ms max=22837ms  GREEN
  intra-warmup           runs=8 median=22215ms min=19647ms max=23461ms  GREEN
  naive                  runs=8 median=22092ms min=19703ms max=24353ms  GREEN

  alloc-front            +8.2% vs initial
  jit-front              +8.8% vs initial
  jfr-warmup-front       +3.5% vs initial
  pkg-alloc+observed-intra +2.8% vs initial
  alloc-front+warm-tail  +9.8% vs initial
  alloc-sort             +11.1% vs initial
  warm-tail              +5.7% vs initial
  pkg-alloc-front        +4.2% vs initial
  pkg-rt-front           +5.2% vs initial
  intra-warmup           -0.8% vs initial
  naive                  -0.3% vs initial

=> SHIP: alloc-sort  (19593ms, 11.1% faster than initial) [green]
```