# Candidate Strategies

Below are the different ordering strategies used by csto2.

A strategy beginning with "pkg" means that intra-package class orders are kept the same, and only packages are reordered.

Generally, if a strategy ends with "front", that means that it moves only a few outliers instead of performing a global sort. "*-sort" on the other hand performs a global sort. However, this rule is unfortunately not always followed.

| Method | Metrics used | Sort technique | Reasoning
| --- |  --- | --- | --- |
| pkg-alloc-front (should be pkg-alloc-sort) | Memory allocation of each class | Global sort of package blocks by their total allocation | Placing heavier allocators earlier can make them faster, since they're using a fresh heap with less to GC. Keeping classes together in packages can maintain cache locality.
| alloc-front | Median total allocation | Any class with total allocation more than 3 standard deviations above the mean is moved to the beginning of the suite | Allocations on a fresh heap are faster. Not disturbing the established order can sometimes perform better.
| alloc-sort | Median total allocation | Classes are globally sorted by mean total allocation | Allocations on a fresh heap are faster |
| jit-sort | JIT compilation time | Classes are globally sorted by median time spent on JIT compilation. Higher JIT time goes at the front. | The idea is that classes that "warm up" shared methods through JIT compilation are moved to the front. [In practice, though, JIT time varies wildly](jit-vs-position.svg). This method should likely be refined. |
| jit-front | JIT compilation time | Same as jit-sort, but moves outliers to the front (3 standard deviations above mean) instead of performing a global sort. |
| warm-tail | Runtime vs. position | Per-class least-squares fit of runtime against position. Each data point is (position in suite, runtimeMS), and classes with a negative slope are assumed to get faster as they are moved to the end of the suite. | Stumbles upon classes that heavily utilize shared resources + cache.
| alloc-front+warm-tail | Median allocation, runtime vs. position | Direct combination of alloc-front and warm-tail | Combines a strategy that only affects the front with one that only affects the back. *What to do in case of overlap?*
| pkg-rt-front (should be pkg-rt-sort) | Total package runtime | Sorts all packages by total median runtime across shuffle runs. | Unknown why this works. Likely because of [chance overlap with other strategies](overlap.md)
| rt-heavy-tail | Class runtime | Moves runtime-heavy outliers to the end of the test suite | Unknown why this works. +11.3% on snakeyaml.
