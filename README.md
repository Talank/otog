# mechdetect

This tool changes the order of the test classes in a Java test suite. The new order makes the
suite faster. The tool finds the new order from one profiled run of the suite.

## How the tool works

The tool does these steps for one Maven module:

1. **Capture.** Run `capture_natural.sh`. This runs `mvn test` one time. It records the order
   in which the test classes run. This order is the natural order.
2. **Profile.** Run `profile.py`. This runs the suite one time in the natural order, with a
   Java agent and a JFR recording attached. The agent records, for each test class: changes to
   static fields, writes to system properties, class retransformation, thread starts, stack
   samples, and compiler activity.
3. **Analyze.** `Analyzer.java` reads the profile. It applies one global set of rules. It
   writes a list of candidate moves. Each candidate names one test class and one direction
   (front, back, swap, or block-to-tail).
4. **Confirm.** Run `confirm_moves.py`. This tests each state-related move with small paired
   runs. A move that fails the test two times, on two different downstream test classes, is
   removed. The total run time of steps 2 and 4 must not be more than 5 times the suite run
   time. The tool records the spend in a ledger.
5. **Emit.** Run `emit_order.py`. This writes the new test order to a file.

`triage.sh` does all five steps for one module with one command:

    ./triage.sh <name> <module-dir> [java-home] [--vintage]

## How to measure the result

The emitted order is a hypothesis. Measure it against the natural order with interleaved
A/B pairs before you use it. A valid win needs 10 or more pairs, no test failures in any run,
and a paired median saving. The measurement step is not part of this repository. This
repository holds the captured natural orders and the emitted orders for the six confirmed
wins: javaparser-core-testing (12.3%), snakeyaml (13.33%), paimon-core (27.1%), commons-io
(10.31%), handlebars (19.08%), and avro (12.73%).

## Requirements

- The forked Maven Surefire plugin (3.0.0-M8-SNAPSHOT) with the `testorder` run order, and
  its companion Maven extension, installed in `~/.m2`.
- A pinned fork JVM. Do not let the fork inherit the system Maven JVM.
- Build the agent with `mvn -q package`.
