# A/B Runtime Comparison: Naive vs CSTO2 Orders

## Module 1683
**CSTO Strategy**: `alloc-front+warm-tail`  
**Runs**: 5 paired iterations  
**Wilcoxon Signed-Rank Test**: W+=15.0, W-=0.0, p-value=0.0625 (Significant at 0.05? **NO**)  
**Median Speedup**: 9.54% (Naive: 30092ms vs CSTO: 27220ms)  

| Metric | Naive Order | CSTO Order | Difference |
|---|---|---|---|
| Median | 30092 ms | 27220 ms | 2872 ms (9.5%) |
| Min | 28826 ms | 26491 ms | 2335 ms |
| Max | 31664 ms | 28051 ms | 3613 ms |

### Runtimes per Run
| Run | Naive Runtime | CSTO Runtime | Speedup |
|---|---|---|---|
| 1 | 31664 ms | 27220 ms | 4444 ms (14.0%) |
| 2 | 30092 ms | 26491 ms | 3601 ms (12.0%) |
| 3 | 28826 ms | 27332 ms | 1494 ms (5.2%) |
| 4 | 29570 ms | 28051 ms | 1519 ms (5.1%) |
| 5 | 31227 ms | 27198 ms | 4029 ms (12.9%) |

## Module 1685
**CSTO Strategy**: `pkg-alloc-front`  
**Runs**: 5 paired iterations  
**Wilcoxon Signed-Rank Test**: W+=15.0, W-=0.0, p-value=0.0625 (Significant at 0.05? **NO**)  
**Median Speedup**: 18.08% (Naive: 24852ms vs CSTO: 20360ms)  

| Metric | Naive Order | CSTO Order | Difference |
|---|---|---|---|
| Median | 24852 ms | 20360 ms | 4492 ms (18.1%) |
| Min | 23277 ms | 20343 ms | 2934 ms |
| Max | 26467 ms | 20792 ms | 5675 ms |

### Runtimes per Run
| Run | Naive Runtime | CSTO Runtime | Speedup |
|---|---|---|---|
| 1 | 26467 ms | 20343 ms | 6124 ms (23.1%) |
| 2 | 24852 ms | 20349 ms | 4503 ms (18.1%) |
| 3 | 23695 ms | 20792 ms | 2903 ms (12.3%) |
| 4 | 23277 ms | 20360 ms | 2917 ms (12.5%) |
| 5 | 25096 ms | 20443 ms | 4653 ms (18.5%) |

## Module 1778
**CSTO Strategy**: `pkg-rt-front`  
**Runs**: 5 paired iterations  
**Wilcoxon Signed-Rank Test**: W+=5.0, W-=10.0, p-value=0.6250 (Significant at 0.05? **NO**)  
**Median Speedup**: -10.11% (Naive: 5943ms vs CSTO: 6544ms)  

| Metric | Naive Order | CSTO Order | Difference |
|---|---|---|---|
| Median | 5943 ms | 6544 ms | -601 ms (-10.1%) |
| Min | 5920 ms | 6513 ms | -593 ms |
| Max | 8229 ms | 6688 ms | 1541 ms |

### Runtimes per Run
| Run | Naive Runtime | CSTO Runtime | Speedup |
|---|---|---|---|
| 1 | 8229 ms | 6573 ms | 1656 ms (20.1%) |
| 2 | 6015 ms | 6688 ms | -673 ms (-11.2%) |
| 3 | 5920 ms | 6513 ms | -593 ms (-10.0%) |
| 4 | 5943 ms | 6529 ms | -586 ms (-9.9%) |
| 5 | 5937 ms | 6544 ms | -607 ms (-10.2%) |

## Module 3613
**CSTO Strategy**: `alloc-sort`  
**Runs**: 5 paired iterations  
**Wilcoxon Signed-Rank Test**: W+=4.0, W-=11.0, p-value=0.4375 (Significant at 0.05? **NO**)  
**Median Speedup**: -4.25% (Naive: 694421ms vs CSTO: 723964ms)  

| Metric | Naive Order | CSTO Order | Difference |
|---|---|---|---|
| Median | 694421 ms | 723964 ms | -29543 ms (-4.3%) |
| Min | 686792 ms | 681033 ms | 5759 ms |
| Max | 721552 ms | 773529 ms | -51977 ms |

### Runtimes per Run
| Run | Naive Runtime | CSTO Runtime | Speedup |
|---|---|---|---|
| 1 | 692846 ms | 712586 ms | -19740 ms (-2.8%) |
| 2 | 720346 ms | 735913 ms | -15567 ms (-2.2%) |
| 3 | 721552 ms | 681033 ms | 40519 ms (5.6%) |
| 4 | 686792 ms | 723964 ms | -37172 ms (-5.4%) |
| 5 | 694421 ms | 773529 ms | -79108 ms (-11.4%) |

