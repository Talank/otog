# analysis

Three scripts. One turns the summarized runs into `master.csv`, one turns
`master.csv` into the tables in `../results/`, and one measures what the JFR
recording cost.

```bash
# runs/ -> one order.txt + tests.csv per order          (in the tool)
python3 ../tool/scripts/summarize_runs.py <runs_dir> <summary_dir> "" 8 --all-runs

# summary_dir -> master.csv: seconds per module-version-order
python3 build_master.py <summary_dir> ../results/master.csv

# master.csv -> every summary table
python3 summarize_master.py ../results/master.csv ../results

# the profiled runs -> what recording cost, per order and per module
python3 jfr_overhead.py <summary_dir> /tmp/jfr_overhead.csv
```

Needs `pandas`. Nothing else, and no notebook.

## What each step is responsible for

**`../tool/scripts/summarize_runs.py`** reads the surefire reports and writes,
per order, the order that was run and what each test in it cost. It is the only
thing that ever parses a surefire report, and the only source of a runtime
anywhere in this campaign — wall time swings with machine load by a factor of 25
and would rank the machine rather than the order.

Pass `--all-runs` once repetitions 4 and 5 exist. It keeps `avg_time` at
run_1..run_3 so the three-repetition figures every published number rests on do
not move when a later repetition lands, and puts the full picture beside it in
`average_all_runs`. Without the flag, orders summarized later get a 7-column
`tests.csv` while the rest have the 11-column one.

**`build_master.py`** reduces that to one row per module-version. Two decisions
in it matter more than the arithmetic:

- **The common test set.** Every cell is measured over the tests that passed in
  every repetition of all 100 random orders at that module-version. Two orders
  of the same version can run different numbers of tests, and an order is not
  faster for having skipped one.
- **Which average.** `avg_time` (run_1..run_3) by default, `average_all_runs`
  with `--all-runs`. The two disagree by tens of percent in a cell whose extra
  repetition was unusual, so a table has to be built from one or the other and
  never a mixture.
- **The reference is kept, not just its mean.** The last column,
  `random_times`, holds all hundred random runtimes `;`-separated and in order,
  at full precision, so `random_average` can be checked and the spread of the
  reference read directly. A missing order is `NA` in its own position, so the
  field always has a hundred entries.

**`summarize_master.py`** does the averaging and the comparisons. It writes
eleven tables plus one per module; `../results/README.md` lists them.

**`jfr_overhead.py`** compares each order's `tests_jfr.csv` against its
`tests.csv`. Only v0 and the historical versions have profiled repetitions, so
only those order dirs carry both. Both files' `avg_time` covers three
repetitions -- run_1..run_3 plain, jfr_run_1..jfr_run_3 profiled -- and the
totals are summed over the tests that passed in both, because a test missing
from one side would otherwise read as a speedup. Its `overhead_pct` is positive
when recording made the order slower, so it does not follow the sign convention
below; it is a cost, not a saving.

## The sign

`+` is faster, `-` is slower, in every table and every csv. The reference is
`random_average` in the `summary_*` tables and the naive of the same history
budget in the `vs_naive_*` ones, so `+12` is twelve percent off its runtime and
`-12` is twelve percent added.

## Two things the averaging does on purpose

**Two stages, not one flat mean.** A cell figure is the mean over versions of
the mean over modules, `mean_v( mean_m( saving(m, v) ) )` — not one mean over
all 176 cells. The two agree only when every version carries the same modules;
in two stages each version counts once however many modules landed in it.

**Mean and median together.** They disagree sharply. A few cells run several
times the random average on the same passing tests, and one such cell drags a
column down by tens of percent. `summary_table_median.csv` keeps the
outer stage a mean over versions and takes a median over modules inside it, so
one ruinous module cannot speak for the version.

And coverage is not optional: jfrsort has no order for 6 of the 16 modules, so
its column averages 110 cells where naive averages 176. Read
`summary_table_coverage.csv` beside any headline, and
`summary_table_matched.csv` when ranking approaches against each other.
