# OTOG — does test order change how long a suite takes?

Runs one test order, at one commit, in a fixed container, and records what it
cost. Works on a laptop, a server, an AWS instance, a CloudLab node or a SLURM
cluster — anywhere with Docker or Apptainer.

## Start

```bash
bash setup.sh docker          # once. or: bash setup.sh apptainer
bash run_experiment.sh        # the whole experiment
```

`setup.sh` prints how many containers your machine fits. `run_experiment.sh`
sizes itself to that automatically — no configuration needed to start.

It is **resumable**: a repetition that already passed is skipped, so you can
stop it and re-run it any time.

## Run a subset

Everything is in the variables at the top of `run_experiment.sh`:

```bash
MODULES="1685 1683 1778 ..."   # which projects
PHASES="v0 historical x10 x5"  # priority order, first to last
ORDERS="1 100"                 # first and last order number
REPEATS=3
PARALLEL=auto                  # auto = as many as CPUs and memory allow
JFR=false
```

One module, version 0, first ten orders:

```bash
MODULES="1685"
PHASES="v0"
ORDERS="1 10"
```

`work_list.txt` is written before anything runs, so you can always see exactly
what it is about to do.

## Run one order yourself

```bash
bash run_once.sh <slug> <module> <sha> <out_dir> [order_file] [jfr]

bash run_once.sh javaparser/javaparser javaparser-core-testing \
     2c8ce56933b17e6fa6fd9638aeaff604b24dd6c7 \
     /tmp/myrun orders/1685/0/1.txt
```

The order file is one `pkg.Class#method` per line. **Any** file works — a
solver's output, a hand-written order, anything — so this is how you try your
own ordering for a module:

```bash
# your own order for module 1685 at version 0
bash run_once.sh javaparser/javaparser javaparser-core-testing <sha> \
     runs/1685/0/order_mine/run_1 my_order.txt
```

Look up `<slug> <module> <sha>` for any module and version in
`data/versions.csv`. Results land in `<out_dir>`: `status`, `wall_time.txt`,
`mvn.log`, `surefire-reports/`.

To see what would happen without starting a container, set
`OTOG_ENGINE_DRYRUN=1` — it prints the exact container command and runs nothing.

## Check the order was really imposed

The whole experiment rests on surefire running the tests in the order it was
handed, which is not self-evident. After a run:

```bash
python3 scripts/check_order_imposed.py orders/1685/0/1.txt runs/1685/0/order_1/run_1
```

Worth doing once on a new machine, and any time the JDK or the surefire fork
changes. A run can otherwise pass having measured nothing.

## The container

Every run gets **4 CPUs and 16 GB**, on every machine and both engines, from a
cold JVM. Timings are comparable across machines only because this is pinned,
so a run that cannot have it is refused rather than quietly run smaller. The
three repetitions are three containers, never a loop inside one.

## Tutorials

| | |
|---|---|
| [docs/HOPPER.md](docs/HOPPER.md) | a SLURM cluster |
| [docs/CLOUDLAB.md](docs/CLOUDLAB.md) | CloudLab bare metal |
| [docs/AWS.md](docs/AWS.md) | AWS, with cost per run |
| [cloudlab_aws_config_steps.md](cloudlab_aws_config_steps.md) | CloudLab and AWS on one page |

## Layout

```
setup.sh            engine check, images, directories
run_experiment.sh   the experiment; edit the variables at the top
run_once.sh         one order, once, in one container
config_default.sh   settings; copy to config.sh to override
lib.sh              what the scripts share
container/          the engine layer and what runs inside the container
data/versions.csv   module_id,slug,module,version,sha
orders/<module>/<version>/<n>.txt              the test orders
runs/<module>/<version>/order_<n>/run_<r>/     one measurement each
tests/              run: pip install pytest && python3 -m pytest tests/ -q
```

Every script's first comment is a working example, then what it takes input and
what is it's output.
