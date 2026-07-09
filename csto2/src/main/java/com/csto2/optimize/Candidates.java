package com.csto2.optimize;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Generates a small set of CANDIDATE orders embodying different, individually-defensible hypotheses.
 * No single model is trusted; the measured selection gate (see {@code select}) picks whichever
 * candidate is actually fastest, with initial as a protected incumbent so a regression can never ship.
 *
 * <p>Design follows the core-testing autopsy:
 * <ul>
 *   <li>heavy allocators belong EARLY (deterministic on allocation magnitude, not a noisy slope sign);</li>
 *   <li>only move a class late when its negative position-slope is HIGH-CONFIDENCE (low residual);</li>
 *   <li>otherwise stay close to initial, which preserves test-family adjacency and JIT type-profile
 *       coherence that an aggressive global re-sort destroys.</li>
 * </ul>
 */
public final class Candidates {

    /**
     * Every candidate-strategy name {@code select} can produce, in generation order — the catalog the
     * wizard offers for enable/disable. {@link #PROTECTED_NAMES} can never be disabled.
     */
    public static final List<String> ALL_NAMES = List.of(
            "initial", "naive", "alloc-front+warm-tail",
            "pkg-alloc-front", "pkg-rt-front", "rt-heavy-tail",
            "alloc-sort", "jit-sort");

    /** Strategies that always run: the protected incumbent and the free baseline a real win must beat. */
    public static final java.util.Set<String> PROTECTED_NAMES = java.util.Set.of("initial", "naive");

    public static final class Stat {
        double allocMB, slope, intercept, residStd, medRt, medJit;
        int n;
    }

    public static Map<String, Stat> stats(Path tracePath) throws Exception {
        Map<String, List<double[]>> obs = new LinkedHashMap<>(); // test -> [pos, rt, allocMB]
        for (String l : Files.readAllLines(tracePath)) {
            l = l.trim(); if (l.isEmpty()) continue;
            Map<String, Object> r = MiniJson.parseObject(l);
            // Skip non-PASS rows (FAIL/MISSING sentinels from a crashed fork): their runtimeMs is 0 or
            // meaningless and would poison the per-class slope/median the candidate strategies fit.
            Object st = r.get("status");
            if (st != null && !"PASS".equals(st)) continue;
            String t = (String) r.get("test");
            double pos = ((Number) r.get("position")).doubleValue();
            double rt = ((Number) r.get("runtimeMs")).doubleValue();
            double a = r.containsKey("allocBytes") ? ((Number) r.get("allocBytes")).doubleValue() / 1e6 : 0;
            double jit = r.containsKey("jitMs") ? ((Number) r.get("jitMs")).doubleValue() : 0;
            obs.computeIfAbsent(t, k -> new ArrayList<>()).add(new double[]{pos, rt, a, jit});
        }
        Map<String, Stat> out = new LinkedHashMap<>();
        for (Map.Entry<String, List<double[]>> e : obs.entrySet()) {
            List<double[]> v = e.getValue();
            Stat s = new Stat(); s.n = v.size();
            int n = v.size();
            double sx = 0, sy = 0; for (double[] p : v) { sx += p[0]; sy += p[1]; }
            double mx = sx / n, my = sy / n, sxx = 0, sxy = 0;
            for (double[] p : v) { double dx = p[0] - mx; sxx += dx * dx; sxy += dx * (p[1] - my); }
            s.slope = sxy / (sxx + 50.0);
            s.intercept = my - s.slope * mx;
            double ss = 0; for (double[] p : v) { double pr = s.intercept + s.slope * p[0]; ss += (p[1] - pr) * (p[1] - pr); }
            s.residStd = Math.sqrt(ss / n);
            s.allocMB = median(v, 2);
            s.medRt = median(v, 1);
            s.medJit = median(v, 3);
            out.put(e.getKey(), s);
        }
        return out;
    }

