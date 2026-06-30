# CSTO2 Adoption Strategy: CI Piggybacking

Similar to prior research, CSTO2 could trace and measure during CI runs of the test suite that would happen anyway.

The first few commits are traced with MXBeans. Each commit after that measures a different method (e.g. alloc-sort). After more commits, we will have sufficient information to determine the best order. Since more tests are added between commits, only the subset of tests from when the process was started will be optimized. The rest will just be added at the end of the order, or inserted arbitrarily.

Once around one hundred commits have passed, the order will likely be stale. A large percent of it is tests that were not present during the optimizing phase, and are therefore inserted in arbitrary positions. At this point, the process will begin again.