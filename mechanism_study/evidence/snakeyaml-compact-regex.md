# SnakeYAML Corretto 8 compact-regex order effect

Date: 2026-07-30

## Scope

- SnakeYAML checkout: `/Users/gabriel/Development/Research/snakeyaml`
- Commit: `e6eb1b7274ea42aceb4194b56392ab42954e1120`
- Test JVM: Amazon Corretto `1.8.0_502`
- Maven: `/opt/homebrew/bin/mvn` 3.9.16
- One reused Surefire fork per run
- Both orders contain the same 349 exact paper test classes.
- The only order change moves
  `org.yaml.snakeyaml.extensions.compactnotation.CompactConstructorErrorsTest`
  from position 348 to position 0.
- Every accepted arm ran 349 classes with zero failures.

This result is limited to Corretto 8. In the Java 11 front/back JFR run, the
same class took 45 ms at position 0 and 7 ms at position 348. Java 17 runs
inspected elsewhere in this study were in the same low-millisecond range.
The evidence below does not establish the same order effect on those JVMs.

## Baseline result

The original source uses the static `GUESS_COMPACT` regular expression.
Ten interleaved pairs were green. Seven pairs came from
`compact-regex-front-back`; three clean additional pairs came from
`compact-regex-corretto8-baseline-add3`.

Complete-suite times in milliseconds:

```text
front: 4951, 4788, 5223, 5379, 5008, 4970, 6236, 4575, 4344, 5011
back:  5523, 5415, 5524, 5652, 5571, 5572, 6692, 5165, 5351, 5338
```

The corresponding paired differences, `back - front`, are:

```text
+572, +627, +301, +273, +563, +602, +456, +590, +1007, +327
```

The front order won all 10 pairs. The two-sided sign-test probability for
10 wins in 10 pairs is approximately 0.002.

| Measure | Front | Back |
|---|---:|---:|
| Suite median | 4,989.0 ms | 5,523.5 ms |
| Suite mean | 5,048.5 ms | 5,580.3 ms |

The paired `back - front` median is +567.5 ms and its mean is +531.8 ms.

The front median is 9.68% lower than the back median.

The moved class itself took:

```text
front: 1237, 1449, 1445, 1432, 1466, 1487, 1319, 1291, 1304, 1300
back:  1625, 1615, 1613, 1643, 1663, 1640, 1772, 1595, 1627, 1600
```

Its medians were 1,375.5 ms at the front and 1,626.0 ms at the back.
The total-suite result, rather than only this class time, is the reported
order effect.

## Source and execution flow

`CompactConstructor` defines `GUESS_COMPACT` at
`src/main/java/org/yaml/snakeyaml/extensions/compactnotation/CompactConstructor.java:39-40`.
The expression contains nested variable-length components:

```text
\p{Alpha}.*\s*\((?:,?\s*(?:(?:\w*)|(?:\p{Alpha}\w*\s*=.+))\s*)+\)
```

`CompactConstructor.getConstructor` executes this expression for scalar
mapping keys and scalar nodes at lines 159-180. If it matches, the method
selects `ConstructCompactObject`.

The nine methods in `CompactConstructorErrorsTest` load the compact-notation
error fixtures through `Yaml.load`. The helper flow is at
`src/test/java/org/yaml/snakeyaml/extensions/compactnotation/CompactConstructorErrorsTest.java:27-73`.

The application flow is:

```text
CompactConstructorErrorsTest
  -> load or check
  -> Yaml.load
  -> compose a ScalarNode or one-entry MappingNode
  -> BaseConstructor.constructObject
  -> CompactConstructor.getConstructor
  -> GUESS_COMPACT.matcher(scalar).matches
  -> java.util.regex.Pattern matching nodes
  -> ConstructCompactObject.construct
  -> CompactConstructor.getCompactData
  -> FIRST_PATTERN and PROPERTY_NAME_PATTERN
  -> create or populate the compact object, or raise the expected error
```

The existing Corretto 8 boundary-counter runs are in
`compact-regex-jdk8-instrumented`. In those runs:

- front intervals loaded 371 classes and assigned 336 to 1,028 ms of compiler
  work to the moved class;
- back intervals loaded one class and assigned 286 to 478 ms of compiler work;
- the moved class still took about 1.51 to 1.52 seconds at the front and
  1.62 to 1.65 seconds at the back.

These counters show that the JVM state differs sharply by position. They do
not, by themselves, identify which compilation tier or prior test is
responsible. The supported claim is narrower: execution of the static
`GUESS_COMPACT` gate is necessary for the repeatable Corretto 8 total-time
gap.

There is also direct Java 8 stack evidence for the regex path. The two
interpreted-mode thread snapshots in `warm-cold-xint/compact-thread-1.txt`
and `compact-thread-2.txt` identify HotSpot 25.502-b07 (Corretto 8). Their
main-thread stacks contain long repetitions of
`java.util.regex.Pattern$Curly.match0`, `Pattern$Curly.match`, and
`Pattern$Loop.match`, followed by:

```text
Matcher.match
Matcher.matches
CompactConstructor.getConstructor
BaseConstructor.constructObject...
Yaml.load
CompactConstructorErrorsTest.load
CompactConstructorErrorsTest.test4
```

