# approaches

An approach reads measured test orders and writes one order for a target
version. Every approach gets the same inputs and is installed the same way, so
the only difference between them is the rule.

| approach | in one sentence | modules |
|---|---|---|
| `jfrsort` | rank test classes by the heap they allocate, read from the JFR recordings | 10 |
| `warmsort` | estimate per-test cost and the early-order penalty, then construct the order those estimates imply | 16 |
| `agentic` | hand an agent the past versions' runtimes and a time budget; it generates and measures candidate orders and keeps its best | 16 / 15 / 15 |

`jfrsort` covers 10 because six of the sixteen suites emit no class-window events
for it to read — see `../docs/notes/jfrsort.txt`. Nothing was excluded for
producing a bad order.

## The input sets

The same approach judged on what it was allowed to learn from. Each is installed
under a name that says which it is, so `orders/<module>/<version>/` stays
readable: 1..100 are the random orders, `warmsort_past_99.txt` is this one.

| name | learns from | pairs with |
|---|---|---|
| `v0_99` | v0's other 99 random orders | `naive_v0_99` |
| `past_24` | versions v-1..v-24, one order each | `naive_25` |
| `past_49` | v-1..v-49 | `naive_50` |
| `past_74` | v-1..v-74 | `naive_75` |
| `past_99` | v-1..v-99 | `naive_100` |

The windows are cumulative, and the two families count differently: the naive
columns count *versions* (`naive_50` is the best of the 50 most recent past
versions) while an approach's suffix is an *offset* (`past_49` learned from
v-1..v-49). Both span the same 50 versions, which is why the table pairs them.

`v0_99` is the cold-start set: it is the only one that sees the target version
itself, so it is an upper bound on what history could have told the approach,
not a fair forecast.

`agentic` is the exception. Its sessions belong to a collaborator, three of the
five exist, and its history windows are slices rather than the cumulative spans
above — `agentic/README.md` says which versions each session read.

## Running one

```bash
bash approaches/warmsort/sweep_warmsort.sh 1685 /tmp/orders
bash approaches/jfrsort/sweep_jfrsort.sh   1685 /tmp/orders
```

Each writes its five orders to `<out_dir>` and installs them into
`orders/<module>/<version>/`. warmsort reads `summary_merged_runs`; jfrsort reads
the JFR recordings. `OTOG_SUMMARY` and `OTOG_JFRSORT_WORK` say where.

Installing an order on its own:

```bash
python3 approaches/common/install_order.py <module> <order.txt> <name> <tool_dir>
```

It writes `orders/<module>/0/<name>.txt`, adapts it forward to every future
version by the campaign's rule — drop deleted tests, append added ones — refuses
an order that is not v0's test set, and never overwrites.

## Provenance

| file | where it came from |
|---|---|
| `jfrsort/*`, `warmsort/*` | ours |
| `agentic/` | a collaborator's agent runs; see `agentic/README.md` |
| `common/install_order.py`, `common/adapt_to_target.py` | ours |

## Before comparing approaches

Each approach's runs were collected on its own day, and the day alone moves a
suite's runtime by up to 27% on orders whose composition never changed. A board
that pools across days measures the calendar as much as the method.
`../scripts/same_batch_board.py` scores only within one collection window;
`../docs/findings.md` has the measurement.
