# Statistical validity of `select` winners (Wilcoxon signed-rank)

Re-measured each project's `speedups.md` winner against `initial` with 10 fresh paired runs and a two-sided Wilcoxon signed-rank test (α = 0.05); only 3 of the 6 originally reported wins hold up.

| Project | Winning strategy | Median `initial` | Median winner | Δ median | p-value | Significant? |
| --- | --- | --- | --- | --- | --- | --- |
| commons-math (`commons-math-legacy`) | pkg-alloc-front | 16722 ms | 16775 ms | -0.3% | 1.000 | No |
| fastjson2 (`core`) | pkg-alloc-front | 21940 ms | 21952 ms | -0.05% | 0.415 | No |
| commons-csv | alloc-front+warm-tail | 12356 ms | 11093 ms | +10.2% | 0.008 | Yes |
| commons-text | naive | 16306 ms | 16036 ms | +1.7% | 0.067 | No |
| javaparser (`javaparser-core-testing`) | pkg-rt-front | 18352 ms | 15879 ms | +13.5% | 0.006 | Yes |
| javaparser (`javaparser-symbol-solver-testing`) | alloc-sort | 11435 ms | 10915 ms | +4.5% | 0.008 | Yes |

## Procedure

For each project, the winning strategy's `.csto2` order (regenerating it from scratch via `discover`/`trace`/`select` where it had been deleted) was measured against `initial` for 10 fresh, interleaved repeats with the instrumentation agent off, and the resulting paired per-run total wall-clock times were compared with a two-sided Wilcoxon signed-rank test at α = 0.05.

**Excluded tests** (failed consistently regardless of order, unrelated to ordering):
- commons-text: `TextStringBuilderTest` — deliberately triggers `OutOfMemoryError`, which the fork's `-XX:OnOutOfMemoryError=kill` flag treats as fatal.
- javaparser-symbol-solver-testing: `ReflectionInterfaceDeclarationTest`, `ReflectionClassDeclarationTest`, `ReferenceTypeTest`, `JavaParserInterfaceDeclarationTest`, `JavaParserEnumDeclarationTest`, `JavaParserClassDeclarationTest` - using JDK 23 instead of JDK 8 breaks all of these.
