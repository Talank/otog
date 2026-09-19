# OTOG

Runs one test order, at one commit, in a fixed container, and records what it
cost. Works anywhere with Docker or Apptainer.

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

## Profile the runs and sort them with jfrsort

With `jfr` set to `true`, the container starts each test JVM with the agent
in `aux/jfrsort-agent.jar` and a Java Flight Recorder recording. The agent
writes one event for each test class that spans the class's execution. The
recording uses the JVM's own `profile` preset with these changes: the two
TLAB allocation events are on, without stack traces, and the compilation,
class load, file, socket, monitor, and sleep events have no threshold. These
are the events behind the metrics of jfrsort and of the PROBO paper. The same
settings go to every JDK, in a settings file that the container writes into
the run directory. The recording of each profiled repetition is at
`runs/<module>/<version>/order_<n>/jfr_run_<r>/jfr/<module>.jfr`.

The recordings are small and the run directories are not. This script copies
the recordings of one module version, with their orders, into a directory
that holds nothing else:

```bash
python3 scripts/export_jfr.py runs/1685/0 exports/1685/0
```

It takes each `jfr_run_<r>` that passed and has a recording, and writes
`collect.json` in the form that jfrsort reads. All paths in it are relative
to the export directory, so the directory can be moved to another machine
and sorted there:

```bash
python3 ../jfrsort/jfrsort.py sort --out exports/1685/0
```

Sorting needs a `jfr` command from JDK 17 or later on the analysis machine.
It reads recordings from every JDK the containers use.

## The agent

The source is in `agent/`. It is a JUnit Platform listener that writes one
`jfrsort.TestClass` event for each top-level test class, and a premain that
puts the jar on the class path of the test JVM. It is built with a JDK 8 of
update 262 or later, which has the Flight Recorder API, so that the jar loads
on every JDK the containers use. The built jar is committed as
`aux/jfrsort-agent.jar`; `setup.sh` compiles nothing. To rebuild it, run
Maven on `agent/pom.xml` with a JDK 8 and copy the jar to `aux/`.

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
agent/                the test-window agent for the recordings; built jar in aux/
scripts/              order generation, adaptation, the order-imposed check, the recording export
data/versions.csv     module_id,slug,module,version,sha
requirements.txt      pytest and gdown
tests/                the suite; see Tests above
orders/<module>/<version>/<n>.txt              the test orders
runs/<module>/<version>/order_<n>/run_<r>/     one measurement each
runs/<module>/<version>/order_<n>/jfr_run_<r>/ one profiled measurement each
```

Every script's header is one usage line, one example, and what it takes and
produces. Every function has a one-line comment.
