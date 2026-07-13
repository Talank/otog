# Candidate Strategies

Below are the different ordering strategies used by csto2.

A strategy beginning with "pkg" means that intra-package class orders are kept the same, and only packages are reordered.

Generally, if a strategy ends with "front", that means that it moves only a few outliers instead of performing a global sort. "*-sort" on the other hand performs a global sort. However, this rule is unfortunately not always followed.

| Method | Metrics used | Sort technique | Reasoning
| --- |  --- | --- | --- |
| initial | None | The as-given/default order, unchanged | The protected incumbent. Every speedup is measured against it, and it ships if nothing beats it.
| naive | Total runtime of each traced order | Picks the fastest fully-covered order among those already traced | A free baseline. A real optimizer win must beat naive, not just initial.
| pkg-alloc-front (should be pkg-alloc-sort) | Memory allocation of each class | Global sort of package blocks by their total allocation | Placing heavier allocators earlier can make them faster, since they're using a fresh heap with less to GC. Keeping classes together in packages can help trigger speculative compilation (since the fact that two classes are in the same package probably means they're hitting a lot of the same methods). I still don't really understand this mechanism. 
| alloc-sort | Median total allocation | Classes are globally sorted by mean total allocation | Allocations on a fresh heap are faster |
| jit-sort | JIT compilation time | Classes are globally sorted by median time spent on JIT compilation. Higher JIT time goes at the front. | The idea is that classes that "warm up" shared methods through JIT compilation are moved to the front. [In practice, though, JIT time varies wildly](jit-vs-position.svg). This method should likely be refined. |
| alloc-front+warm-tail | Median allocation, runtime vs. position | Two moves at once. Allocation outliers (3 standard deviations above the mean) go to the front. Classes whose per-class least-squares fit of runtime against position has a confident negative slope go to the tail. | Combines a front move (fresh heap for heavy allocators) with a tail move (classes that run faster late, after shared state is warm). *What to do in case of overlap?*
| pkg-rt-front (should be pkg-rt-sort) | Total package runtime | Sorts all packages by total median runtime across shuffle runs. | Unknown why this works. Likely because of [chance overlap with other strategies](overlap.md)
| rt-heavy-tail | Class runtime | Moves runtime-heavy outliers to the end of the test suite | Unknown why this works. +11.3% on snakeyaml.
