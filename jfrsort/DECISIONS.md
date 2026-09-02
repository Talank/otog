# Decision log

This log records each arbitrary decision in jfrsort. The style is ASD-STE100
Simplified Technical English. Each entry gives the decision and the reason.

## D1 — Tool language

We write the tool in Python 3 with only the standard library. Thus the tool has no
build step and no dependencies.

## D2 — Profiled run command

We start each profiled run with the command `mvn -B test` in the project directory.
This command is the same command that developers use, thus the measured runs agree
with the usual builds.

## D3 — How we start JFR

We set the environment variable `JAVA_TOOL_OPTIONS` to
`-XX:StartFlightRecording:settings=profile,dumponexit=true,filename=<run dir>/`.
Each JVM in the build reads this variable, thus each Surefire fork makes a recording,
and the `argLine` of the project pom stays unchanged.

## D4 — Stack depth in the recording (replaced by D21)

We set `-XX:FlightRecorderOptions:stackdepth=1024`. The default depth of 64 cuts the
deep JUnit and coverage-agent stacks, and a cut stack loses the test-class frame.
With depth 128 on commons-csv, cut stacks held 1.1 GB of the sample weight.
Window attribution (D21) does not read stacks, thus we do not set this option now.

## D5 — Allocation metric

We measure allocation with the `weight` field of `jdk.ObjectAllocationSample` events.
The weight is an estimate of the allocated bytes, and the sampled event has a much
lower overhead than the full TLAB allocation events.

## D6 — Recording parser

We parse each recording with the command `jfr print --json --stack-depth 1024
--events jdk.ObjectAllocationSample <file>`. The `jfr` tool is part of the JDK, thus
we do not add a JFR library.

## D6a — Stack depth in the parser (replaced by D21)

We give `--stack-depth 1024` to `jfr print`. Without this option, `jfr print` shows
only five frames for each event. Five frames almost never include the test-class
frame, and on commons-csv only 15 percent of the weight got an owner. With the
option, 90 percent of the weight got an owner. Window attribution (D21) does not
read stacks, thus we do not give this option now.

## D7 — Event attribution (replaced by D21)

We examine the stack frames of each event from the innermost frame to the outermost
frame. The first frame with a known test class gets the full weight of the event.
Thus allocations in library code go to the test that caused them.

Stack traces are the only attribution method that does not change the test run.
Surefire runs all test classes on one thread, thus the thread identity cannot give
the owner. Time windows for each class need a listener in the fork, and we do not
add one (see D2 and D3). The trade-off: an allocation on a thread that a test starts
does not have the test frame on its stack, thus this weight, and the weight of
framework and coverage-agent work, stays unattributed. On commons-csv this loss is
approximately 10 percent of the total weight, and the tool prints the attributed
percentage for each run.

## D8 — Nested classes

We change each nested class name (`com.Foo$Bar`) to its top-level class name
(`com.Foo`). Surefire orders top-level classes, and csto2 uses the same rule.

## D9 — Test list source

We read the test-class list from the Surefire XML reports (`TEST-*.xml`). These
reports show the classes that ran, thus the list agrees with `mvn test`.

## D10 — Initial order (replaced by D23)

We use the ascending modification times of the run-1 report files as the initial
order. Surefire writes each report when its class completes, thus this order is
approximately the execution order.

## D11 — Non-test recordings (replaced by D24)

We remove each recording that has zero attributed weight. The Maven launcher JVM
also reads `JAVA_TOOL_OPTIONS` and makes a recording, and this rule removes it.

## D12 — Stale reports

We delete all `target/surefire-reports` directories before each run. Thus reports
from an earlier run cannot go into the test list.

## D13 — Red suites

We stop with an error if `mvn test` fails. Metrics from a red run are not safe,
and csto2 uses the same rule.

## D14 — Aggregation

We compute the arithmetic mean of the attributed bytes for each class across the N
runs. A class with no samples in a run gives the value 0 for that run. The mean of
independent runs decreases the sampling variance.

## D15 — Sort rule

We do a stable sort of the initial order by the mean metric, descending. Classes
with equal values keep their initial relative order. This rule is the same as the
`alloc-sort` rule in csto2.

## D16 — XML parser

We parse the Surefire reports with the standard `xml.etree.ElementTree` module.
The reports are local files from the user's own build, thus a hardened external
parser is not necessary (see D1).

## D17 — Custom test-boundary events (changes D3 and D7)

We inject a test listener into the Surefire fork. The listener emits a custom JFR
event at the start and at the end of each test class. We then give each JFR event
in a test's time period to that test, on all threads. We select this method because
it captures all data in the test's time period, including data from threads that
the test starts and data from events without stack traces. Thus it is more reliable
than stack-trace attribution (D7).

## D18 — Parallel test execution

We do not support builds that run multiple tests at the same time. The time periods
of parallel tests overlap, and an overlapped period cannot give an event one owner.

## D19 — Listener injection

We add `-javaagent:jfrsort-agent.jar` to `JAVA_TOOL_OPTIONS`, and the agent's
premain appends its jar to the system classloader. Thus the JUnit Platform
ServiceLoader finds the listener in the Surefire fork, and the pom stays unchanged.
The target must run its tests through the JUnit Platform (JUnit 5, or JUnit 4
through the vintage engine).

## D20 — Window event design

The listener makes one `jfrsort.TestClass` event for each top-level test class:
`begin()` at container start and `commit()` at container finish, thus the event's
start time and duration give the class window. Only containers with a `ClassSource`
and no `$` in the class name open a window, thus nested classes and test methods
stay inside their top-level window.

## D21 — Window attribution (replaces D4, D6a, D7)

We give each metric event to the test class whose time window contains the event,
on all threads. Events outside all windows (JVM start, test discovery, gaps between
classes) stay unattributed. This rule implements D17.

## D22 — Sampler throttle

We set `jdk.ObjectAllocationSample#throttle=1000/s` in the recording options, above
the 150/s of the profile settings. More samples each second make the per-class
estimate more exact and decrease the run-to-run variance.

## D23 — Initial order and test list (replaces D10)

We take the test list and the initial order from the run-1 window events, in
start-time order. These events come from the same clock as the metric events. We
keep the Surefire reports as a cross-check and give a warning on a difference.

## D24 — Non-test recordings (replaces D11)

We remove each recording that has no `jfrsort.TestClass` events. A JVM without
test windows ran no tests; this removes the Maven launcher JVM.

## D25 — Overlap check

We stop with an error if two windows overlap in one recording. This check enforces
D18.

## D26 — Tool languages

The orchestrator stays in Python (see D1). Only the in-fork listener is Java,
because it must run in the test JVM. The tool builds the agent jar with Maven on
first use.