    /** Build the named candidate orders. */
    public static Map<String, List<String>> generate(List<String> initial, Map<String, Stat> stats, Path tracePath,
                                                     double coldSlope, double maxResid,
                                                     double heavyK, double heavyCap) throws Exception {
        Map<String, List<String>> cands = new LinkedHashMap<>();
        cands.put("initial", new ArrayList<>(initial));      // as-given/default order
        cands.put("naive", fastestObserved(tracePath, initial)); // fastest of the trivially-observed orders

        // heavy allocators (adaptive log-MAD outliers), descending -- feeds the alloc-front+warm-tail
        // combo below. (The standalone alloc-front candidate was dropped: 0 shipped wins, dominated by
        // pkg-alloc-front/alloc-sort.)
        List<String> heavy = heavyOutliers(initial, stats, s -> s.allocMB, heavyK, heavyCap);
        heavy.sort(Comparator.comparingDouble((String t) -> -stats.get(t).allocMB));
        java.util.Set<String> heavyAllocSet = new java.util.HashSet<>(heavy);

        // confident cold-sensitive classes (steep negative slope, low residual), not a heavy allocator --
        // feeds the combo. (The standalone warm-tail candidate was dropped: 0 shipped wins, and the
        // runtime-only rt-heavy-tail supersedes it, firing even where the slope model is blind.)
        List<String> cold = new ArrayList<>();
        for (String t : initial) {
            Stat s = stats.get(t);
            if (s != null && s.slope <= coldSlope && s.residStd <= maxResid && !heavyAllocSet.contains(t)) cold.add(t);
        }

        // combined: heavy allocators to front AND cold-sensitive classes to tail
        List<String> combo = move(move(initial, heavy, true), cold, false);
        cands.put("alloc-front+warm-tail", combo);

        // Whole-package block moves: sort package blocks by aggregate signal, but preserve the
        // project's original order inside each package. This is the middle ground between minimal
        // local perturbations and destructive global sorts. It keeps suite-authored adjacency within
        // coherent test families while still moving alloc/runtime-heavy regions earlier.
        cands.put("pkg-alloc-front", packageBlockSort(initial, stats, Signal.ALLOC, true));
        cands.put("pkg-rt-front", packageBlockSort(initial, stats, Signal.RUNTIME, true));

        // Runtime-heavy TAIL: move the runtime-heaviest classes (adaptive log-MAD outliers) to the tail,
        // preserving initial order within the tail and among the rest. Runtime-only, so it fires even
        // on plain-JUnit4 suites where the agent is blind (jitMs/alloc = 0) and warm-tail's slope model
        // has no signal to fit -- exactly the case warm-tail structurally misses. Locality-preserving
        // (outlier-bounded + capped, not a global sort), so the few heavy classes inherit maximum
        // accumulated JIT/type-cache warmth by running last, while the rest keep suite-authored
        // adjacency. Won snakeyaml (+5.8-8.1%) and jackson-core (+4.8%); regressions (e.g. commons-math,
        // where the heavies are position-invariant self-warmers) are gated out by select's green gate.
        List<String> heavyRt = heavyOutliers(initial, stats, s -> s.medRt, heavyK, heavyCap);
        heavyRt.sort(Comparator.comparingDouble((String t) -> stats.get(t).medRt)); // ascending: heaviest deepest in the tail
        cands.put("rt-heavy-tail", move(initial, heavyRt, false));


        // Global allocation-descending sort: a FULL re-sort by allocation, not the threshold-bounded
        // minimal perturbation of alloc-front. Captures alloc-dominated suites where many MEDIUM
        // allocators (none individually over alloc-front's threshold) collectively drive GC -- a full
        // sort fronts them all. Generalizes across alloc-heavy suites (jackson-core +5.4%, paimon +5.8%
        // vs initial) but breaks JIT/locality on locality-bound suites (javaparser -17%). Safe to offer:
        // select's green gate only ships it where it actually measures faster.
        List<String> allocSorted = new ArrayList<>(initial);
        allocSorted.sort(Comparator.comparingDouble((String t) -> {
            Stat s = stats.get(t);
            return s == null ? 0 : -s.allocMB;     // largest allocator first
        }));
        cands.put("alloc-sort", allocSorted);

        // Global JIT-warmup sort: sort by per-test compilation time (jitMs) descending. For JIT-BOUND
        // suites (where compilation, not GC or compute, dominates -- e.g. jackson-core: ~8.5s of a 12s
        // run is JIT), front-loading the compilation-heaviest tests warms the JIT once so everyone after
        // runs hot, cutting total compilation. Measured jackson-core +3.3% vs naive / +10% vs initial
        // (beat the fastest-observed baseline, confirmed over 7 rounds). Like alloc-sort this is a global
        // re-sort, so it breaks locality on locality-bound suites -- select's green gate gates it.
        List<String> jitSorted = new ArrayList<>(initial);
        jitSorted.sort(Comparator.comparingDouble((String t) -> {
            Stat s = stats.get(t);
            return s == null ? 0 : -s.medJit;      // heaviest compiler first
        }));
        cands.put("jit-sort", jitSorted);

        return cands;
    }

