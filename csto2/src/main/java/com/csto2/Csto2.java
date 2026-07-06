package com.csto2;

import com.csto2.analyze.StaticComprehension;
import com.csto2.analyze.StaticEdges;
import com.csto2.optimize.Candidates;
import com.csto2.optimize.OrderOptimizer;
import com.csto2.trace.OrderRunner;
import com.csto2.surefire.SurefireOrchestrator;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/** CSTO v2 CLI. First command: static comprehension. */
public final class Csto2 {
    public static void main(String[] args) throws Exception {
        // Launch the interactive REPL for: no args, `repl [dir]`, `pipeline [dir]`, or a bare directory.
        boolean replCmd = args.length > 0 && (args[0].equals("repl") || args[0].equals("pipeline"));
        boolean bareDir = args.length == 1 && java.nio.file.Files.isDirectory(java.nio.file.Paths.get(args[0]));
        if (args.length == 0 || replCmd || bareDir) {
            String dir = replCmd ? (args.length > 1 ? args[1] : null) : (bareDir ? args[0] : null);
            com.csto2.cli.Repl repl = new com.csto2.cli.Repl();
            if (dir != null) repl.run(java.nio.file.Paths.get(dir)); else repl.run();
            return;
        }
        dispatch(args[0], parse(args));
    }

    /** Run a single subcommand with a pre-parsed flag map. Public so the REPL can drive the pipeline. */
    public static void dispatch(String cmd, Map<String, String> a) throws Exception {
        switch (cmd) {
            case "analyze" -> analyze(a);
            case "discover" -> discover(a);
            case "trace" -> trace(a);
            case "validate" -> validate(a);
            case "select" -> select(a);
            default -> usage();
        }
    }

    private static void discover(Map<String, String> a) throws Exception {
        String cp = filterClasspath(req(a, "cp"));
        Path candidates = Paths.get(req(a, "tests"));
        Path out = Paths.get(req(a, "out"));
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        List<String> cmd = new ArrayList<>();
        cmd.add(javaBin(a));
        cmd.addAll(jvmArgs(a));
        cmd.add("-cp"); cmd.add(cp + File.pathSeparator + self.toAbsolutePath());
        cmd.add("com.csto2.trace.TestDiscovery");
        cmd.add("--discover"); cmd.add("--tests"); cmd.add(candidates.toString());
        cmd.add("--out"); cmd.add(out.toString());
        ProcessBuilder pb = new ProcessBuilder(cmd).inheritIO();
        Path wd = resolveWorkDir(a, cp);
        if (wd != null) pb.directory(wd.toFile());
        int code = pb.start().waitFor();
        if (code != 0) throw new IllegalStateException("discover failed with exit " + code);
    }

    /**
     * Build the order runner the pipeline measures with. All measurement runs through REAL Maven
     * Surefire (the testorder fork) so timing + greenness match {@code mvn test}; {@code --surefire-ext}
     * (the changing-maven-extension jar) is required. Per-class alloc/jit/gc/JFR come from the
     * injected agent (csto2-agent.jar, auto-located beside csto2.jar). The old in-JVM TraceRunner
     * backend has been retired — only its reflection-based discovery survives as {@code TestDiscovery}.
     */
    private static OrderRunner makeRunner(Map<String, String> a, String cp, Path outDir, Path self) throws Exception {
        return makeRunner(a, cp, outDir, self, true);
    }

    /**
     * Build the Surefire-backed runner.
     *
     * <p>{@code attachAgent} controls the per-class instrumentation agent. The agent (alloc/jit/gc
     * deltas) is the engine of <b>discovery</b> — tracing needs its per-class facts. But the agent's
     * recording and listener add real overhead that perturbs the very wall-clock we optimize, so the
     * final A/B <b>validation</b> of promising orders (the {@code select} ship gate, {@code validate})
     * runs with {@code attachAgent=false} for clean timing — those phases only read runtime+status,
     * never agent facts.
     */
    private static OrderRunner makeRunner(Map<String, String> a, String cp, Path outDir, Path self,
                                          boolean attachAgent) throws Exception {
        Path ext = a.containsKey("surefire-ext") && !a.get("surefire-ext").isBlank()
                ? Paths.get(a.get("surefire-ext")) : defaultSurefireExt();
        if (ext == null || !Files.exists(ext))
            throw new IllegalArgumentException("Surefire testorder fork not found in ~/.m2 — build & install it "
                    + "(`mvn install -DskipTests -Drat.skip -Denforcer.skip` in the maven-surefire fork), or pass "
                    + "--surefire-ext <surefire-changing-maven-extension jar>.");
        if (!a.containsKey("surefire-ext")) System.err.println("[csto2] surefire extension (auto): " + ext);
        Path workDir = resolveWorkDir(a, cp);
        Path moduleDir = workDir != null ? workDir : Paths.get("").toAbsolutePath();
        SurefireOrchestrator s = new SurefireOrchestrator(moduleDir, outDir, ext, surefireMvnBin(a, moduleDir));
        Path jHome = resolveJavaHome(a);
        if (jHome != null) s.setJavaHome(jHome);
        if (a.containsKey("kp-argline")) s.setKpArgline(a.get("kp-argline"));
        if (!attachAgent) {
            System.err.println("[csto2] measurement runner: no agent (clean wall-clock for A/B validation)");
            return s;
        }
        // Per-class instrumentation agent: explicit --agent, else csto2-agent.jar beside csto2.jar.
        Path agent = a.containsKey("agent") ? Paths.get(a.get("agent"))
                : (self.getParent() == null ? null : self.getParent().resolve("csto2-agent.jar"));
        if (agent != null && Files.exists(agent) && !"none".equals(a.get("agent"))) {
            s.setAgent(agent);
            System.err.println("[csto2] surefire instrumentation agent: " + agent);
        } else {
            System.err.println("[csto2] no instrumentation agent (runtime+status only); build csto2-agent.jar or pass --agent");
        }
        return s;
    }

