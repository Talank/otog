#!/bin/bash
#
# usage: nohup bash slurm_experiment_watchdog.sh [modules] [phases] [orders] [jfr] [max_jobs] >> slurm_logs/watchdog.log 2>&1 &
# e.g.   nohup bash slurm_experiment_watchdog.sh 1685 v0 "1 10" false 250 >> slurm_logs/watchdog.log 2>&1 &
#
# Keeps slurm_run_experiment.sh feeding. The feeder is a login-node process, so
# a session ending, an OOM or a reboot takes it away; this starts it again.
#
# in : the same arguments the feeder takes, passed straight through.
# out: slurm_logs/feeder.log, slurm_logs/watchdog.heartbeat
#
# To stop it: touch STOP -- a file and not a signal, because a watchdog is
# exactly the thing you need to stop when you no longer trust any pid.

tool_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
logs="$tool_dir/slurm_logs"
interval=${WATCHDOG_INTERVAL:-600}

mkdir -p "$logs"

while true; do
    if [ -e "$tool_dir/STOP" ]; then
        echo "[$(date '+%F %T')] STOP present -- watchdog exiting"
        exit 0
    fi

    # flock, not pgrep: a command line that mentions the feeder is not a feeder,
    # and that false positive once let the queue drain unnoticed for hours.
    ( flock -n 9 || exit 0
      bash "$tool_dir/slurm_run_experiment.sh" "$@" >> "$logs/feeder.log" 2>&1
    ) 9> "$logs/feeder.lock" &

    # A file only this loop can touch. Process presence is not a health signal.
    date +%s > "$logs/watchdog.heartbeat"
    echo "[$(date '+%F %T')] queue=$(squeue -u "$USER" -h -o '%j' 2>/dev/null | grep -c '^otog_')"
    sleep "$interval"
done