    private enum Signal { ALLOC, RUNTIME }

    /**
     * Sort whole package blocks by aggregate signal, preserving first-appearance package order for
     * ties and preserving the original class order inside each package. The stability matters:
     * package adjacency often encodes fixture/resource/JIT locality that per-class global sorts break.
     */
    static List<String> packageBlockSort(List<String> initial, Map<String, Stat> stats, Signal signal, boolean toFront) {
        final class Block {
            final String pkg;
            final int first;
            final List<String> members = new ArrayList<>();
            Block(String pkg, int first) { this.pkg = pkg; this.first = first; }
            double score() {
                double s = 0;
                for (String t : members) {
                    Stat st = stats.get(t);
                    if (st == null) continue;
                    if (signal == Signal.ALLOC) {
                        s += st.allocMB;
                    } else if (signal == Signal.RUNTIME) {
                        s += st.medRt;
                    }
                }
                return s;
            }
        }

        Map<String, Block> blocks = new LinkedHashMap<>();
        for (int i = 0; i < initial.size(); i++) {
            String t = initial.get(i);
            String p = packageName(t);
            Block b = blocks.get(p);
            if (b == null) {
                b = new Block(p, i);
                blocks.put(p, b);
            }
            b.members.add(t);
        }
        List<Block> ordered = new ArrayList<>(blocks.values());
        // toFront: heaviest packages first (score desc). toTail: heaviest packages last (score asc),
        // so runtime-heavy regions run warmest. Ties keep first-appearance order either way.
        Comparator<Block> byScore = toFront
                ? Comparator.comparingDouble(Block::score).reversed()
                : Comparator.comparingDouble(Block::score);
        ordered.sort(byScore.thenComparingInt(b -> b.first));
        List<String> out = new ArrayList<>(initial.size());
        for (Block b : ordered) out.addAll(b.members);
        return out;
    }

    private static String packageName(String test) {
        int dot = test.lastIndexOf('.');
        return dot < 0 ? "" : test.substring(0, dot);
    }

    /** Move {@code group} to the front (toFront=true) or back (false), preserving the given group order. */
    private static List<String> move(List<String> base, List<String> group, boolean toFront) {
        java.util.Set<String> g = new java.util.LinkedHashSet<>(group);
        List<String> rest = new ArrayList<>();
        for (String t : base) if (!g.contains(t)) rest.add(t);
        List<String> out = new ArrayList<>();
        if (toFront) { out.addAll(group); out.addAll(rest); }
        else { out.addAll(rest); out.addAll(group); }
        return out;
    }

    /** The traced order with the lowest total runtime (the paper's "naive" selection). */
    private static List<String> fastestObserved(Path tracePath, List<String> fallback) throws Exception {
        Map<String, Double> total = new LinkedHashMap<>();
        Map<String, List<String[]>> orderRows = new LinkedHashMap<>(); // orderId -> [pos, test]
        for (String l : Files.readAllLines(tracePath)) {
            l = l.trim(); if (l.isEmpty()) continue;
            Map<String, Object> r = MiniJson.parseObject(l);
            // Skip non-PASS rows so a crashed order's MISSING sentinels neither add to its total nor count
            // toward coverage below -- otherwise the sentinel carries the class name and would make an
            // incomplete order look fully-covered, letting the OOM-truncated run win as "naive".
            Object st = r.get("status");
            if (st != null && !"PASS".equals(st)) continue;
            String oid = (String) r.get("orderId");
            total.merge(oid, ((Number) r.get("runtimeMs")).doubleValue(), Double::sum);
            orderRows.computeIfAbsent(oid, k -> new ArrayList<>())
                    .add(new String[]{String.valueOf(((Number) r.get("position")).intValue()), (String) r.get("test")});
        }
        if (total.isEmpty()) return new ArrayList<>(fallback);
        // Only rank runs that actually covered the full suite. A run whose fork crashed early (e.g. an
        // OOM-killed JVM) records only the classes that completed before the crash, so its summed runtime
        // is artificially tiny and would otherwise always win -- collapsing "naive" to whatever handful of
        // classes happened to run before the crash. Require complete coverage before comparing totals.
        java.util.Set<String> required = new java.util.HashSet<>(fallback);
        List<String> complete = new ArrayList<>();
        for (Map.Entry<String, List<String[]>> e : orderRows.entrySet()) {
            java.util.Set<String> seen = new java.util.HashSet<>();
            for (String[] a : e.getValue()) seen.add(a[1]);
            if (seen.containsAll(required)) complete.add(e.getKey());
        }
        if (complete.isEmpty()) return new ArrayList<>(fallback); // no run finished the whole suite; don't trust partials
        String best = complete.stream().min(Comparator.comparingDouble(total::get)).get();
        List<String[]> rows = orderRows.get(best);
        rows.sort(Comparator.comparingInt(a -> Integer.parseInt(a[0])));
        java.util.Set<String> allowed = new java.util.HashSet<>(fallback);
        List<String> order = new ArrayList<>();
        for (String[] a : rows) if (allowed.contains(a[1])) order.add(a[1]); // keep only stable classes
        return order;
    }

