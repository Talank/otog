# JDK 26 AOT cache benefits fresh-fork test workloads

*2026-07-16 (week 2026-W29)*

A 13-class `curator-framework` workload took 68.48 s with AOT disabled and 53.60 s with a JDK 26 AOT cache, a 21.7% wall-time reduction; user CPU fell from 15.26 s to 10.58 s. Each class ran in a separate JVM, matching Curator's `<reuseForks>false</reuseForks>` configuration, and every fork passed. The 41 MiB cache was trained on `TestReconfiguration`, contained 5,383 classes and 4,371 method-training records, and was reused by all 13 forks.

The improvement depended on repeated JVM startup: Gson improved from 0.98 s to 0.65 s, while reused-fork Jackson Core and JGraphT workloads improved by 0% and 1.3%, respectively. The Curator result uses one uncached and one cached measurement without paired replication, so it demonstrates a qualifying case rather than a stable effect-size estimate.
