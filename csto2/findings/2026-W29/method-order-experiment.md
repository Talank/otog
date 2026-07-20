# Method, class, and package sort experiment

## Goal

The experiment measures how the sort level changes the suite time. It sorts the tests by allocation at
three levels: the package, the class, and the method. A custom JUnit launcher runs the tests, because
Surefire cannot run methods from different classes together. The harness keeps each class together. It
does not mix methods from different classes.

## Test arms

Each arm sorts the same tests in a different way:

| Arm | Package sort | Class sort | Method sort |
| --- | --- | --- | --- |
| initial | no | no | no |
| mth | no | no | yes |
| pkg | yes | no | no |
| pkg-cls | yes | yes (in package) | no |
| pkg-cls-mth | yes | yes (in package) | yes |
| cls | no (global) | yes | no |
| cls-mth | no (global) | yes | yes |

## Results

The numbers are the speed increase against the initial order. Each module used 6 rounds. The test is a
paired Wilcoxon signed-rank test.

| Arm | javaparser-core | p | symbol-solver | p |
| --- | --- | --- | --- | --- |
| pkg-cls-mth | +21.90% | 0.028 | +3.04% | 0.028 |
| pkg | +21.47% | 0.028 | +2.50% | 0.028 |
| pkg-cls | +20.07% | 0.028 | +1.48% | 0.463 |
| cls-mth | +19.76% | 0.028 | +4.37% | 0.028 |
| cls | +12.33% | 0.028 | +4.50% | 0.345 |
| mth | +1.99% | 0.600 | −0.70% | 0.463 |

## Notes

Based on the results, sorting package-class-method has a marginal benefit over sorting package-class. This experiment was just run to assess potential for a larger experiment in the future. Now that the machine is free, this week presents an opportunity to run more experiments. 

One caveat: the speed increase for javaparser's `symbol-solver-testing` was unusually low. It is unknown why this is the case. It may have been because the harness for this experiment specifically did not use Surefire and simply loaded and ran tests manually.