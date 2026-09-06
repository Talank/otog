# Running on a SLURM cluster

The scripts do not need SLURM — `run_experiment.sh` is its own scheduler. On a
cluster you use SLURM to get *machines*, then run it on them. Two ways.

## A: one job, many containers (simplest)

Ask for a whole node, then let `run_experiment.sh` fill it.

```bash
#!/bin/bash
#SBATCH --job-name=otog
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=12:00:00
#SBATCH --output=otog.%j.out

module load apptainer
cd $SCRATCH/otog_v2_2

bash run_experiment.sh
```

`PARALLEL=auto` sizes itself to whatever the node has. Submit with `sbatch`.
Resumable, so requeue it as often as you like.

## B: one job per run (better on a busy cluster)

Small jobs backfill into gaps that a whole-node job never gets. One repetition
per job:

```bash
#!/bin/bash
#SBATCH --job-name=otog_one
#SBATCH --cpus-per-task=6
#SBATCH --mem=24G
#SBATCH --exclusive
#SBATCH --time=01:00:00

module load apptainer
cd $SCRATCH/otog_v2_2

read -r SLUG MODULE SHA <<< "$(awk -F, -v m=$M -v v=$V \
    'NR>1 && $1==m && $4==v {print $2" "$3" "$5; exit}' data/versions.csv)"

bash run_once.sh "$SLUG" "$MODULE" "$SHA" \
     "runs/$M/$V/order_$O/run_$R" "orders/$M/$V/$O.txt"
```

```bash
sbatch --export=ALL,M=1685,V=0,O=1,R=1 one.sbatch
```

Ask for **6 CPUs and 24 GB** even though the container is 4 and 16: the extra
absorbs maven, the JVM outside the test fork, and the OS, so the container
actually gets its full share.

## Which to use

| | A: node per job | B: run per job |
|---|---|---|
| queue wait | long — needs a whole free node | short — backfills |
| jobs to manage | few | thousands |
| best when | the cluster is quiet | the cluster is busy |

`--exclusive` matters in both: two containers sharing a node share its page
cache and memory bandwidth, and the second order at a version then reads its
jars out of RAM where the first had to fetch them from disk.

## Watching it

```bash
squeue -u $USER
find runs -name status | wc -l                       # runs finished
find runs -name status -exec grep -L '^PASS' {} + | head   # any that did not
```

## If jobs will not start

`squeue -u $USER -o '%.12i %.10T %.20r'` — `Reason=Priority` means fairshare,
not a fault in the setup, and nothing about the experiment will change it.
Shorter `--time` backfills better; `--exclusive` is the biggest limiter but is
not negotiable, since dropping it makes every timing incomparable.
