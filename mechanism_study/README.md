# Test-order runtime mechanism study

Start with an exact paper order and record the project revision, module, Java
version, Maven version, fork settings, and host conditions. Use
`make_orders.py` to make two orders that contain the same tests and differ only
in the placement under study. Use `run_ab.py` to run the orders in alternating
slots, with no other performance experiment active on the host. Keep only
green runs. First measure the original code without profiling. Then read the
test and production code, use boundary data, JFR, stack samples, or thread
snapshots to trace the exact path that can explain the difference. Change one
relevant item, state why it was changed, and repeat the same orders as a check.
Accept a mechanism only when the complete-suite difference is repeatable and
the check removes or substantially reduces it. Restore all temporary changes
to the project under test.

Keep generated recordings and run output under `mechanism_study/artifacts/`.
Git ignores that directory because the data is large and often specific to one
host. Commit the final report, the exact accepted order files, the scripts and
settings needed to repeat the work, and a small evidence summary with the
accepted measurements and excluded runs. Before a run, install the patched
Surefire extension as version `1.0-SNAPSHOT`; build the `csto2` agent when the
run needs boundary data or JFR test intervals. Run each script with `--help`
for its command-line options. The consolidated results are in
`../csto2/findings/mechanisms.md`, and the accepted inputs are listed in
`orders/ACCEPTED.md`.
