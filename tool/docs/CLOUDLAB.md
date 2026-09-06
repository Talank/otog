# Running this on CloudLab

CloudLab gives you **bare-metal machines**, not a batch queue. There is no
SLURM: you reserve physical nodes for a time window, SSH in, and run whatever
you like. That suits us — `run_experiment.sh` is its own scheduler.

**The one thing that will bite you:** an experiment terminates automatically
after a few hours, and *you lose everything on local disk when it does*. Copy
results off continuously, not at the end.

## 1. Pick the hardware

Our container is 4 CPUs + 16 GB, so containers-per-node is
`min(cores/4, RAM_GB/16)`:

| cluster | node | cores | RAM | containers/node |
|---|---|---|---|---|
| Clemson | `c6420` | 32 | 384 GB | **8** |
| Clemson | `r6525` | 64 | 256 GB | **16** |
| Clemson | `c6320` | 28 | 256 GB | **7** |
| Clemson | `c8220` | 20 | 256 GB | **5** |
| Wisconsin | `c220g5` | 20 | 192 GB | **5** |
| Wisconsin | `sm220u` | 32 | 256 GB | **8** |
| Utah | `c6525-25g` | 16 | 128 GB | **4** |

Clemson `r6525` is the best fit — 16 containers per node, and 32 of them exist.
Eight of those nodes gives 128 parallel containers; sixteen gives 256, matching
the 250 the SLURM campaign uses.

Prefer many mid-size nodes over few huge ones: a node lost to a hardware
failure then costs proportionally less.

## 2. Reserve the nodes

Reservations are per-cluster and per-type, requested through **Reserve Nodes**
in the portal and reviewed by an administrator. Smaller and shorter requests
are approved more readily, so ask for what you will actually use.

A reservation guarantees capacity; it does not start anything. You still create
an experiment inside the window.

## 3. The profile

Create a profile (Experiments → Create Profile → geni-lib) with this. Change
`NODES` and `HARDWARE` and nothing else.

```python
"""OTOG: N bare-metal nodes for test-order experiments."""
import geni.portal as portal
import geni.rspec.pg as rspec

NODES    = 8
HARDWARE = "r6525"
IMAGE    = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"

request = portal.context.makeRequestRSpec()
for i in range(NODES):
    node = request.RawPC("n%d" % i)
    node.hardware_type = HARDWARE
    node.disk_image    = IMAGE
    # Local disk: the image root is small, and maven plus checkouts are not.
    bs = node.Blockstore("bs%d" % i, "/mnt/otog")
    bs.size = "300GB"
portal.context.printRequestRSpec()
```

Then Start Experiment with that profile, pick the cluster you reserved, and
wait for the nodes to boot.

## 4. Set up each node

```bash
ssh <user>@<node>.<cluster>.cloudlab.us

sudo apt-get update && sudo apt-get install -y docker.io unzip openjdk-17-jdk
sudo usermod -aG docker $USER && newgrp docker
sudo chown -R $USER /mnt/otog

cd /mnt/otog
unzip ~/otog_v2_2.zip && cd otog_v2_2
bash setup.sh docker
```

`setup.sh` prints how many containers the node fits — check it matches the
table above before starting a long run.

## 5. Split the work across nodes

Give each node a slice by editing the variables at the top of
`run_experiment.sh`. The simplest split that never overlaps is by module:

```bash
# on n0
MODULES="1117 3613"
# on n1
MODULES="1216 3320"
```

Then on each node:

```bash
tmux new -s otog          # survives your SSH session dropping
bash run_experiment.sh
```

Splitting by module also keeps every order of a module on one machine, which
matters: **the node effect is larger than the ordering effect**, so orders
being compared must come from the same hardware.

## 6. Copy results off before the experiment expires

This is the step people forget. Local disk is erased on termination.

```bash
# from your own machine, every hour
while true; do
    rsync -az --partial <user>@n0.<cluster>.cloudlab.us:/mnt/otog/otog_v2_2/runs/ ./runs/
    sleep 3600
done
```

Or push from the node to somewhere durable. Either way, do it on a timer from
the first hour — not once at the end.

Use **Extend** in the portal well before expiry. An extension can be refused if
it would collide with someone else's reservation, so extend early and assume
the answer might be no.

## 7. Sanity check before the long run

```bash
# one order, one repetition, on one module
bash run_once.sh javaparser/javaparser javaparser-core-testing \
     2c8ce56933b17e6fa6fd9638aeaff604b24dd6c7 /tmp/t1 orders/1685/0/1.txt

cat /tmp/t1/status        # expect PASS
cat /tmp/t1/wall_time.txt
```

Then check the order was actually imposed — a run can pass having measured
nothing, and this is the moment to find that out:

```bash
python3 scripts/check_order_imposed.py orders/1685/0/1.txt /tmp/t1
```

If both pass, the node is configured correctly and the full run will work.