    private static double median(List<double[]> v, int idx) {
        List<Double> s = new ArrayList<>(); for (double[] p : v) s.add(p[idx]); s.sort(Double::compare);
        int n = s.size(); return n == 0 ? 0 : (n % 2 == 1 ? s.get(n / 2) : (s.get(n / 2 - 1) + s.get(n / 2)) / 2);
    }

    private static double medianOf(List<Double> v) {
        if (v.isEmpty()) return 0;
        List<Double> s = new ArrayList<>(v); s.sort(Double::compare);
        int n = s.size(); return n % 2 == 1 ? s.get(n / 2) : (s.get(n / 2 - 1) + s.get(n / 2)) / 2;
    }

    /**
     * Adaptive "heavy" selection. Flags a class heavy when its signal, on a LOG scale, sits more than
     * {@code k} standard deviations above the mean: {@code log1p(signal) > mean + k * stddev}. Log scale
     * because test signals (runtime, allocation) are multiplicative and span orders of magnitude; the log
     * transform naturally reins in extreme outliers so the mean and standard deviation remain robust. This
     * replaces the old fixed absolute cutoffs (heavy-rt-ms=50, heavy-alloc-mb=500), which picked a
     * suite-dependent fraction (2% of snakeyaml but 10%+ of others) for the same number.
     *
     * <p>Capped at {@code capFrac} of the suite so it can NEVER degenerate into a global sort (the whole
     * point of a threshold-based, locality-preserving move); if more than the cap qualify, the top
     * {@code capFrac} by raw signal are kept. Returns [] when there is no clear heavy tail (uniform
     * suite) or the signal is absent (e.g. alloc on an agent-blind plain-JUnit4 run) -- the candidate
     * then degenerates harmlessly to initial, which the green gate treats as a duplicate.
     */
    static List<String> heavyOutliers(List<String> initial, Map<String, Stat> stats,
                                      java.util.function.ToDoubleFunction<Stat> signal, double k, double capFrac) {
        int n = initial.size();
        if (n == 0) return new ArrayList<>();
        List<Double> logs = new ArrayList<>(n);
        for (String t : initial) {
            Stat s = stats.get(t);
            double v = s == null ? 0 : Math.max(0, signal.applyAsDouble(s));
            logs.add(Math.log1p(v));
        }
        double mean = 0;
        for (double x : logs) mean += x;
        mean /= n;
        double var = 0;
        for (double x : logs) var += (x - mean) * (x - mean);
        var /= n;
        double stddev = Math.sqrt(var);
        double thr = mean + k * stddev;
        List<String> heavy = new ArrayList<>();
        for (int i = 0; i < n; i++) if (logs.get(i) > thr) heavy.add(initial.get(i));
        int cap = Math.max(1, (int) Math.floor(n * capFrac));
        if (heavy.size() > cap) {
            heavy.sort(Comparator.comparingDouble((String t) -> {
                Stat s = stats.get(t); return s == null ? 0 : -signal.applyAsDouble(s);
            }));
            heavy = new ArrayList<>(heavy.subList(0, cap));
        }
        return heavy;
    }
}
