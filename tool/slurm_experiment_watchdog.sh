#!/bin/bash
#
# nohup bash slurm_experiment_watchdog.sh >> slurm_logs/watchdog.log 2>&1 &
#
# Keeps slurm_run_experiment.sh feeding. The feeder is the only thing between
# an empty queue and an unfinished campaign, and it is a login-node process: a
# session ending, an OOM or a reboot takes it away. This starts it again.
#
# in : the same MODULES/PHASES/JFR the feeder reads, plus MAX_JOBS
# out: slurm_logs/feeder.log, slurm_logs/watchdog.heartbeat
#
# To stop it:  touch STOP     -- the watchdog exits within $interval, and the
# feeder stops submitting at its next order. Deliberately a file and not a
# signal: a watchdog is exactly the thing you need to stop when you have lost
# track of which process is which, and `kill` needs a pid you can trust.

tool_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
logs="$tool_dir/slurm_logs"
interval=${WATCHDOG_INTERVAL:-600}

mkdir -p "$logs"

while true; do
    if [ -e "$tool_dir/STOP" ]; then
        echo "[$(date '+%F %T')] STOP present -- watchdog exiting"
        exit 0
    fi

    # flock, not pgrep: a command line that mentions the feeder is not a
    # feeder, and that false positive once let the queue drain unnoticed for
    # hours. A second feeder fails to take the lock and exits immediately.
    # Backgrounded so this loop keeps ticking while a feeder runs for hours.
    ( flock -n 9 || exit 0
      bash "$tool_dir/slurm_run_experiment.sh" >> "$logs/feeder.log" 2>&1
    ) 9> "$logs/feeder.lock" &

    # A file whose mtime only this loop can advance. Process presence is not a
    # health signal here -- the subshell above also matches "bash watchdog.sh",
    # and such an orphan once kept every pgrep check green for 18 hours.
    date +%s > "$logs/watchdog.heartbeat"
    echo "[$(date '+%F %T')] queue=$(squeue -u "$USER" -h -o '%j' 2>/dev/null | grep -c '^otog_')"
    sleep "$interval"
done
