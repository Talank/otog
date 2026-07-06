package com.csto2;

import com.csto2.analyze.StaticComprehension;
import com.csto2.analyze.StaticEdges;
import com.csto2.cli.Orchestrator;
import com.csto2.optimize.Candidates;
import com.csto2.optimize.OrderOptimizer;
import com.csto2.optimize.WilcoxonSignedRank;
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
import java.util.Set;
import java.util.stream.Collectors;

/** CSTO v2 CLI. First command: static comprehension. */
public final class Csto2 {
    public static void main(String[] args) throws Exception {
        // Launch the interactive REPL for: no args, `repl [dir]`, or a bare directory.
        boolean replCmd = args.length > 0 && args[0].equals("repl");
        boolean bareDir = args.length == 1 && java.nio.file.Files.isDirectory(java.nio.file.Paths.get(args[0]));
        if (args.length == 0 || replCmd || bareDir) {
            String dir = replCmd ? (args.length > 1 ? args[1] : null) : (bareDir ? args[0] : null);
            com.csto2.cli.Repl repl = new com.csto2.cli.Repl();
            if (dir != null) repl.run(java.nio.file.Paths.get(dir)); else repl.run();
            return;
        }
        dispatch(args[0], parse(args), args);
    }

    /** Run a single subcommand with a pre-parsed flag map. Public so the REPL can drive the pipeline. */
    public static void dispatch(String cmd, Map<String, String> a) throws Exception {
        dispatch(cmd, a, new String[0]);
    }

