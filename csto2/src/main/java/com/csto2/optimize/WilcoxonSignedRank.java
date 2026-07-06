package com.csto2.optimize;

import java.util.ArrayList;
import java.util.List;

/**
 * Two-sided Wilcoxon signed-rank test for a paired sample (e.g. per-round suite totals for two test
 * orders measured in the same rounds). Non-parametric, so it makes no normality assumption about the
 * per-round noise — appropriate for a handful of A/B measurement rounds.
 *
 * <p>Given paired observations {@code a[i]} (incumbent) and {@code b[i]} (candidate), it ranks the
 * nonzero absolute differences {@code d[i] = a[i] - b[i]} (average-ranking ties), sums the ranks of
 * positive and negative differences into {@code wPlus}/{@code wMinus}, and reports a two-sided
 * p-value under H0 (the two orders have the same distribution, so each sign is equally likely):
 *
 * <ul>
 *   <li><b>exact</b> for a small number {@code m} of nonzero differences ({@code m <= EXACT_MAX}):
 *       enumerate all {@code 2^m} sign assignments over the ranks and count the tail at least as
 *       extreme as the observed statistic. At m=10 this is 1024 cases.</li>
 *   <li><b>normal approximation</b> (with continuity + tie correction) beyond that.</li>
 * </ul>
 *
 * Pure and dependency-free.
 */
public final class WilcoxonSignedRank {

    /** Max number of nonzero pairs for exact enumeration (2^m assignments). */
    static final int EXACT_MAX = 20;

    public final int n;          // number of nonzero paired differences actually used
    public final double wPlus;   // sum of ranks where a-b > 0  (incumbent slower -> candidate faster)
    public final double wMinus;  // sum of ranks where a-b < 0
    public final double pValue;  // two-sided
    public final boolean exact;

    private WilcoxonSignedRank(int n, double wPlus, double wMinus, double pValue, boolean exact) {
        this.n = n; this.wPlus = wPlus; this.wMinus = wMinus; this.pValue = pValue; this.exact = exact;
    }

    /** Run the test on two equal-length paired arrays. Zero differences are dropped. */
    public static WilcoxonSignedRank test(double[] a, double[] b) {
        if (a.length != b.length) throw new IllegalArgumentException("paired arrays differ in length");

        // Collect nonzero absolute differences with their sign.
        List<double[]> diffs = new ArrayList<>(); // {absDiff, sign}
        for (int i = 0; i < a.length; i++) {
            double d = a[i] - b[i];
            if (d != 0.0) diffs.add(new double[]{Math.abs(d), Math.signum(d)});
        }
        int m = diffs.size();
        if (m == 0) return new WilcoxonSignedRank(0, 0, 0, 1.0, true); // no information

        diffs.sort((x, y) -> Double.compare(x[0], y[0]));

        // Average-rank ties on the absolute differences.
        double[] rank = new double[m];
        double[] sign = new double[m];
        int i = 0;
        while (i < m) {
            int j = i;
            while (j + 1 < m && diffs.get(j + 1)[0] == diffs.get(i)[0]) j++;
            double avg = (i + j) / 2.0 + 1.0;   // ranks are 1-based
            for (int k = i; k <= j; k++) { rank[k] = avg; sign[k] = diffs.get(k)[1]; }
            i = j + 1;
        }

        double wPlus = 0, wMinus = 0;
        for (int k = 0; k < m; k++) {
            if (sign[k] > 0) wPlus += rank[k]; else wMinus += rank[k];
        }

        double p = (m <= EXACT_MAX)
                ? exactP(rank, Math.min(wPlus, wMinus))
                : normalP(rank, m, Math.min(wPlus, wMinus));
        return new WilcoxonSignedRank(m, wPlus, wMinus, p, m <= EXACT_MAX);
    }

    /**
     * Exact two-sided p-value: over all 2^m sign assignments of the given ranks, the probability that
     * the smaller of (W+, W-) is <= the observed {@code wMin}. By symmetry that equals
     * P(W+ <= wMin) + P(W+ >= total - wMin); we compute it directly by enumeration.
     */
    private static double exactP(double[] rank, double wMin) {
        int m = rank.length;
        double total = 0;
        for (double r : rank) total += r;
        long combos = 1L << m;
        long count = 0;
        for (long mask = 0; mask < combos; mask++) {
            double wp = 0;
            for (int k = 0; k < m; k++) if ((mask & (1L << k)) != 0) wp += rank[k];
            if (Math.min(wp, total - wp) <= wMin + 1e-9) count++;
        }
        double p = (double) count / combos;
        return Math.min(1.0, p);
    }

    /** Normal approximation with continuity + tie correction. */
    private static double normalP(double[] rank, int m, double wMin) {
        double meanW = m * (m + 1) / 4.0;
        // Tie correction: subtract sum over tie-groups of (t^3 - t)/48.
        double tieAdj = 0;
        int i = 0;
        while (i < m) {
            int j = i;
            while (j + 1 < m && rank[j + 1] == rank[i]) j++;
            long t = j - i + 1;
            tieAdj += (t * t * t - t) / 48.0;
            i = j + 1;
        }
        double varW = m * (m + 1) * (2.0 * m + 1) / 24.0 - tieAdj;
        if (varW <= 0) return 1.0;
        double z = (Math.abs(wMin - meanW) - 0.5) / Math.sqrt(varW); // continuity correction
        if (z < 0) z = 0;
        return Math.min(1.0, 2.0 * (1.0 - normalCdf(z)));
    }

    /** Standard normal CDF via a numerically stable erf approximation (Abramowitz & Stegun 7.1.26). */
    private static double normalCdf(double z) {
        double x = z / Math.sqrt(2.0);
        double t = 1.0 / (1.0 + 0.3275911 * Math.abs(x));
        double y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
                + 0.254829592) * t * Math.exp(-x * x);
        double erf = x >= 0 ? y : -y;
        return 0.5 * (1.0 + erf);
    }
}
