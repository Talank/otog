# Order pairs used in the reported measurements

Each row lists two order files compared in `csto2/findings/mechanisms.md`.
Both files contain the same tests. In repeated runs, the faster order has a
lower total test-suite time than the slower order. The report explains why.
Use the project revision and JVM named in the report when you repeat the
comparison.

| Report section | Faster order | Slower order |
|---|---|---|
| 3. OpenPojo cache | `openpojo-structural-then-identity.order` | `openpojo-identity-then-structural.order` |
| 4. JavaParser lexical preservation | `javaparser-javadoc-then-lpp.order` | `javaparser-lpp-then-javadoc.order` |
| 5. SnakeYAML initialization | `snakeyaml-warm-consumers-last.order` | `snakeyaml-cold-consumers-first.order` |
| 6. JavaParser symbol solver | `javaparser-symbol-type-solver-back.order` | `javaparser-symbol-type-solver-front.order` |
| 7. Commons Text inline mock, pair | `commons-text-reader-then-append-insert.order` | `commons-text-append-insert-then-reader.order` |
| 7. Commons Text inline mock, prefix | `commons-text-reader-prefix-early.order` | `commons-text-reader-prefix-late.order` |
| 8. AsyncHttpClient leak policy | `async-multipart-body-reset-peer.order` | `async-reset-peer-multipart-body.order` |
| 9. AsyncHttpClient pool policy | `async-paper-keepalive-restored-heavy-consumers.order` | `async-paper-keepalive-false-heavy-consumers.order` |
| 10. Gson iterator optimization | `gson-linked-then-object.order` | `gson-object-then-linked.order` |
| 11. SnakeYAML compiler queue | `snakeyaml-references-then-stress.order` | `snakeyaml-stress-then-references.order` |
| 12. SnakeYAML Java 8 regular expression | `snakeyaml-compact-regex-front.order` | `snakeyaml-compact-regex-back.order` |
