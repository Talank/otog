# CloudLab and AWS — the short version

Both are "get a machine, unzip, run". Full tutorials:
[docs/CLOUDLAB.md](docs/CLOUDLAB.md), [docs/AWS.md](docs/AWS.md).

## CloudLab (free, bare metal)

1. Log in at cloudlab.us → **Experiments → Start Experiment**.
2. Profile `small-lan`, **1 node**, hardware type `c6420` (32 cores, 384 GB →
   8 containers) or `c220g5` (40 cores, 192 GB → 12 containers).
3. Set the duration to the maximum, **16 hours**. Longer needs an extension
   request, so ask for it on day one.
4. `ssh` in with your CloudLab key, then:

```bash
sudo apt-get update && sudo apt-get install -y docker.io unzip
sudo usermod -aG docker $USER && newgrp docker
unzip otog_v2_2.zip && cd otog_v2_2
bash setup.sh docker
bash run_experiment.sh
```

**The local disk is erased when the experiment expires.** Copy `runs/` out
before then, every time:

```bash
tar cf - runs | zstd -3 | ssh you@elsewhere 'cat > runs.tar.zst'
```

## AWS (paid, on demand)

Pick `m` instances — the container needs 4 GB of RAM per core, which is what
`m` gives. `m6i.4xlarge` runs 4 containers, `m6i.16xlarge` runs 16.

```bash
sudo dnf install -y docker unzip && sudo systemctl start docker
sudo usermod -aG docker $USER && newgrp docker
unzip otog_v2_2.zip && cd otog_v2_2
bash setup.sh docker
bash run_experiment.sh
```

Sync results to S3 as they land, then stop the instance:

```bash
aws s3 sync runs/ s3://<bucket>/otog/runs/ --only-show-errors
```

### Cost per run

$0.192 per container-hour on-demand; spot is 60-70% less and safe here because
the work is resumable.

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

The whole ×10 phase for all 16 modules is $3,000 on-demand, $900 spot; ×5
doubles it. us-east-1, September 2026.

## On both

Split work **by module**, never by order, and keep every machine the same type
— the node effect is larger than the ordering effect being measured.

```bash
MODULES="1117 3613"     # machine 1
MODULES="1216 3320"     # machine 2
```