    /** Auto-locate the installed testorder-fork extension jar in the local Maven repo (newest). */
    public static Path defaultSurefireExt() {
        Path base = Paths.get(System.getProperty("user.home"), ".m2", "repository",
                "fun", "jvm", "surefire", "flaky", "surefire-changing-maven-extension");
        if (!Files.isDirectory(base)) return null;
        try (java.util.stream.Stream<Path> s = Files.walk(base, 2)) {
            return s.filter(p -> p.getFileName().toString().matches("surefire-changing-maven-extension-.*\\.jar"))
                    .max(java.util.Comparator.comparing(Path::toString)).orElse(null);
        } catch (java.io.IOException e) { return null; }
    }

    private static String surefireMvnBin(Map<String, String> a, Path dir) {
        String m = a.get("mvn");
        if (m != null && !m.isBlank()) return m;
        Path w = dir.resolve("mvnw");
        return Files.isExecutable(w) ? w.toAbsolutePath().toString() : "mvn";
    }

    private static void trace(Map<String, String> a) throws Exception {
        String cp = filterClasspath(req(a, "cp"));
        Path testsFile = Paths.get(req(a, "tests"));
        int orders = Integer.parseInt(a.getOrDefault("orders", "6"));
        long seed = Long.parseLong(a.getOrDefault("seed", "1"));
        Path outDir = Paths.get(a.getOrDefault("out", ".csto2/trace"));
        List<String> tests = readTests(testsFile);
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());

