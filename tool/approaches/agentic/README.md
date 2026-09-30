# agentic

An LLM agent is handed a module's past versions — the orders that ran at each and
what they cost — and a time budget. Inside that budget it generates candidate
orders, measures them, and keeps its fastest.

The agent runs belong to a collaborator, so what ships here is the record of each
session, not the code that drove it. The orders themselves are campaign data:
`install_order.py` writes each to `tool/orders/<module>/<version>/agentic_<set>.txt`.

## Three input sets

| installed as | context_versions | budget_versions | column |
|---|---|---|---|
| `agentic_v0_99` | v0's own measured orders | — | `ag_v0_99` |
| `agentic_past_24` | -1..-15 | -16..-25 | `ag_24` |
| `agentic_past_74` | -51..-65 | -66..-75 | `ag_74` |

The windows come from each session's own `summary.csv`, and all 15 sessions of a
set carry the same pair. `past_24` spans v-1..v-25, the minus25 band. `past_74`
reaches v-75, the outer edge of minus75. The directory names `mode4/1to15` and
`mode4/51to65` are the context window, not the band.

**`ag_74` sits on less history than the column around it.** The other approaches'
`past_74` is cumulative v-1..v-74 and `naive_75` is the best over v-1..v-75; the
agentic session never saw v-1..v-50. Same band edge, smaller information set —
which understates agentic in that row rather than flattering it, so the column is
still the honest place for it. `ag_24` has a milder version of the same gap.

`past_49` and `past_99` stay empty: an agent given v-51..v-75 was not given
v-1..v-49, and filing the same order under another band would invent a
measurement.

## Coverage

`agentic_v0_99` covers 16 modules, both history sets cover the same 15 — module
3320 has no session. Two `v0_99` modules have two session directories and only
one of each pair carries an order; the session named here is always the one that
produced it.

## The files

`sessions_<set>.csv` is one row per session: the versions it saw, its budget,
what it generated and measured, tokens and cost. `results_overview_<set>.csv` is
the collaborator's own summary — best runtime per module, and whether the agent
or the best historical order won. Every `*_file`, `*_path` and `*_csv` column was
dropped; they were absolute paths into the machine the agent ran on.

## How the orders were installed

```bash
python3 approaches/common/install_order.py <module> <agent_best_order.txt> agentic_past_74 <tool_dir>
```

Then v0 and the ten x10 versions, 3 repetitions, the same container as every
other order: 15 x 11 x 3 = 495 runs per history set, 16 x 11 x 3 for `v0_99`.

Notes: `../../docs/notes/agentic_v0.txt`, `agentic_past24.txt`, `agentic_past74.txt`.