These snapshots establish that the expensive Java 8 work is occurring inside
the `GUESS_COMPACT` matcher reached by the moved test. They are path evidence,
not timing samples from the accepted ten-pair baseline.

For JVM-version scope, `compact-regex-flow-jfr/00-00-front.jfr` records
OpenJDK 11.0.31 explicitly in its `jdk.JVMInformation` event. Its derived
`front-flow.txt` reports the moved class at 45 ms and an L3 compilation of
`java.util.regex.Pattern$Loop.match`; `back-flow.txt` reports the class at
7 ms and an L2 compilation of the same method. This confirms that the
`Pattern$Loop` flow still exists on Java 11 while the Corretto 8-scale class
cost does not. It does not prove a Java 11 order effect.

## Check

The check replaced only the two calls to
`GUESS_COMPACT.matcher(...).matches()` in `getConstructor` with this
linear shape predicate:

```java
private static boolean hasCompactShape(String scalar) {
  if (scalar.length() < 3 || scalar.charAt(scalar.length() - 1) != ')'
      || scalar.indexOf('(') < 1) {
    return false;
  }
  char first = scalar.charAt(0);
  return first >= 'A' && first <= 'Z' || first >= 'a' && first <= 'z';
}
```

The change did not alter `getCompactData`, `FIRST_PATTERN`,
`PROPERTY_NAME_PATTERN`, fixture inputs, test methods, or assertions. Thus,
the real compact-data parser still parsed each candidate after the shape
gate. The compiled class was verified as Java 8 bytecode and verified to call
`hasCompactShape` at both former matcher sites.

Ten interleaved check pairs were green:

```text
front: 2988, 3728, 3976, 3759, 3634, 3435, 4073, 3920, 3836, 4046
back:  3582, 3714, 3691, 3707, 3859, 3493, 4046, 3874, 3783, 4121
```

The paired differences, `back - front`, were:

```text
+594, -14, -285, -52, +225, +58, -27, -46, -53, +75
```

The front order won 4 of 10 pairs.

| Measure | Front | Back |
|---|---:|---:|
| Suite median | 3,797.5 ms | 3,748.5 ms |

The paired `back - front` median is -20.5 ms and its mean is +47.5 ms.

The stable baseline direction is absent. The check reduces the absolute
paired median from 567.5 ms to 20.5 ms, a 96.4% reduction, and changes its
sign slightly.

The moved class fell to 36 to 44 ms at the front and 0 ms at the back in the
Surefire XML reports. This large change is expected because the check removes
the expensive boolean regex gate. It is not used as the total-suite effect
estimate.

## Commands

The source was compiled to Java 8 bytecode with Temurin 17 because the current
compiler configuration uses `--release 8`, which Corretto 8's `javac` does
not support:

```text
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  /opt/homebrew/bin/mvn compiler:compile -DskipTests
```

`javap -verbose` reported major version 52 for both original and changed
classes. Before the added baseline pairs it showed both
`GUESS_COMPACT.matcher` call sites. Before the check it showed
`hasCompactShape` at both sites.

The three added baseline pairs used:

```text
python3 mechanism_study/run_ab.py \
  --project /Users/gabriel/Development/Research/snakeyaml \
  --java-home /Library/Java/JavaVirtualMachines/amazon-corretto-8.jdk/Contents/Home \
  --mvn /opt/homebrew/bin/mvn \
  --order front=mechanism_study/orders/snakeyaml-compact-regex-front.order \
  --order back=mechanism_study/orders/snakeyaml-compact-regex-back.order \
  --rounds 3 \
  --out mechanism_study/artifacts/snakeyaml/compact-regex-corretto8-baseline-add3 \
  --os-time
```

The ten check pairs used the same command with:

```text
--rounds 10
--out mechanism_study/artifacts/snakeyaml/compact-regex-linear-gate-corretto8-r10-clean
```

## Raw evidence and exclusions

Accepted baseline:

- `mechanism_study/artifacts/snakeyaml/compact-regex-front-back`
- `mechanism_study/artifacts/snakeyaml/compact-regex-corretto8-baseline-add3`

Accepted check:

- `mechanism_study/artifacts/snakeyaml/compact-regex-linear-gate-corretto8-r10-clean`

Supporting Corretto 8 counters:

- `mechanism_study/artifacts/snakeyaml/compact-regex-jdk8-instrumented`

Direct Java 8 regex stacks:

- `mechanism_study/artifacts/snakeyaml/warm-cold-xint/compact-thread-1.txt`
- `mechanism_study/artifacts/snakeyaml/warm-cold-xint/compact-thread-2.txt`

Java 11 scope and `Pattern$Loop` compilation:

- `mechanism_study/artifacts/snakeyaml/compact-regex-flow-jfr/00-00-front.jfr`
- `mechanism_study/artifacts/snakeyaml/compact-regex-flow-jfr/front-flow.txt`
- `mechanism_study/artifacts/snakeyaml/compact-regex-flow-jfr/back-flow.txt`

The partial directory
`compact-regex-corretto8-baseline-r10` overlapped another high-load
experiment and is excluded. The interrupted
`compact-regex-linear-gate-corretto8-r10` directory is also excluded.

The original `CompactConstructor.java` source and original compiled class were
restored after the check. The pre-existing `pom.xml` and `.csto2/` changes
were left untouched.