        long t0 = System.nanoTime();
        OrderRunner orch = makeRunner(a, cp, outDir, self);
        Path traceOut = orch.run(tests, orders, seed);
        System.err.printf("[csto2] traced %d orders in %.1fs -> %s%n", orders, (System.nanoTime() - t0) / 1e9, traceOut);
    }

    private static void validate(Map<String, String> a) throws Exception {
        String cp = filterClasspath(req(a, "cp"));
        Path testsFile = Paths.get(req(a, "tests"));
        Path tracePath = Paths.get(req(a, "trace"));     // existing trace.jsonl for calibration
        int repeats = Integer.parseInt(a.getOrDefault("repeats", "5"));
        Path outDir = Paths.get(a.getOrDefault("out", ".csto2/validate"));
        List<String> tests = readTests(testsFile);
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        Files.createDirectories(outDir);

        OrderOptimizer.Model model = OrderOptimizer.calibrate(tracePath);
        List<String> initial = new ArrayList<>(tests);
        List<String> optimized = OrderOptimizer.optimize(model, tests);
        OrderOptimizer.writeReport(model, initial, optimized, outDir.resolve("optimization.json"));
        Path initialFile = outDir.resolve("initial.order");
        Path optFile = outDir.resolve("optimized.order");
        Files.write(initialFile, String.join("\n", initial).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        Files.write(optFile, String.join("\n", optimized).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        System.err.println("[csto2] front class chosen: " + optimized.get(0));
        System.err.printf("[csto2] predicted: initial=%.0fms optimized=%.0fms%n",
                model.predict(initial), model.predict(optimized));

        Path measure = outDir.resolve("measure.jsonl");
        Files.deleteIfExists(measure);
        // Validate promising orders with NO agent: the instrumentation/JFR overhead perturbs the
        // wall-clock we are comparing. report() only reads runtimeMs, so agent facts aren't needed.
        OrderRunner orch = makeRunner(a, cp, outDir, self, false);
        // Interleave repeats to spread background-load noise evenly across both orders.
        for (int r = 0; r < repeats; r++) {
            orch.runOrder(initialFile, "initial#" + r, measure);
            orch.runOrder(optFile, "optimized#" + r, measure);
            System.err.println("[csto2] measured repeat " + (r + 1) + "/" + repeats);
        }
        report(measure);
    }

    private static void select(Map<String, String> a) throws Exception {
        String cp = filterClasspath(req(a, "cp"));
        Path testsFile = Paths.get(req(a, "tests"));
        Path tracePath = Paths.get(req(a, "trace"));
        int repeats = Integer.parseInt(a.getOrDefault("repeats", "4"));
        double heavyAllocMB = Double.parseDouble(a.getOrDefault("heavy-alloc-mb", "500"));
        double heavyJitMs = Double.parseDouble(a.getOrDefault("heavy-jit-ms", "100"));
        double coldSlope = Double.parseDouble(a.getOrDefault("cold-slope", "-1.0"));
        double maxResid = Double.parseDouble(a.getOrDefault("max-resid", "300"));
        double heavyRtMs = Double.parseDouble(a.getOrDefault("heavy-rt-ms", "50"));
        double cpGate = Double.parseDouble(a.getOrDefault("cp-gate", "1.5"));
        double cpMinMs = Double.parseDouble(a.getOrDefault("cp-min-ms", "8"));
        int cpTopK = Integer.parseInt(a.getOrDefault("cp-top-k", "24"));
        int cpRotate = Integer.parseInt(a.getOrDefault("cp-rotate", "6"));
        int cpColdRepeats = Integer.parseInt(a.getOrDefault("cp-cold-repeats", "2"));
        int cpWarmRepeats = Integer.parseInt(a.getOrDefault("cp-warm-repeats", "3"));
        Path outDir = Paths.get(a.getOrDefault("out", ".csto2/select"));
        List<String> tests = readTests(testsFile);
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        Files.createDirectories(outDir);

        // Keep ALL tests. We never drop tests; instead the selection gate ships only an order that
        // measures fully GREEN (0 failures, 0 timeouts). A green order is known to exist (initial),
        // so any shipped order must be at least as correct as initial AND faster.
        System.err.println("[csto2] optimizing all " + tests.size() + " classes; will ship only a fully-green order");

        // Approaches the user disabled in the wizard / CLI. 'initial' and 'naive' are protected and can
        // never be skipped (incumbent + free baseline). Only the measurement of a disabled strategy is avoided.
        java.util.Set<String> skip = csv(a.get("skip-candidates"));
        skip.removeAll(Candidates.PROTECTED_NAMES);

        Map<String, Candidates.Stat> stats = Candidates.stats(tracePath);
        Map<String, List<String>> cands = Candidates.generate(tests, stats, tracePath, heavyAllocMB, heavyJitMs, coldSlope, maxResid, heavyRtMs);

        // Validation runner, agent OFF: the agent's recording/listener overhead would confound the very
        // wall-clock the ship gate decides on, and select reads only runtime+status (never agent facts).
        OrderRunner validate = makeRunner(a, cp, outDir, self, false);

        // Drop any disabled strategy that was generated above so it is never measured (the costly part).
        for (String s : skip)
            if (cands.remove(s) != null) System.err.println("[csto2] approach disabled: " + s);

        for (Map.Entry<String, List<String>> e : cands.entrySet()) {
            Files.write(outDir.resolve(e.getKey() + ".order"),
                    String.join("\n", e.getValue()).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            System.err.println("[csto2] candidate " + e.getKey() + " (" + e.getValue().size() + " classes)");
        }

        // ---- Cold-penalty probe: the DIAGNOSTIC warmup-tail (displacement estimator) ----
        // The mechanism behind rt-tail is shared-code JIT warmup: a class carries a "cold penalty" =
        // extra time executing shared bytecode not yet JIT-compiled. rt-tail proxies that by runtime
        // MAGNITUDE, which mis-handles self-warming benchmarks (a class whose own tight loop compiles
        // itself has huge jitMs but ~0 cold penalty). Here we MEASURE the penalty directly, agent off:
        //   penalty(X) = median rt(X in the INITIAL order)  -  median rt(X at the extreme TAIL, rt-tail)
        // The initial order is the informative COLD context (package grouping delays compilation of the
        // shared core, so heavy classes run before it is hot); rt-tail is the WARM context. Self-warm
        // compilation happens in BOTH conditions and cancels, so self-warmers read ~0 and are left in
        // place. Only classes whose penalty clears their own same-position noise (cpGate x IQR) are
        // tail-loaded. Cheap: two orders x cpProbeRepeats clean repeats.
        if (!skip.contains("cold-penalty-tail")) {
            try {
                // Finder (order-free): rank ALL classes by warm median runtime and take the top K above a
                // low floor. medRt is measured position-independently, so — unlike the old
                // "early in the initial order" filter — it introduces NO initial-order dependence, and it
                // correlates ~0.97 with intrinsic JIT-benefit so it already carries the ranking of the
                // gain-carriers. The low floor + top-K keeps recall high without a magnitude cliff; the
                // probe's near-cold reads then self-audit any small class that turns out to matter.
                List<String> cpCands = new ArrayList<>();
                for (String t : tests) { Candidates.Stat s = stats.get(t); if (s != null && s.medRt >= cpMinMs) cpCands.add(t); }
                cpCands.sort(java.util.Comparator.comparingDouble((String t) -> -stats.get(t).medRt)); // heaviest first
                if (cpCands.size() > cpTopK) cpCands = new ArrayList<>(cpCands.subList(0, cpTopK));
                List<String> cpt = coldPenaltyTail(validate, outDir, tests, cpCands, stats, heavyRtMs, cpRotate, cpColdRepeats, cpWarmRepeats, cpGate);
                if (cpt != null) {
                    cands.put("cold-penalty-tail", cpt);
                    Files.write(outDir.resolve("cold-penalty-tail.order"),
                            String.join("\n", cpt).getBytes(java.nio.charset.StandardCharsets.UTF_8));
                }
            } catch (Exception e) {
                System.err.println("[csto2] cold-penalty probe skipped: " + e);
            }
        }

        Path measure = outDir.resolve("measure.jsonl");
        Files.deleteIfExists(measure);
        // Interleave: one repeat = each candidate once, but SHUFFLE the within-round order each round.
        // A fixed order pins every candidate to the same slot every round, so any within-round drift
        // (OS file-cache warming, thermal, harness JIT) becomes a systematic per-candidate bias —
        // e.g. the incumbent (always first/cold) looks slow and a later candidate looks fast for free.
        // Seeded shuffle keeps it reproducible while decorrelating slot from candidate.
        List<String> names = new ArrayList<>(cands.keySet());
        java.util.Random shufRnd = new java.util.Random(20240625L);
        for (int r = 0; r < repeats; r++) {
            java.util.Collections.shuffle(names, shufRnd);
            for (String name : names)
                validate.runOrder(outDir.resolve(name + ".order"), name + "#" + r, measure);
            System.err.println("[csto2] measured round " + (r + 1) + "/" + repeats);
        }
        selectReport(measure, "initial");
    }

    /**
     * Measured cold-penalty → the diagnostic warmup-tail order (agent off). The mechanism is shared-code
     * JIT warmup; this MEASURES each class's reorderable cold penalty rather than proxying it by runtime
     * magnitude (rt-tail) or jitMs (both conflate self-warm — a benchmark whose own loop compiles itself
     * has huge jitMs/interpreted cost but ~0 reorderable penalty). Uses NO initial-order position in its
     * judgement.
     *
     * <p><b>Rotated position-0 probe.</b> WARM baseline: all candidates clustered at the tail (each runs
     * after the whole suite has compiled the shared core). COLD baseline: rotate each of the top-R
     * heaviest candidates through <b>position 0</b> across R orders — the position-0 class runs genuinely
     * cold (nothing before it). {@code penalty(X) = median rt(X cold) − median rt(X warm)}. A self-warmer
     * compiles its own code in both conditions and cancels to ~0; a shared-core-dependent reads a large
     * positive penalty. Rotating (rather than clustering all candidates at the front at once) avoids
     * intra-cluster warming, where a cluster-mate compiles the core for a later candidate and hides its
     * penalty. Non-rotated candidates are read NEAR-cold (they sit at positions 1..K-1 of the cold
     * orders) — a conservative under-estimate that still promotes any smaller class with a real penalty,
     * self-auditing recall without an -Xint pass. A class is tail-loaded only if its penalty clears
     * gate×IQR plus a small floor; else it stays put (graceful degradation). {@code candsByWeight} is
     * heaviest-first.
     */
    private static List<String> coldPenaltyTail(OrderRunner runner, Path outDir, List<String> initial,
            List<String> candsByWeight, Map<String, Candidates.Stat> stats, double heavyRtMs,
            int rotate, int coldRepeats, int warmRepeats, double gate) throws Exception {
        if (candsByWeight.size() < 2) { System.err.println("[csto2] cold-penalty-tail: <2 candidate classes; skipped"); return null; }
        java.util.Set<String> cand = new java.util.LinkedHashSet<>(candsByWeight);
        List<String> nonCand = new ArrayList<>();
        for (String t : initial) if (!cand.contains(t)) nonCand.add(t);
        int R = Math.min(rotate, candsByWeight.size());

        // WARM order: non-candidates first, then candidates at the tail ascending weight (heaviest last).
        List<String> warm = new ArrayList<>(nonCand);
        for (int i = candsByWeight.size() - 1; i >= 0; i--) warm.add(candsByWeight.get(i));
        Files.write(outDir.resolve("cp-warm.order"), String.join("\n", warm).getBytes(java.nio.charset.StandardCharsets.UTF_8));

        Path probe = outDir.resolve("cp-probe.jsonl");
        Files.deleteIfExists(probe);
        System.err.println("[csto2] cold-penalty probe (rotated pos-0): " + R + " cold x" + coldRepeats
                + " + " + warmRepeats + " warm, over " + candsByWeight.size() + " candidates");
        for (int r = 0; r < warmRepeats; r++)
            runner.runOrder(outDir.resolve("cp-warm.order"), "cp-warm#" + r, probe);
        for (int i = 0; i < R; i++) {
            String h = candsByWeight.get(i);
            List<String> cold = new ArrayList<>();
            cold.add(h);                                                 // genuinely cold at position 0
            for (String c : candsByWeight) if (!c.equals(h)) cold.add(c);// rest of candidates near-cold
            cold.addAll(nonCand);
            Files.write(outDir.resolve("cp-cold-" + i + ".order"), String.join("\n", cold).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            for (int r = 0; r < coldRepeats; r++)
                runner.runOrder(outDir.resolve("cp-cold-" + i + ".order"), "cp-cold-" + i + "#" + r, probe);
        }

        Map<String, List<Double>> warmRt = new LinkedHashMap<>();
        Map<Integer, Map<String, List<Double>>> coldByIdx = new LinkedHashMap<>();
        for (String line : Files.readAllLines(probe)) {
            line = line.trim(); if (line.isEmpty()) continue;
            int oi = line.indexOf("\"orderId\":\""); int ti = line.indexOf("\"test\":\""); int ri = line.indexOf("\"runtimeMs\":");
            if (oi < 0 || ti < 0 || ri < 0) continue;
            String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
            String test = line.substring(ti + 8, line.indexOf('"', ti + 8));
            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
            if (oid.startsWith("cp-warm")) {
                warmRt.computeIfAbsent(test, k -> new ArrayList<>()).add(rt);
            } else if (oid.startsWith("cp-cold-")) {
                int idx = Integer.parseInt(oid.substring(8, oid.indexOf('#')));
                coldByIdx.computeIfAbsent(idx, k -> new LinkedHashMap<>()).computeIfAbsent(test, k -> new ArrayList<>()).add(rt);
            }
        }
        // Raw penalty per candidate: a rotated heavy uses its genuine pos-0 reads (cp-cold-<its index>);
        // a non-rotated candidate uses its near-cold reads pooled across all cold orders (conservative).
        Map<String, Double> penalty = new LinkedHashMap<>();
        for (int c = 0; c < candsByWeight.size(); c++) {
            String X = candsByWeight.get(c);
            List<Double> warmX = warmRt.get(X);
            if (warmX == null || warmX.isEmpty()) continue;
            List<Double> coldX;
            if (c < R) coldX = coldByIdx.getOrDefault(c, java.util.Collections.emptyMap()).get(X);   // genuine cold (pos 0)
            else { coldX = new ArrayList<>(); for (Map<String, List<Double>> m : coldByIdx.values()) { List<Double> l = m.get(X); if (l != null) coldX.addAll(l); } }
            if (coldX == null || coldX.isEmpty()) continue;
            penalty.put(X, median(coldX) - median(warmX));
        }

        // ROBUST TAIL SET. Empirically the *reorderable* per-class penalty (~50-100ms) is comparable to a
        // heavy class's own run-to-run variance, so per-class penalties are NOT individually reliable in a
        // few reps — requiring each to clear a gate throws away real gain-carriers (their outliers inflate
        // the gate). But the AGGREGATE tail effect over all heavies is robust, and the probe reliably
        // recovers the SIGN for clear cases. So: tail-load every heavy class (medRt >= heavyRtMs) — the
        // aggregate warmup win — EXCEPT any the probe confidently flags as a self-warmer (penalty clearly
        // negative). Additionally PROMOTE any lighter class the probe shows a clear positive penalty
        // (self-audit of finder recall). This is rt-heavy-tail corrected by measured self-warmer removal.
        double selfWarmCut = -Math.max(gate * 15.0, 30.0);   // "clearly negative": a self-warmer, not noise
        double promoteCut = Math.max(gate * 25.0, 40.0);     // "clearly positive": worth promoting a light class
        List<String> tailSet = new ArrayList<>();
        List<String> dropped = new ArrayList<>();
        for (String X : candsByWeight) {
            Candidates.Stat s = stats.get(X);
            double mrt = s == null ? 0 : s.medRt;
            double pen = penalty.getOrDefault(X, 0.0);
            boolean heavy = mrt >= heavyRtMs;
            if (heavy && pen < selfWarmCut) { dropped.add(X); continue; }      // confirmed self-warmer → leave in place
            if (heavy || pen > promoteCut) tailSet.add(X);                     // aggregate heavy, or promoted light class
        }
        if (tailSet.isEmpty()) { System.err.println("[csto2] cold-penalty-tail: no heavy/benefiting classes; not generated"); return null; }
        tailSet.sort(java.util.Comparator.comparingDouble((String t) -> { Candidates.Stat s = stats.get(t); return s == null ? 0 : s.medRt; })); // heaviest last
        System.err.println("[csto2] cold-penalty-tail: tail-load " + tailSet.size() + " heavy classes; dropped "
                + dropped.size() + " measured self-warmer(s): " + dropped);
        for (String X : dropped) System.err.printf("           self-warmer penalty=%+.0fms (kept in place)  %s%n", penalty.getOrDefault(X, 0.0), X);
        java.util.Set<String> mv = new java.util.LinkedHashSet<>(tailSet);
        List<String> rest = new ArrayList<>();
        for (String t : initial) if (!mv.contains(t)) rest.add(t);
        List<String> out = new ArrayList<>(rest); out.addAll(tailSet);
        return out;
    }

    private static double median(List<Double> v) {
        List<Double> s = new ArrayList<>(v); s.sort(Double::compare);
        int n = s.size(); return n == 0 ? 0 : (n % 2 == 1 ? s.get(n / 2) : (s.get(n / 2 - 1) + s.get(n / 2)) / 2);
    }
    private static double iqr(List<Double> v) {
        List<Double> s = new ArrayList<>(v); s.sort(Double::compare);
        int n = s.size(); if (n < 2) return 0;
        return s.get((int) Math.floor(0.75 * (n - 1))) - s.get((int) Math.floor(0.25 * (n - 1)));
    }

    /** Report medians + greenness per candidate; SHIP only a fully-green order (incumbent fallback). */
    private static void selectReport(Path measure, String incumbent) throws Exception {
        Map<String, List<Double>> perRun = new LinkedHashMap<>();
        Map<String, Integer> runNonPass = new LinkedHashMap<>(); // per run id: count of FAIL/TIMEOUT
        for (String line : Files.readAllLines(measure)) {
            line = line.trim(); if (line.isEmpty()) continue;
            int oi = line.indexOf("\"orderId\":\""); int ri = line.indexOf("\"runtimeMs\":");
            if (oi < 0 || ri < 0) continue;
            String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
            perRun.computeIfAbsent(oid, k -> new ArrayList<>()).add(rt);
            int si = line.indexOf("\"status\":\"");
            if (si >= 0) {
                String st = line.substring(si + 10, line.indexOf('"', si + 10));
                if (!"PASS".equals(st)) runNonPass.merge(oid, 1, Integer::sum);
            }
        }
        Map<String, List<Double>> perCand = new LinkedHashMap<>();
        Map<String, Integer> candNonPass = new LinkedHashMap<>(); // total non-pass across all runs
        for (Map.Entry<String, List<Double>> e : perRun.entrySet()) {
            String name = e.getKey().contains("#") ? e.getKey().substring(0, e.getKey().indexOf('#')) : e.getKey();
            double sum = e.getValue().stream().mapToDouble(Double::doubleValue).sum();
            perCand.computeIfAbsent(name, k -> new ArrayList<>()).add(sum);
            candNonPass.merge(name, runNonPass.getOrDefault(e.getKey(), 0), Integer::sum);
        }
        Map<String, Double> med = new LinkedHashMap<>();
        System.out.println("\n=== CANDIDATE MEASUREMENTS ===");
        for (Map.Entry<String, List<Double>> e : perCand.entrySet()) {
            List<Double> v = new ArrayList<>(e.getValue()); v.sort(Double::compare);
            double m = v.get(v.size() / 2);
            med.put(e.getKey(), m);
            int np = candNonPass.getOrDefault(e.getKey(), 0);
            System.out.printf("  %-22s runs=%d median=%.0fms min=%.0fms max=%.0fms  %s%n",
                    e.getKey(), v.size(), m, v.get(0), v.get(v.size() - 1),
                    np == 0 ? "GREEN" : ("NOT-GREEN (" + np + " non-pass)"));
        }
        double base = med.getOrDefault(incumbent, Double.NaN);
        // Ship only a fully-green candidate, fastest, with a >1% margin over incumbent to deviate.
        String winner = incumbent; double wm = base;
        for (Map.Entry<String, Double> e : med.entrySet()) {
            if (candNonPass.getOrDefault(e.getKey(), 0) != 0) continue; // green gate
            if (e.getValue() < wm) { wm = e.getValue(); winner = e.getKey(); }
        }
        if (!winner.equals(incumbent) && (base - wm) < 0.01 * base) winner = incumbent; // margin guard
        System.out.println();
        for (Map.Entry<String, Double> e : med.entrySet()) {
            if (e.getKey().equals(incumbent)) continue;
            double pct = 100.0 * (base - e.getValue()) / base;
            String grn = candNonPass.getOrDefault(e.getKey(), 0) == 0 ? "" : "  [disqualified: not green]";
            System.out.printf("  %-22s %+.1f%% vs initial%s%n", e.getKey(), pct, grn);
        }
        System.out.printf("%n=> SHIP: %s  (%.0fms, %.1f%% faster than initial) [green]%n",
                winner, wm, 100.0 * (base - wm) / base);
    }

    private static void report(Path measure) throws Exception {
        Map<String, List<Double>> totals = new LinkedHashMap<>();
        for (String line : Files.readAllLines(measure)) {
            line = line.trim();
            if (line.isEmpty()) continue;
            // orderId like "initial#3"; sum runtimeMs per run.
            int oi = line.indexOf("\"orderId\":\"");
            int ri = line.indexOf("\"runtimeMs\":");
            if (oi < 0 || ri < 0) continue;
            String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
            String group = oid.contains("#") ? oid.substring(0, oid.indexOf('#')) : oid;
            String run = oid;
            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
            totals.computeIfAbsent(group + "|" + run, k -> new ArrayList<>()).add(rt);
        }
        // sum per run, then aggregate per group
        Map<String, List<Double>> perGroup = new LinkedHashMap<>();
        for (Map.Entry<String, List<Double>> e : totals.entrySet()) {
            String group = e.getKey().substring(0, e.getKey().indexOf('|'));
            double sum = e.getValue().stream().mapToDouble(Double::doubleValue).sum();
            perGroup.computeIfAbsent(group, k -> new ArrayList<>()).add(sum);
        }
        System.out.println("\n=== MEASURED VALIDATION ===");
        Map<String, Double> medians = new LinkedHashMap<>();
        for (Map.Entry<String, List<Double>> e : perGroup.entrySet()) {
            List<Double> v = new ArrayList<>(e.getValue());
            v.sort(Double::compare);
            double med = v.get(v.size() / 2);
            System.out.printf("  %-10s runs=%d  median=%.0fms  min=%.0fms  max=%.0fms%n",
                    e.getKey(), v.size(), med, v.get(0), v.get(v.size() - 1));
            medians.put(e.getKey(), med);
        }
        Double initialMed = medians.get("initial");
        if (initialMed != null) {
            for (Map.Entry<String, Double> e : medians.entrySet()) {
                if (e.getKey().equals("initial")) continue;
                double pct = 100.0 * (initialMed - e.getValue()) / initialMed;
                System.out.printf("  => %-10s is %.1f%% %s than initial (median)%n",
                        e.getKey(), Math.abs(pct), pct >= 0 ? "FASTER" : "SLOWER");
            }
        }
    }

    private static int findEnd(String s, int from) {
        int i = from;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        return i;
    }

    /**
     * Working directory for child test JVMs. Maven Surefire runs each module's tests with the module
     * basedir as the cwd, so tests resolving relative paths (e.g. {@code src/test/resources/...}) only
     * pass when launched from there. Honors an explicit {@code --workdir}; otherwise infers the TEST
     * module basedir as the parent of the {@code target/test-classes} dir (the module whose tests we
     * run — its src/test/resources is what relative paths resolve against). Falls back to a plain
     * {@code target/classes} module only if no test-classes entry is on the classpath. Returns null
     * (inherit our cwd) when nothing can be inferred.
     */
    private static Path inferWorkDir(Map<String, String> a, String cp) {
        String wd = a.get("workdir");
        if (wd != null && !wd.isBlank()) return Paths.get(wd);
        String marker = File.separator + "target" + File.separator;
        // Prefer the test module (parent of target/test-classes); fall back to a target/classes module.
        String fallback = null;
        for (String e : cp.split(File.pathSeparator)) {
            if (e.endsWith(File.separator + "target" + File.separator + "test-classes")) {
                int i = e.lastIndexOf(marker);
                if (i > 0) return Paths.get(e.substring(0, i));
            } else if (fallback == null && e.endsWith(File.separator + "target" + File.separator + "classes")) {
                fallback = e;
            }
        }
        if (fallback != null) {
            int i = fallback.lastIndexOf(marker);
            if (i > 0) return Paths.get(fallback.substring(0, i));
        }
        return null;
    }

    private static Path resolveWorkDir(Map<String, String> a, String cp) {
        Path wd = inferWorkDir(a, cp);
        if (wd != null) System.err.println("[csto2] child JVM workdir: " + wd);
        else System.err.println("[csto2] child JVM workdir: <inherited> (pass --workdir if tests use relative paths)");
        return wd;
    }

    /** Drop classpath entries that no longer exist (stale harness entries break child JVMs too). */
    private static String filterClasspath(String cp) {
        return Arrays.stream(cp.split(File.pathSeparator))
                .map(String::trim).filter(s -> !s.isEmpty())
                .filter(s -> Files.exists(Paths.get(s)))
                .collect(Collectors.joining(File.pathSeparator));
    }

    /** Java binary for child test JVMs (e.g. point at JDK 17 for projects that don't support newer). */
    private static String javaBin(Map<String, String> a) {
        String home = a.get("java");
        if (home == null || home.isBlank()) return Paths.get(System.getProperty("java.home"), "bin", "java").toString();
        Path p = Paths.get(home);
        if (p.getFileName().toString().equals("java")) return p.toString();      // full path to java
        return p.resolve("bin").resolve("java").toString();                       // JAVA_HOME given
    }

    private static Path resolveJavaHome(Map<String, String> a) {
        String home = a.get("java");
        if (home == null || home.isBlank()) return null;
        Path p = Paths.get(home);
        if (p.getFileName().toString().equals("java")) {
            Path bin = p.getParent();
            return bin != null ? bin.getParent() : null;
        }
        return p;
    }

    /** Extra JVM args for child test JVMs (e.g. --add-opens to match the project's Surefire config). */
    private static List<String> jvmArgs(Map<String, String> a) {
        String v = a.get("jvmargs");
        if (v == null || v.isBlank()) return List.of();
        return Arrays.stream(v.trim().split("\\s+")).filter(s -> !s.isEmpty()).toList();
    }

    private static List<String> readTests(Path testsFile) throws Exception {
        return Files.readAllLines(testsFile).stream()
                .map(String::trim).filter(s -> !s.isEmpty() && !s.startsWith("#")).toList();
    }

    private static void analyze(Map<String, String> a) throws Exception {
        String app = req(a, "app");
        String lib = a.getOrDefault("lib", "");
        Path testsFile = Paths.get(req(a, "tests"));
        Path outDir = Paths.get(a.getOrDefault("out", ".csto/comprehension"));
        List<String> tests = Files.readAllLines(testsFile).stream()
                .map(String::trim).filter(s -> !s.isEmpty() && !s.startsWith("#")).toList();

        long t0 = System.nanoTime();
        System.err.println("[csto2] building class hierarchy (app + lib scope)...");
        StaticComprehension sc = StaticComprehension.build(app, lib);
        System.err.printf("[csto2] CHA built in %.1fs; analyzing %d test classes%n",
                (System.nanoTime() - t0) / 1e9, tests.size());

        Path factsOut = outDir.resolve("static-facts.jsonl");
        List<StaticComprehension.TestFacts> facts = sc.analyzeAll(tests, factsOut);
        Map<String, Object> edges = StaticEdges.derive(facts);
        Path edgesOut = outDir.resolve("static-edges.json");
        StaticEdges.write(edges, edgesOut);

        @SuppressWarnings("unchecked")
        Map<String, Object> counts = (Map<String, Object>) edges.get("counts");
        System.err.printf("[csto2] done in %.1fs%n", (System.nanoTime() - t0) / 1e9);
        System.err.println("[csto2] facts -> " + factsOut);
        System.err.println("[csto2] edges -> " + edgesOut + "  " + counts);
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> m = new LinkedHashMap<>();
        for (int i = 1; i < args.length; i++) {
            if (args[i].startsWith("--")) {
                String k = args[i].substring(2);
                // All flags take a value (e.g. --jvmargs's value itself begins with "--add-opens"),
                // so consume the next token unconditionally when present.
                if (i + 1 < args.length) m.put(k, args[++i]);
                else m.put(k, "true");
            }
        }
        return m;
    }

    private static String req(Map<String, String> a, String k) {
        String v = a.get(k);
        if (v == null || v.isBlank()) throw new IllegalArgumentException("Missing --" + k);
        return v;
    }

    /** Split a comma/whitespace-separated value into an ordered, de-duplicated set (empty if null). */
    private static java.util.Set<String> csv(String v) {
        java.util.Set<String> out = new java.util.LinkedHashSet<>();
        if (v != null) for (String s : v.split("[,\\s]+")) if (!s.isBlank()) out.add(s.trim());
        return out;
    }

    private static void usage() {
        System.out.println("""
                CSTO v2

                Commands:
                  analyze --app <classpath> [--lib <classpath>] --tests <file> [--out <dir>]
                      Static comprehension: per-test facts + candidate interaction edges.
                """);
    }
}