    public static void dispatch(String cmd, Map<String, String> a, String[] rawArgs) throws Exception {
        switch (cmd) {
            case "analyze" -> analyze(a);
            case "discover" -> discover(a);
            case "trace" -> trace(a);
            case "validate" -> validate(a);
            case "select" -> select(a);

            // Orchestration subcommands (Parity with REPL)
            case "configure" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.configure(a);
            }
            case "state" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);
                orch.state();
            }
            case "exclude" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                List<String> positionals = new ArrayList<>();
                for (int i = 1; i < rawArgs.length; i++) {
                    if (rawArgs[i].startsWith("--")) {
                        i++; // skip value
                    } else {
                        positionals.add(rawArgs[i]);
                    }
                }
                List<String> tokens = new ArrayList<>();
                String val = a.get("exclude");
                if (val != null && !val.isBlank()) {
                    for (String tok : val.split("[,\\s]+")) {
                        if (!tok.isEmpty()) tokens.add(tok);
                    }
                }
                for (String pos : positionals) {
                    if (!pos.isEmpty()) tokens.add(pos);
                }

                orch.exclude(tokens);
                orch.saveConfig();
            }
            case "approaches" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                List<String> positionals = new ArrayList<>();
                for (int i = 1; i < rawArgs.length; i++) {
                    if (rawArgs[i].startsWith("--")) {
                        i++; // skip value
                    } else {
                        positionals.add(rawArgs[i]);
                    }
                }
                List<String> toggles = new ArrayList<>();
                String toggleVal = a.get("toggle");
                if (toggleVal == null || toggleVal.isBlank()) {
                    toggleVal = a.get("skip-candidates");
                }
                if (toggleVal != null && !toggleVal.isBlank()) {
                    for (String tok : toggleVal.split("[,\\s]+")) {
                        if (!tok.isEmpty()) toggles.add(tok);
                    }
                }
                for (String pos : positionals) {
                    if (!pos.isEmpty()) toggles.add(pos);
                }

                orch.approaches(toggles);
                orch.saveConfig();
            }
            case "project" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                String dirStr = a.get("dir");
                Path p = dirStr == null || dirStr.isBlank()
                        ? Paths.get(System.getProperty("user.dir"))
                        : Paths.get(dirStr);

                orch.loadProject(p, msg -> {
                    System.out.println(msg + " [auto-yes]");
                    return true;
                });
                orch.loadPersistedExclusions();
                orch.saveConfig();
            }
            case "pipeline" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                orch.fullPipeline();
                orch.saveConfig();
            }
            case "scientific" -> {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                orch.scientific();
                orch.saveConfig();
            }
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
        double heavyRtMs = Double.parseDouble(a.getOrDefault("heavy-rt-ms", "50"));
        double coldSlope = Double.parseDouble(a.getOrDefault("cold-slope", "-1.0"));
        double maxResid = Double.parseDouble(a.getOrDefault("max-resid", "300"));
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
        Map<String, List<String>> cands = Candidates.generate(tests, stats, tracePath, heavyAllocMB, coldSlope, maxResid, heavyRtMs);

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

    /**
     * Extra rigor for the REPL's "scientific" pipeline: a two-sided Wilcoxon signed-rank test of each
     * GREEN candidate vs the incumbent, pairing per-round suite totals by round index. Reads the same
     * {@code measure.jsonl} {@link #selectReport} consumes; leaves that report's output untouched (the
     * scientific path prints this on top). A candidate with any non-PASS run is skipped (green gate).
     */
    public static void signedRankReport(Path measure, String incumbent) throws Exception {
        // roundTotal[candidate][roundIdx] = summed runtimeMs; nonPass[candidate] = total non-PASS rows.
        Map<String, Map<Integer, Double>> roundTotal = new LinkedHashMap<>();
        Map<String, Integer> nonPass = new LinkedHashMap<>();
        for (String line : Files.readAllLines(measure)) {
            line = line.trim(); if (line.isEmpty()) continue;
            int oi = line.indexOf("\"orderId\":\""); int ri = line.indexOf("\"runtimeMs\":");
            if (oi < 0 || ri < 0) continue;
            String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
            int hash = oid.indexOf('#');
            String name = hash < 0 ? oid : oid.substring(0, hash);
            int round = hash < 0 ? 0 : Integer.parseInt(oid.substring(hash + 1));
            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
            roundTotal.computeIfAbsent(name, k -> new LinkedHashMap<>()).merge(round, rt, Double::sum);
            int si = line.indexOf("\"status\":\"");
            if (si >= 0 && !"PASS".equals(line.substring(si + 10, line.indexOf('"', si + 10))))
                nonPass.merge(name, 1, Integer::sum);
        }
        Map<Integer, Double> baseRounds = roundTotal.get(incumbent);
        System.out.println("\n=== WILCOXON SIGNED-RANK (paired per round, vs " + incumbent + ") ===");
        if (baseRounds == null) { System.out.println("  no '" + incumbent + "' rounds found — cannot pair."); return; }
        for (Map.Entry<String, Map<Integer, Double>> e : roundTotal.entrySet()) {
            String name = e.getKey();
            if (name.equals(incumbent)) continue;
            if (nonPass.getOrDefault(name, 0) != 0) {
                System.out.printf("  %-22s skipped (not green)%n", name);
                continue;
            }
            // Pair only rounds both orders were measured in.
            List<Double> ba = new ArrayList<>(), ca = new ArrayList<>();
            for (Map.Entry<Integer, Double> re : e.getValue().entrySet()) {
                Double bv = baseRounds.get(re.getKey());
                if (bv != null) { ba.add(bv); ca.add(re.getValue()); }
            }
            if (ba.size() < 2) { System.out.printf("  %-22s too few paired rounds (%d)%n", name, ba.size()); continue; }
            double[] a = ba.stream().mapToDouble(Double::doubleValue).toArray();
            double[] c = ca.stream().mapToDouble(Double::doubleValue).toArray();
            WilcoxonSignedRank w = WilcoxonSignedRank.test(a, c);
            double medA = median(a), medC = median(c);
            double pct = 100.0 * (medA - medC) / medA;
            System.out.printf("  %-22s n=%d  W+=%.1f W-=%.1f  p=%.4f (%s)  median %+.1f%% vs %s  %s%n",
                    name, w.n, w.wPlus, w.wMinus, w.pValue, w.exact ? "exact" : "approx",
                    pct, incumbent, w.pValue < 0.05 ? "SIGNIFICANT@0.05" : "n.s.");
        }
    }

    private static double median(double[] v) {
        double[] s = v.clone(); Arrays.sort(s);
        int n = s.length;
        return n % 2 == 1 ? s[n / 2] : (s[n / 2 - 1] + s[n / 2]) / 2.0;
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

                Stage Commands:
                  analyze --app <classpath> [--lib <classpath>] --tests <file> [--out <dir>]
                      Static comprehension: per-test facts + candidate interaction edges.
                  discover --cp <classpath> --tests <file> --out <file> [--workdir <dir>]
                      Filter the test list to runnable classes.
                  trace --cp <classpath> --tests <file> [--orders N] [--seed S] [--out <dir>]
                      Run N random test orders through Surefire to collect execution facts.
                  validate --cp <classpath> --tests <file> --trace <file> [--repeats R] [--out <dir>]
                      Calibrate the slope model and measure initial vs optimized order.
                  select --cp <classpath> --tests <file> --trace <file> [--repeats R] [--out <dir>]
                      Measure candidate strategies and select the fastest green order.

                Orchestration Commands (Parity with REPL):
                  project [--dir <dir>] [--out <dir>]
                      Autodetect classpath + test list + workdir from a Maven project.
                  configure [--cp ...] [--tests ...] [--out ...] [--jvmargs ...] ...
                      Configure and persist settings in config.properties.
                  state [--out <dir>]
                      Show current config, persisted exclusions, and candidate settings.
                  exclude <classes> | --exclude <classes> [--out <dir>]
                      Exclude test classes from the test list.
                  approaches <toggles> | --toggle <toggles> [--out <dir>]
                      Enable/disable candidate optimization strategies.
                  pipeline [--out <dir>]
                      Run the full pipeline: discover -> trace -> select.
                  scientific [--out <dir>]
                      Run the pipeline at repeats=10 + Wilcoxon signed-rank report.
                """);
    }
}
