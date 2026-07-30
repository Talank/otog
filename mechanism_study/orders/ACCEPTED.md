# Accepted test orders

These are the exact order files used by the confirmed results in
`csto2/findings/mechanisms.md`. Files under `accepted/` were copied from
ignored run output or an external project checkout so that a fresh clone keeps
the measured inputs.

| Report section | First order | Reverse order |
|---|---|---|
| 3. OpenPojo cache | `openpojo-structural-then-identity.order` | `openpojo-identity-then-structural.order` |
| 4. JavaParser lexical preservation | `javaparser-javadoc-then-lpp.order` | `javaparser-lpp-then-javadoc.order` |
| 5. SnakeYAML initialization | `accepted/snakeyaml-cold-consumers-first.order` | `accepted/snakeyaml-warm-consumers-last.order` |
| 6. JavaParser symbol solver | `accepted/javaparser-symbol-type-solver-front.order` | `accepted/javaparser-symbol-type-solver-back.order` |
| 7. Commons Text inline mock, pair | `commons-text-reader-then-append-insert.order` | `commons-text-append-insert-then-reader.order` |
| 7. Commons Text inline mock, prefix | `commons-text-reader-prefix-early.order` | `commons-text-reader-prefix-late.order` |
| 8. AsyncHttpClient leak policy | `async-multipart-body-reset-peer.order` | `async-reset-peer-multipart-body.order` |
| 9. AsyncHttpClient pool policy | `async-paper-keepalive-restored-heavy-consumers.order` | `async-paper-keepalive-false-heavy-consumers.order` |
| 10. Gson iterator optimization | `accepted/gson-linked-then-object.order` | `accepted/gson-object-then-linked.order` |
| 11. SnakeYAML compiler queue | `accepted/snakeyaml-references-then-stress.order` | `accepted/snakeyaml-stress-then-references.order` |
| 12. SnakeYAML Java 8 regular expression | `snakeyaml-compact-regex-front.order` | `snakeyaml-compact-regex-back.order` |
