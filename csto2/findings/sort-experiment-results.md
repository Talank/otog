# Sort experiment results

The experiment sorts tests by allocation at three levels: package, class, and method. It runs through
Maven Surefire. Each module used 10 rounds. The test is a paired Wilcoxon signed-rank test. The numbers
are the speed increase against the initial order.

| Arm | 1685 core | 1683 sym-solver | 3613 paimon | 1778 spring-ai |
| --- | --- | --- | --- | --- |
| pkg | +20.3% * | +2.0% | +16.6% * | −3.4% |
| pkg-cls | +21.6% * | +1.1% | +20.7% * | −1.8% |
| pkg-cls-mth | +18.0% * | +2.9% | +20.0% * | −10.7% |
| cls | +20.3% * | +8.8% * | +20.0% * | −6.5% |
| cls-mth | +18.8% * | +8.8% * | +20.9% * | −6.1% |
| mth | −3.3% | −0.5% | +1.2% | −3.7% |

`*` = significant (p < 0.05). All rounds were green.

## Results

1. A class sort gives a large speed increase on 1685 and 3613 (about +20%). Every class-sort arm is
   significant on these two modules.

2. A method-only sort (`mth`) does nothing. The result is not significant on any module.

3. On 1683, the package arms are not significant, but the class arms are (+8.8%). Thus 1683 responds to
   a global class sort but not to a package sort.

4. A package sort never beats a global class sort. On 1683 it is worse. This is evidence against the
   idea that you must keep classes together in their package.

## Caveat

Do not use 1778. The round-to-round noise was 54.8%. The suite is too small and too noisy to measure an
effect. All its arms are negative, but none are significant.

The noise on 1685 and 1683 was also high (about 41%). Trust the significant results, because they won
all 10 rounds. Do not trust the rank order between two significant arms.
