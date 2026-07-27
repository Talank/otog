package com.csto2;

import com.csto2.cli.Orchestrator;
import com.csto2.optimize.Candidates;
import com.csto2.optimize.WilcoxonSignedRank;
import com.csto2.trace.OrderRunner;
import com.csto2.surefire.SurefireOrchestrator;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
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
        try {
            dispatch(args[0], parse(args), args);
        } catch (Exception e) {
            // Fail early: a test failed during measurement (thrown directly, or wrapped -- e.g. the
            // baseline-not-green abort). Print which order/classes and exit non-zero instead of dumping a
            // stack trace. Any other exception (bad flags, missing files) keeps its normal stack trace.
            boolean failEarly = false;
            for (Throwable t = e; t != null; t = t.getCause())
                if (t instanceof com.csto2.surefire.OrderFailedException) { failEarly = true; break; }
            if (!failEarly) throw e;
            System.err.println("[csto2] FAILED EARLY: " + e.getMessage()
                    + "\n[csto2] a test must never fail during measurement -- make the suite green "
                    + "(fix or exclude the failing test) before re-running.");
            System.exit(1);
        }
    }

    /** Run a single subcommand with a pre-parsed flag map. Public so the REPL can drive the pipeline. */
    public static void dispatch(String cmd, Map<String, String> a) throws Exception {
        dispatch(cmd, a, new String[0]);
    }

    public static void dispatch(String cmd, Map<String, String> a, String[] rawArgs) throws Exception {
        switch (cmd) {
            case "discover": discover(a); break;
            case "trace": trace(a); break;
            case "select": select(a); break;

            // Orchestration subcommands (Parity with REPL)
            case "configure": {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.configure(a);
                break;
            }
            case "state": {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);
                orch.state();
                break;
            }
            case "exclude": {
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
                break;
            }
            case "approaches": {
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
                break;
            }
            case "project": {
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
                break;
            }
            case "pipeline": {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                orch.fullPipeline();
                orch.saveConfig();
                break;
            }
            case "scientific": {
                Orchestrator orch = new Orchestrator();
                if (a.containsKey("out")) orch.cfg.put("out", a.get("out"));
                orch.loadConfig();
                orch.cfg.putAll(a);

                orch.scientific();
                orch.saveConfig();
                break;
            }
            default: usage(); break;
        }
    }

    private static void discover(Map<String, String> a) throws Exception {
        Path out = Paths.get(req(a, "out"));
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());

        Path outDir = out.getParent() != null ? out.getParent() : Paths.get(".");

        System.err.println("[discover] running mvn test to discover tests natively...");
        Path discoveryOutDir = outDir.resolve("discover");
        Files.createDirectories(discoveryOutDir);
        Path traceOut = discoveryOutDir.resolve("discovery.jsonl");
        Files.deleteIfExists(traceOut);

        SurefireOrchestrator runner = makeRunner(a, discoveryOutDir, self, false);
        int exitCode = runner.runNative("discovery", traceOut);
        if (exitCode != 0) {
            System.err.println("[discover] warning: mvn test exited with code " + exitCode + " (some tests may have failed or fork crashed)");
        }

        // Evaluate results from the mvn test run
        List<String> keptGreen = new ArrayList<>();
        List<String> skippedRed = new ArrayList<>();

        if (Files.exists(traceOut)) {
            for (String line : Files.readAllLines(traceOut)) {
                line = line.trim();
                if (line.isEmpty()) continue;
                String t = strField(line, "test");
                String s = strField(line, "status");
                long f = numField(line, "failures");
                long tf = numField(line, "testsFound");
                
                if (t != null) {
                    if ("PASS".equals(s) && f == 0 && tf > 0) {
                        keptGreen.add(t);
                    } else {
                        skippedRed.add(t);
                        String detail = tf == 0 ? "0 tests found / non-test class"
                                : ("status=" + s + (f > 0 ? ", " + f + " failure/error(s)" : ""));
                        System.out.println("[discover] SKIPPING RED TEST: " + t + " (" + detail + ")");
                    }
                }
            }
        } else {
            throw new IllegalStateException("mvn test discovery pass produced no output at " + traceOut);
        }

        Files.write(out, String.join("\n", keptGreen).getBytes(StandardCharsets.UTF_8));
        System.out.println(String.format("[discover] discovery complete: kept %d green test(s), skipped %d red test(s) -> %s",
                keptGreen.size(), skippedRed.size(), out));

        // Save skipped red tests to exclude.txt in base directory if any were found
        if (!skippedRed.isEmpty()) {
            Path exFile = outDir.resolve("exclude.txt");
            Set<String> allExcluded = new LinkedHashSet<>();
            if (Files.exists(exFile)) {
                for (String l : Files.readAllLines(exFile)) {
                    String s = l.trim();
                    if (!s.isEmpty()) allExcluded.add(s);
                }
            }
            allExcluded.addAll(skippedRed);
            Files.write(exFile, String.join("\n", allExcluded).getBytes(StandardCharsets.UTF_8));
            System.out.println("[discover] persisted " + skippedRed.size() + " skipped red test(s) to " + exFile);
        }
    }

    /**
     * Build the order runner the pipeline measures with. All measurement runs through REAL Maven
     * Surefire (the testorder fork) so timing + greenness match {@code mvn test}; {@code --surefire-ext}
     * (the changing-maven-extension jar) is required. Per-class alloc/jit/gc/JFR come from the
     * injected agent (csto2-agent.jar, auto-located beside csto2.jar). The old in-JVM TraceRunner
     * backend has been completely retired.
     */
    private static SurefireOrchestrator makeRunner(Map<String, String> a, Path outDir, Path self) throws Exception {
        return makeRunner(a, outDir, self, true);
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
    private static SurefireOrchestrator makeRunner(Map<String, String> a, Path outDir, Path self,
                                          boolean attachAgent) throws Exception {
        Path ext = a.containsKey("surefire-ext") && !a.get("surefire-ext").isBlank()
                ? Paths.get(a.get("surefire-ext")) : defaultSurefireExt();
        if (ext == null || !Files.exists(ext))
            throw new IllegalArgumentException("Surefire testorder fork not found in ~/.m2 — build & install it "
                    + "(`mvn install -DskipTests -Drat.skip -Denforcer.skip` in the maven-surefire fork), or pass "
                    + "--surefire-ext <surefire-changing-maven-extension jar>.");
        if (!a.containsKey("surefire-ext")) System.err.println("[csto2] surefire extension (auto): " + ext);
        Path workDir = resolveWorkDir(a);
        Path moduleDir = workDir != null ? workDir : Paths.get("").toAbsolutePath();
        SurefireOrchestrator s = new SurefireOrchestrator(moduleDir, outDir, ext, surefireMvnBin(a, moduleDir));
        Path jHome = resolveJavaHome(a);
        if (jHome != null) s.setJavaHome(jHome);
        if (a.containsKey("kp-argline")) s.setKpArgline(a.get("kp-argline"));
        if (a.containsKey("mvnopts")) {
            String opts = a.get("mvnopts");
            if (opts != null && !opts.isBlank()) {
                for (String opt : opts.trim().split("\\s+")) {
                    if (!opt.isEmpty()) s.addProp(opt);
                }
            }
        }
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
        Path testsFile = Paths.get(req(a, "tests"));
        int orders = Integer.parseInt(a.getOrDefault("orders", "6"));
        long seed = Long.parseLong(a.getOrDefault("seed", "1"));
        Path outDir = Paths.get(a.getOrDefault("out", ".csto2/trace"));
        List<String> tests = readTests(testsFile);
        Path self = Paths.get(Csto2.class.getProtectionDomain().getCodeSource().getLocation().toURI());

        long t0 = System.nanoTime();
        SurefireOrchestrator orch = makeRunner(a, outDir, self);
        Path traceOut = orch.run(tests, orders, seed);
        System.err.printf("[csto2] traced %d orders in %.1fs -> %s%n", orders, (System.nanoTime() - t0) / 1e9, traceOut);
    }


    private static void select(Map<String, String> a) throws Exception {
        Path testsFile = Paths.get(req(a, "tests"));
        Path tracePath = Paths.get(req(a, "trace"));
        int repeats = Integer.parseInt(a.getOrDefault("repeats", "4"));
        double heavyK = Double.parseDouble(a.getOrDefault("heavy-k", "3.0"));
        double heavyCap = Double.parseDouble(a.getOrDefault("heavy-cap", "0.15"));
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
        Map<String, List<String>> cands = Candidates.generate(tests, stats, tracePath, coldSlope, maxResid, heavyK, heavyCap);

        // Validation runner, agent OFF: the agent's recording/listener overhead would confound the very
        // wall-clock the ship gate decides on, and select reads only runtime+status (never agent facts).
        SurefireOrchestrator validate = makeRunner(a, outDir, self, false);

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
        // No pre-run green gate. Every class that failed during trace is already excluded from every
        // candidate order (trace-gate), so a failure HERE is a NEW failure -- a class that passed in trace
        // but fails now. We cannot retroactively drop it from the OTHER candidates' already-measured rounds
        // without a whole extra measurement pass, so a fair paired comparison of this candidate is
        // impossible. We therefore SCRAP the whole candidate (all rounds), not just this run -- including
        // 'initial': every surviving candidate must have the SAME round count for a fair paired test, and a
        // test that failed once is very likely to fail again, so its remaining rounds would be scrapped too.
        Map<String, String> excluded = new LinkedHashMap<>(); // strategy -> reason it was scrapped
        for (int r = 0; r < repeats; r++) {
            java.util.Collections.shuffle(names, shufRnd);
            for (String name : names) {
                if (excluded.containsKey(name)) continue;
                try {
                    validate.runOrder(outDir.resolve(name + ".order"), name + "#" + r, measure);
                } catch (com.csto2.surefire.OrderFailedException ex) {
                    String reason = ex.failedClasses().isEmpty()
                            ? "fork crashed (mvn exit " + ex.exitCode() + ")"
                            : "new failure - " + String.join(", ", ex.failedClasses());
                    excluded.put(name, reason);
                    System.err.println("[csto2] SCRAPPED candidate " + name + " (round " + r + "): " + reason
                            + " -- not seen in trace; whole candidate dropped from all rounds and the report"
                            + ("initial".equals(name) ? " (this was the baseline)" : ""));
                }
            }
            System.err.println("[csto2] measured round " + (r + 1) + "/" + repeats);

            // After two rounds, keep the top 3 candidates (excluding initial/naive) by combined
            // rounds-0+1 runtime and discard the rest. Two rounds instead of one: round 0 alone is
            // the noisiest (cold caches, slot luck) and a single-round rank is close to a coin flip
            // when candidates are within noise of each other.
            if (r == 1 && repeats > 2) {
                Map<String, Double> earlyRuntimes = new LinkedHashMap<>();
                if (Files.exists(measure)) {
                    for (String line : Files.readAllLines(measure)) {
                        line = line.trim(); if (line.isEmpty()) continue;
                        int oi = line.indexOf("\"orderId\":\"");
                        int ri = line.indexOf("\"runtimeMs\":");
                        if (oi < 0 || ri < 0) continue;
                        String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
                        int hash = oid.indexOf('#');
                        String name = hash < 0 ? oid : oid.substring(0, hash);
                        int round = hash < 0 ? 0 : Integer.parseInt(oid.substring(hash + 1));
                        if (round <= 1 && !excluded.containsKey(name) && !"initial".equals(name) && !"naive".equals(name)) {
                            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
                            earlyRuntimes.merge(name, rt, Double::sum);
                        }
                    }
                }

                // Sort candidates by combined rounds-0+1 runtime
                List<Map.Entry<String, Double>> sorted = new ArrayList<>(earlyRuntimes.entrySet());
                sorted.sort(Map.Entry.comparingByValue());

                // Select top 3
                java.util.Set<String> top3 = new java.util.HashSet<>();
                for (int i = 0; i < Math.min(3, sorted.size()); i++) {
                    top3.add(sorted.get(i).getKey());
                }

                // Discard all other candidates (except protected ones), and say by how much they missed
                double cutoff = top3.isEmpty() ? Double.NaN : sorted.get(Math.min(2, sorted.size() - 1)).getValue();
                for (String name : names) {
                    if (!"initial".equals(name) && !"naive".equals(name) && !top3.contains(name) && !excluded.containsKey(name)) {
                        Double total = earlyRuntimes.get(name);
                        String detail = (total == null || Double.isNaN(cutoff)) ? ""
                                : String.format(" (%.0fms over 2 rounds, top-3 cutoff %.0fms)", total, cutoff);
                        excluded.put(name, "discarded after 2 rounds (not in top 3)" + detail);
                        System.err.println("[csto2] DISCARDED candidate " + name
                                + ": not in top 3 after 2 rounds" + detail);
                    }
                }
            }
        }
        // Physically purge every scrapped/discarded candidate's rows from measure.jsonl so no report can credit its
        // partial (unequal-round) data. Reports then see only clean, equal-round candidates.
        if (!excluded.isEmpty()) {
            List<String> keep = new ArrayList<>();
            for (String line : Files.readAllLines(measure)) {
                int oi = line.indexOf("\"orderId\":\"");
                if (oi < 0) { keep.add(line); continue; }
                String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
                String nm = oid.contains("#") ? oid.substring(0, oid.indexOf('#')) : oid;
                if (!excluded.containsKey(nm)) keep.add(line);
            }
            Files.write(measure, String.join("\n", keep).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            System.err.println("[csto2] excluded " + excluded.size() + " candidate(s): "
                    + String.join(", ", excluded.keySet()));
        }
        java.io.PrintStream originalOut = System.out;
        Path reportFile = outDir.resolve("select-report.log");
        try (java.io.OutputStream fos = Files.newOutputStream(reportFile)) {
            TeePrintStream tee = new TeePrintStream(fos, originalOut);
            System.setOut(tee);
            selectReport(measure, "initial", excluded.keySet());
            if (!excluded.isEmpty()) {
                System.out.println("\n=== EXCLUDED (failed early, not measured/reported) ===");
                for (Map.Entry<String, String> e : excluded.entrySet())
                    System.out.printf("  %-22s %s%n", e.getKey(), e.getValue());
            }
        } finally {
            System.setOut(originalOut);
        }
    }

    /** Report medians + greenness per candidate; SHIP only a fully-green order (incumbent fallback). */
    private static void selectReport(Path measure, String incumbent) throws Exception {
        selectReport(measure, incumbent, java.util.Set.of());
    }

    private static void selectReport(Path measure, String incumbent, java.util.Set<String> excluded) throws Exception {
        Map<String, List<Double>> perRun = new LinkedHashMap<>();
        Map<String, Integer> runNonPass = new LinkedHashMap<>(); // per run id: count of FAIL/TIMEOUT/MISSING
        Map<String, java.util.Set<String>> runTests = new LinkedHashMap<>(); // per run id: classes that reported
        java.util.Set<String> allTests = new java.util.LinkedHashSet<>();    // full suite = union across all runs
        for (String line : Files.readAllLines(measure)) {
            line = line.trim(); if (line.isEmpty()) continue;
            int oi = line.indexOf("\"orderId\":\""); int ri = line.indexOf("\"runtimeMs\":");
            if (oi < 0 || ri < 0) continue;
            String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
            // Skip rows belonging to a strategy that already failed early -- it is excluded from the report.
            String cand = oid.contains("#") ? oid.substring(0, oid.indexOf('#')) : oid;
            if (excluded.contains(cand)) continue;
            double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
            perRun.computeIfAbsent(oid, k -> new ArrayList<>()).add(rt);
            int si = line.indexOf("\"status\":\"");
            if (si >= 0) {
                String st = line.substring(si + 10, line.indexOf('"', si + 10));
                if (!"PASS".equals(st)) runNonPass.merge(oid, 1, Integer::sum);
            }
            int ti = line.indexOf("\"test\":\"");
            if (ti >= 0) {
                String test = line.substring(ti + 8, line.indexOf('"', ti + 8));
                runTests.computeIfAbsent(oid, k -> new java.util.HashSet<>()).add(test);
                allTests.add(test);
            }
        }
        // Coverage guard (defense in depth over runOrder's MISSING sentinels): even if measure.jsonl came
        // from an older/hand-edited run without sentinels, any run that reported fewer than the full suite
        // of classes crashed mid-way -- its summed runtime is a partial (fake) total. Count each missing
        // class as non-green so the incomplete candidate is disqualified rather than shipped as a speedup.
        for (Map.Entry<String, java.util.Set<String>> e : runTests.entrySet()) {
            int miss = allTests.size() - e.getValue().size();
            if (miss > 0) runNonPass.merge(e.getKey(), miss, Integer::sum);
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
            double m = v.size() % 2 == 1 ? v.get(v.size() / 2) : (v.get(v.size() / 2 - 1) + v.get(v.size() / 2)) / 2.0;
            med.put(e.getKey(), m);
            int np = candNonPass.getOrDefault(e.getKey(), 0);
            System.out.printf("  %-22s runs=%d median=%.0fms min=%.0fms max=%.0fms  %s%n",
                    e.getKey(), v.size(), m, v.get(0), v.get(v.size() - 1),
                    np == 0 ? "GREEN" : ("NOT-GREEN (" + np + " non-pass)"));
        }
        double base = med.getOrDefault(incumbent, Double.NaN);
        if (Double.isNaN(base)) {
            System.out.println("\n=> baseline '" + incumbent + "' was scrapped for a new failure during select"
                    + " -- no green baseline to rank against; nothing shipped.");
            return;
        }
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
        java.io.PrintStream originalOut = System.out;
        Path reportFile = measure.getParent().resolve("select-report.log");
        try (java.io.OutputStream fos = Files.newOutputStream(reportFile, java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND)) {
            TeePrintStream tee = new TeePrintStream(fos, originalOut);
            System.setOut(tee);

            // roundTotal[candidate][roundIdx] = summed runtimeMs; nonPass[candidate] = total non-PASS rows.
            Map<String, Map<Integer, Double>> roundTotal = new LinkedHashMap<>();
            Map<String, Integer> nonPass = new LinkedHashMap<>();
            Map<String, java.util.Set<String>> runTests = new LinkedHashMap<>(); // orderId -> classes reported
            java.util.Set<String> allTests = new java.util.LinkedHashSet<>();     // full suite = union across runs
            Map<String, String> oidName = new LinkedHashMap<>();
            for (String line : Files.readAllLines(measure)) {
                line = line.trim(); if (line.isEmpty()) continue;
                int oi = line.indexOf("\"orderId\":\""); int ri = line.indexOf("\"runtimeMs\":");
                if (oi < 0 || ri < 0) continue;
                String oid = line.substring(oi + 11, line.indexOf('"', oi + 11));
                int hash = oid.indexOf('#');
                String name = hash < 0 ? oid : oid.substring(0, hash);
                oidName.put(oid, name);
                int round = hash < 0 ? 0 : Integer.parseInt(oid.substring(hash + 1));
                double rt = Double.parseDouble(line.substring(ri + 12, findEnd(line, ri + 12)));
                roundTotal.computeIfAbsent(name, k -> new LinkedHashMap<>()).merge(round, rt, Double::sum);
                int si = line.indexOf("\"status\":\"");
                if (si >= 0 && !"PASS".equals(line.substring(si + 10, line.indexOf('"', si + 10))))
                    nonPass.merge(name, 1, Integer::sum);
                int ti = line.indexOf("\"test\":\"");
                if (ti >= 0) {
                    String test = line.substring(ti + 8, line.indexOf('"', ti + 8));
                    runTests.computeIfAbsent(oid, k -> new java.util.HashSet<>()).add(test);
                    allTests.add(test);
                }
            }
            // Coverage guard: a run reporting fewer than the full suite crashed mid-way (partial total) -- treat
            // the candidate as non-green so it is skipped, never credited with a fake per-round speedup.
            for (Map.Entry<String, java.util.Set<String>> e : runTests.entrySet())
                if (allTests.size() - e.getValue().size() > 0)
                    nonPass.merge(oidName.get(e.getKey()), allTests.size() - e.getValue().size(), Integer::sum);
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
        } finally {
            System.setOut(originalOut);
        }
    }

    private static double median(double[] v) {
        double[] s = v.clone(); Arrays.sort(s);
        int n = s.length;
        return n % 2 == 1 ? s[n / 2] : (s[n / 2 - 1] + s[n / 2]) / 2.0;
    }


    private static int findEnd(String s, int from) {
        int i = from;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        return i;
    }

    private static String strField(String json, String key) {
        String needle = "\"" + key + "\":\"";
        int i = json.indexOf(needle);
        if (i < 0) return null;
        i += needle.length();
        int j = json.indexOf('"', i);
        return j < 0 ? null : json.substring(i, j);
    }

    private static long numField(String json, String key) {
        String needle = "\"" + key + "\":";
        int i = json.indexOf(needle);
        if (i < 0) return 0;
        i += needle.length();
        int j = i;
        while (j < json.length() && "+-0123456789".indexOf(json.charAt(j)) >= 0) j++;
        try { return Long.parseLong(json.substring(i, j)); } catch (RuntimeException e) { return 0; }
    }

    private static Path resolveWorkDir(Map<String, String> a) {
        String wd = a.get("workdir");
        if (wd != null && !wd.isBlank()) return Paths.get(wd);
        return null;
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
        return Arrays.stream(v.trim().split("\\s+")).filter(s -> !s.isEmpty()).collect(Collectors.toList());
    }

    private static List<String> readTests(Path testsFile) throws Exception {
        return Files.readAllLines(testsFile).stream()
                .map(String::trim).filter(s -> !s.isEmpty() && !s.startsWith("#")).collect(Collectors.toList());
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
        System.out.println(
                "CSTO v2\n" +
                "\n" +
                "Stage Commands:\n" +
                "  discover --tests <file> --out <file> [--workdir <dir>]\n" +
                "      Filter the test list to runnable classes (runs mvn test once, skipping and reporting red tests).\n" +
                "  trace --tests <file> [--orders N] [--seed S] [--out <dir>]\n" +
                "      Run N random test orders through Surefire to collect execution facts.\n" +
                "  select --tests <file> --trace <file> [--repeats R] [--out <dir>]\n" +
                "      Measure candidate strategies and select the fastest green order.\n" +
                "\n" +
                "Orchestration Commands (Parity with REPL):\n" +
                "  project [--dir <dir>] [--out <dir>]\n" +
                "      Autodetect classpath + test list + workdir from a Maven project.\n" +
                "  configure [--tests ...] [--out ...] [--jvmargs ...] ...\n" +
                "      Configure and persist settings in config.properties.\n" +
                "  state [--out <dir>]\n" +
                "      Show current config, persisted exclusions, and candidate settings.\n" +
                "  exclude <classes> | --exclude <classes> [--out <dir>]\n" +
                "      Exclude test classes from the test list.\n" +
                "  approaches <toggles> | --toggle <toggles> [--out <dir>]\n" +
                "      Enable/disable candidate optimization strategies.\n" +
                "  pipeline [--out <dir>]\n" +
                "      Run the full pipeline: discover -> trace -> select.\n" +
                "  scientific [--out <dir>]\n" +
                "      Run the pipeline at repeats=10 + Wilcoxon signed-rank report.\n"
        );
    }

    private static class TeePrintStream extends java.io.PrintStream {
        private final java.io.PrintStream branch;
        public TeePrintStream(java.io.OutputStream out, java.io.PrintStream branch) {
            super(out, true);
            this.branch = branch;
        }
        @Override
        public void write(int b) {
            super.write(b);
            branch.write(b);
        }
        @Override
        public void write(byte[] buf, int off, int len) {
            super.write(buf, off, len);
            branch.write(buf, off, len);
        }
        @Override
        public void flush() {
            super.flush();
            branch.flush();
        }
    }
}
