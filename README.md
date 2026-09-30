# optimal test order

Does the order tests run in change how long a suite takes, and can an order be
chosen in advance that is reliably faster than a random one?

16 Maven modules from real projects, each at 201 versions. At every version the
same suite is run in 100 random orders, three times each, one container per run
with 4 CPUs and 16 GB. Runtime is always the sum of the surefire reports, never
wall time. Three approaches then try to beat that reference, and a naive
baseline -- keep whichever past order was fastest -- is the bar they have to
clear.

## Where to look

| | |
|---|---|
| `tool/` | the campaign: containers, runners, the order trees, the approaches |
| `summary_merged_runs/` | what every run cost, per test. 9.9 GB, 36,189 orders |
| `analysis/` | three scripts, from the summaries to the tables |
| `results/` | the tables, and `master.csv`, the only measured file |

Start with `results/README.md` for what was found, `tool/README.md` for how a run
is made, and `tool/docs/findings.md` for what the numbers do and do not support
-- read that before quoting any cross-approach comparison.

## The shortest path to a number

```bash
python3 analysis/build_master.py summary_merged_runs results/master.csv
python3 analysis/summarize_master.py results/master.csv results
```

Needs `pandas`. That rebuilds every table in `results/` from the summarized runs;
nothing else is required and there is no notebook.

## What is not here

`csto2/`, `mechanism_study/`, `mechdetect/`, `sort_experiment/`,
`docker_template/`, `jfrsort/` and `old_things/` are earlier, separate work kept
for the record. They are not part of this campaign and nothing above reads them.

The raw runs -- every surefire report, every JFR recording -- are far larger than
this repository and stay on the machine that produced them.
