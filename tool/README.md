# OTOG — does test order change how long a suite takes?

Runs one test order, at one commit, in a fixed container, and records what it
cost. Works on a laptop, a server, an AWS instance, a CloudLab node or a SLURM
cluster — anywhere with Docker or Apptainer.

## Start

```bash
bash setup.sh docker          # once. or: bash setup.sh apptainer
bash run_experiment.sh        # the whole experiment
```

`setup.sh` prints how many containers your machine fits; `run_experiment.sh`
sizes itself to that. It is **resumable** — a repetition that already passed is
skipped — so you can stop it and re-run it any time.

## Run a subset

Every script takes plain arguments. `run_experiment.sh` takes four, and each
one falls back to the default in `config_default.sh`:

```bash
bash run_experiment.sh <modules> <phases> <orders> <jfr>

bash run_experiment.sh 1685 v0 "1 10"          # one module, v0, first 10 orders
bash run_experiment.sh "1685 1683" historical  # two modules, the past 100 versions
bash run_experiment.sh 1685 v0 "1 5" true      # ...and profile them with JFR
```

- **modules** — module ids, as in `data/versions.csv`
- **phases** — `v0`, `historical`, `x10`, `x5`, or a literal version number
- **orders** — first and last order number
- **jfr** — `true` adds a profiled run beside every plain one, on `v0` and
  `historical` only

`work_list.txt` is written before anything runs, so you can always see exactly
what it is about to do. `bash run_experiment.sh --list ...` prints it and stops.

Repetitions and parallelism come from `config_default.sh` (`otog_repeats`,
`otog_parallel`). Copy it to `config.sh` to change them; `config.sh` wins and is
never overwritten.

## Run one order yourself

```bash
bash run_once.sh <slug> <module> <sha> <out_dir> [order_file] [jfr]

bash run_once.sh javaparser/javaparser javaparser-core-testing \
     2c8ce56933b17e6fa6fd9638aeaff604b24dd6c7 \
     /tmp/myrun orders/1685/0/1.txt
```

Look up `<slug> <module> <sha>` for any module and version in
`data/versions.csv`. Results land in `<out_dir>`: `status`, `wall_time.txt`,
`mvn.log`, `surefire-reports/`.

**Any file works as an order** — a solver's output, a hand-written order,
anything. Give one to `run_experiment.sh` in place of an order number and it is
run three times, in its own directories, with the same fixes as every other
order of that module-version:

```bash
bash run_experiment.sh --one 1685 0 /tmp/arbitrary_order.txt v0
# -> runs/1685/0/order_arbitrary_order/run_1, run_2, run_3
```

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
cold JVM. Timings are comparable across machines only because this is pinned, so
a run that cannot have it is refused rather than quietly run smaller. The three
repetitions are three containers, never a loop inside one.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m pytest tests/ -q                    # whole suite, ~17s
.venv/bin/python -m pytest tests/test_setup.py -q       # one file
.venv/bin/python -m pytest tests/ -q -k imposed         # tests whose name matches
```

`pytest` and `gdown` are the only dependencies; a system `pip install pytest
gdown` works just as well, and the commands are then the plain `python3 -m
pytest ...`. Activate the venv before `bash setup.sh` so its download step can
find `gdown`.

The suite exercises the real scripts, symlinked into a throwaway directory, with
`OTOG_ENGINE_DRYRUN=1` — nothing starts a container, touches `runs/`, or needs
docker, a JDK or the network. The exception is `tests/test_run_data.py`, which
reads the real `runs/` tree and asserts the properties the analysis depends on.
A failure there is a statement about the data, not about the code.

```bash
OTOG_RUNS=/scratch/$USER/otog/runs .venv/bin/python -m pytest tests/test_run_data.py -q
OTOG_SAMPLE=0 OTOG_EVERY_ORDER=1 .venv/bin/python -m pytest tests/test_run_data.py -q
```

## Layout

```
setup.sh              engine check, images, orders, seeded maven repo
run_experiment.sh     the experiment: what runs, in what priority
run_once.sh           one order, once, in one container
config_default.sh     settings; copy to config.sh to override
lib.sh                what the host-side scripts share
fix_helper.sh         per-project build fixes, keyed on the version
container/            the engine layer and what runs inside the container
scripts/              order generation, adaptation, and the order-imposed check
data/versions.csv     module_id,slug,module,version,sha
requirements.txt      pytest and gdown
tests/                the suite; see Tests above
orders/<module>/<version>/<n>.txt              the test orders
runs/<module>/<version>/order_<n>/run_<r>/     one measurement each
```

Every script's header is one usage line, one example, and what it takes and
produces. Every function has a one-line comment.

## More

| | |
|---|---|
| [docs/design.md](docs/design.md) | why the code is the way it is — read before changing it |
| [docs/jfr_runner_flow.md](docs/jfr_runner_flow.md) | what a profiled run records, and where |
| [docs/HOPPER.md](docs/HOPPER.md) | a SLURM cluster |
| [docs/CLOUDLAB.md](docs/CLOUDLAB.md) | CloudLab bare metal |
| [docs/AWS.md](docs/AWS.md) | AWS, with cost per run |
