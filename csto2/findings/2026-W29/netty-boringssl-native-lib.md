# netty (33, 20): missing OpenSSL 1.0 broke SSL tests — fixed with `-Pboringssl`

*2026-07-13 (week 2026-W29)*

Module 33's SSL tests need `netty-tcnative`, which dynamically links against OpenSSL 1.0.x — a
library our container's Debian base doesn't have and can't install. Fix: added `-Pboringssl` to
`mvnopts` in `33.properties` and `20.properties` (same dependency), which swaps in a self-contained
static build needing no system OpenSSL. No code changes required. Not yet re-verified end-to-end.
