# Order pairs used in the reported measurements

Each row names the two order files used for a baseline comparison in
`csto2/findings/mechanisms.md`. The two files contain the same tests. The
faster order repeatedly has a lower complete-suite run time than the slower
order in the documented experiment. The report gives the mechanism that makes
the direction stable. The project revision and JVM are part of the experiment
definition. Some files were copied from ignored run output or an external
project checkout so that a fresh clone keeps the measured inputs.

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
