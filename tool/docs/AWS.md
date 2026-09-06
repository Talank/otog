# Running this on AWS

Same idea as CloudLab, different machines. Our container is 4 vCPU + 16 GB, so
pick instances where vCPU/4 and RAM/16 give the same number.

| instance | vCPU | RAM | containers | notes |
|---|---|---|---|---|
| `m6i.4xlarge` | 16 | 64 GB | **4** | the balanced default |
| `m6i.8xlarge` | 32 | 128 GB | **8** | |
| `m6i.16xlarge` | 64 | 256 GB | **16** | fewest instances to manage |
| `c6i.8xlarge` | 32 | 64 GB | 4 | compute-optimised, **memory-starved for us** |
| `r6i.4xlarge` | 16 | 128 GB | 4 | memory-optimised, CPU-starved for us |

**Use `m` (balanced), not `c` or `r`.** Our unit needs 4 GB of RAM per core;
`c` gives 2 and `r` gives 8, so either way you pay for capacity you cannot use.

Graviton (`m7g`) is cheaper per core, but the JDK images are amd64 and the
timings would not be comparable with the existing dataset. Stay on x86.

## Setup

```bash
# Amazon Linux 2023 or Ubuntu 22.04, 300 GB gp3 root volume
sudo dnf install -y docker unzip && sudo systemctl start docker   # AL2023
sudo usermod -aG docker $USER && newgrp docker

unzip otog_v2_2.zip && cd otog_v2_2
bash setup.sh docker
bash run_experiment.sh
```

Before the long run, do the one-order sanity check from
[CLOUDLAB.md](CLOUDLAB.md) §7 — it costs a few minutes and catches a
misconfigured instance before you have paid for a day of it.

## Cost per run, by project

$0.192 per container-hour (any `m6i` size divides to the same rate), on-demand.

| module | project | s/run | $/run | $ for its ×10 (3,000 runs) |
|---|---|---|---|---|
| 1685 | javaparser :: core-testing | 535 | 0.029 | 86 |
| 1683 | javaparser :: symbol-solver-testing | 554 | 0.030 | 89 |
| 1778 | spring-ai :: openai | 602 | 0.032 | 96 |
| 1305 | async-http-client :: client | 658 | 0.035 | 105 |
| 2088 | liquibase :: standard | 703 | 0.037 | 112 |
| 29 | netty :: transport | 748 | 0.040 | 120 |
| 33 | netty :: handler | 904 | 0.048 | 145 |
| 1122 | flowable :: cmmn-engine | 910 | 0.049 | 146 |
| 20 | netty :: transport-native-epoll | 1075 | 0.057 | 172 |
| 1497 | drools :: test-coverage | 1090 | 0.058 | 174 |
| 3323 | curator :: curator-framework | 1127 | 0.060 | 180 |
| 1694 | iotdb :: confignode | 1473 | 0.079 | 236 |
| 3320 | curator :: curator-recipes | 2011 | 0.107 | 322 |
| 1216 | mapstruct :: processor | 2024 | 0.108 | 324 |
| 3613 | paimon :: paimon-core | 2072 | 0.111 | 332 |
| 1117 | flowable :: flowable-engine | 2281 | 0.122 | 365 |

| | on-demand | spot |
|---|---|---|
| all 16 modules, the whole ×10 phase (48,000 runs) | $3,000 | **$900** |

Double for ×5. Prices are us-east-1, checked September 2026.

## Cost control

- **Spot instances** are 60-70% cheaper and fine here: the work is resumable,
  so an interrupted run just gets redone. Set `PARALLEL` to the instance size
  and let it restart.
- Results are small (a run is ~9 MB, and compresses ~40x). Push them to S3 as
  they finish rather than keeping a large EBS volume alive:

  ```bash
  aws s3 sync runs/ s3://<bucket>/otog/runs/ --only-show-errors
  ```

- **Stop the instance when the run finishes.** The experiment is
  embarrassingly parallel, so many small instances for a short time costs the
  same as few large ones for long — but only if you actually stop them.

## Splitting across instances

As on CloudLab, split by module so that every order of a module is measured on
identical hardware:

```bash
MODULES="1117 3613"     # instance 1
MODULES="1216 3320"     # instance 2
```

Keep every instance the same type. **The node effect is larger than the
ordering effect being measured**, so orders compared against each other must
come from the same instance type — ideally the same instance.
