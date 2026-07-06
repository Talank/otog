package com.csto2.cli;

import com.csto2.Csto2;
import com.csto2.optimize.Candidates;
import com.csto2.surefire.SurefireTestFilter;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Shared orchestration logic for CSTO v2. Handles running the individual pipeline stages
 * and combined pipelines, managing the shared configuration state, and persisting settings.
 * Designed to be driven by both the interactive Repl and the headless CLI.
 */
public final class Orchestrator {

    public interface Confirmer {
        boolean confirm(String message) throws IOException;
    }

    /** Shared flag values, keyed exactly like the CLI flags (cp, app, lib, tests, jvmargs, ...). */
    public final Map<String, String> cfg = new LinkedHashMap<>();

    /** Config keys offered by the 'configure' screen, with a one-line hint each. */
    public static final String[][] CONFIG_KEYS = {
        {"cp", "target test+runtime classpath (discover/trace/select/validate)"},
        {"app", "app classes classpath (analyze only)"},
        {"lib", "library classpath, optional (analyze only)"},
        {"tests", "file of fully-qualified test class names, one per line"},
        {"out", "base output dir (default .csto2)"},
        {"jvmargs", "extra child-JVM args as ONE value, e.g. \"--add-opens ... -Dfoo=bar\""},
        {"java", "JAVA_HOME or path to java for child JVMs (optional)"},
        {"workdir", "child-JVM working dir if tests use relative resource paths (optional)"},
        {"orders", "trace: number of orders to run (default 6)"},
        {"seed", "trace: shuffle seed (default 1)"},
        {"repeats", "measurement rounds for select/validate (lower = faster, noisier; select default 4)"},
        {"surefire-ext", "testorder-fork extension jar (optional; auto-located from ~/.m2 when blank)"},
        {"mvn", "mvn binary/wrapper for the Surefire runner (optional; default ./mvnw or mvn)"},
        {"heavy-k", "robust deviations (log mean+k*stddev) above which a class counts as heavy (default 3.0)"},
        {"heavy-cap", "max fraction of the suite a heavy-outlier move may relocate (default 0.15)"},
    };

    /** Output base dir, always ABSOLUTE. */
    public Path baseDir() {
        return Paths.get(cfg.getOrDefault("out", ".csto2")).toAbsolutePath();
    }

    // ---- config persistence ----------------------------------------------------------------------

    /** Load configuration from baseDir()/config.properties if present. */
    public void loadConfig() throws IOException {
        Path path = baseDir().resolve("config.properties");
        if (Files.exists(path)) {
            java.util.Properties props = new java.util.Properties();
            try (java.io.Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                props.load(reader);
            }
            for (String key : props.stringPropertyNames()) {
                cfg.put(key, props.getProperty(key));
            }
        }
    }

    /** Save configuration to baseDir()/config.properties. */
    public void saveConfig() throws IOException {
        Files.createDirectories(baseDir());
        Path path = baseDir().resolve("config.properties");
        java.util.Properties props = new java.util.Properties();
        for (Map.Entry<String, String> e : cfg.entrySet()) {
            if (e.getValue() != null) {
                props.setProperty(e.getKey(), e.getValue());
            }
        }
        try (java.io.Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            props.store(writer, "CSTO v2 Configuration");
        }
    }

    public void configure(Map<String, String> kv) throws IOException {
        for (Map.Entry<String, String> e : kv.entrySet()) {
            String key = e.getKey();
            String val = e.getValue();
            boolean valid = false;
            for (String[] k : CONFIG_KEYS) {
                if (k[0].equals(key)) { valid = true; break; }
            }
            if (key.equals("facts") || key.equals("trace") || key.equals("exclude") || key.equals("skip-candidates")) {
                valid = true;
            }
            if (valid) {
                if (val == null || val.isBlank()) {
                    cfg.remove(key);
                } else {
                    cfg.put(key, val.trim());
                }
            }
        }
        saveConfig();
    }

    // ---- stages ----------------------------------------------------------------------------------

    public void discover() throws Exception {
        require("cp"); require("tests");
        Path runnable = baseDir().resolve("tests.runnable");
        Map<String, String> a = args("cp", "jvmargs", "java", "workdir");
        a.put("tests", cfg.get("tests"));
        a.put("out", runnable.toString());
        Csto2.dispatch("discover", a);
        cfg.put("tests", runnable.toString());
        System.out.println("[wired] tests -> " + runnable);
        loadPersistedExclusions();   // re-apply persisted test-class exclusions to the fresh list
    }

    public void analyze() throws Exception {
        require("app"); require("tests");
        Path outDir = baseDir().resolve("comprehension");
        Map<String, String> a = args("app", "lib");
        a.put("tests", cfg.get("tests"));
        a.put("out", outDir.toString());
        Csto2.dispatch("analyze", a);
        Path facts = outDir.resolve("static-facts.jsonl");
        cfg.put("facts", facts.toString());
        System.out.println("[wired] facts -> " + facts);
    }

    public void trace() throws Exception {
        require("cp"); require("tests");
        Path outDir = baseDir().resolve("trace");
        Path traceJsonl = outDir.resolve("trace.jsonl");
        Map<String, String> a = args("cp", "jvmargs", "java", "workdir", "orders", "seed", "surefire-ext", "mvn", "kp-argline");
        a.put("tests", cfg.get("tests"));
        a.put("out", outDir.toString());
        Csto2.dispatch("trace", a);
        if (!Files.exists(traceJsonl) || Files.readAllLines(traceJsonl).stream().noneMatch(l -> !l.isBlank())) {
            cfg.remove("trace");
            System.out.println("[error] trace produced no rows — every order's Surefire run failed (no reports).");
            printFirstLogError(outDir.resolve("logs"));
            throw new IllegalStateException("trace produced no rows (see " + outDir.resolve("logs") + ")");
        }
        cfg.put("trace", traceJsonl.toString());
        System.out.println("[wired] trace -> " + cfg.get("trace"));
        warnNonGreen(traceJsonl);
    }

    public void select() throws Exception {
        require("cp"); require("tests"); requireFile("trace");
        Map<String, String> a = args("cp", "trace", "jvmargs", "java", "workdir", "repeats", "surefire-ext", "mvn", "kp-argline", "skip-candidates", "heavy-k", "heavy-cap");
        a.put("tests", cfg.get("tests"));
        a.put("out", baseDir().resolve("select").toString());
        Csto2.dispatch("select", a);
    }

    public void validate() throws Exception {
        require("cp"); require("tests"); requireFile("trace");
        Map<String, String> a = args("cp", "trace", "jvmargs", "java", "workdir", "repeats", "surefire-ext", "mvn", "kp-argline");
        a.put("tests", cfg.get("tests"));
        a.put("out", baseDir().resolve("validate").toString());
        Csto2.dispatch("validate", a);
    }

    public void fullPipeline() throws Exception {
        System.out.println("[pipeline] discover -> trace -> select");
        discover();
        trace();
        select();
        System.out.println("[pipeline] done.");
    }

    public void scientific() throws Exception {
        System.out.println("[scientific] discover -> trace -> select (repeats=10) + Wilcoxon signed-rank");
        String prevRepeats = cfg.get("repeats");
        cfg.put("repeats", "10");
        try {
            discover();
            trace();
            select();
        } finally {
            if (prevRepeats == null) cfg.remove("repeats"); else cfg.put("repeats", prevRepeats);
        }
        Path measure = baseDir().resolve("select").resolve("measure.jsonl");
        if (Files.exists(measure)) Csto2.signedRankReport(measure, "initial");
        else System.out.println("[scientific] no measure.jsonl at " + measure + " — select produced no measurements.");
        System.out.println("[scientific] done.");
    }

    // ---- exclude -------------------------------------------------------------------------------

    public void exclude(List<String> tokens) throws Exception {
        requireFile("tests");
        Path testsFile = Paths.get(cfg.get("tests"));
        List<String> current = new ArrayList<>();
        for (String line : Files.readAllLines(testsFile)) {
            String t = line.trim();
            if (!t.isEmpty()) current.add(t);
        }
        if (current.isEmpty()) {
            throw new IllegalStateException("current test list is empty: " + testsFile);
        }

        if (tokens == null || tokens.isEmpty()) {
            throw new IllegalArgumentException("No classes to exclude specified.");
        }

        // Resolve every token before changing anything — any failure aborts the whole operation.
        Set<String> toRemove = new LinkedHashSet<>();
        List<String> problems = new ArrayList<>();
        for (String tok : tokens) {
            if (tok.isEmpty()) continue;
            List<String> matches = matchTests(tok, current);
            if (matches.isEmpty()) {
                String hint = nearMisses(tok, current);
                problems.add("not found: " + tok + (hint.isEmpty() ? "" : "  (did you mean: " + hint + "?)"));
            } else if (matches.size() > 1) {
                problems.add("ambiguous: " + tok + " matches " + matches.size() + " classes: " + String.join(", ", matches));
            } else {
                toRemove.add(matches.get(0));
            }
        }
        if (!problems.isEmpty()) {
            StringBuilder sb = new StringBuilder("exclude rejected — nothing changed. Fix these and retry:\n");
            for (String p : problems) sb.append("   ").append(p).append("\n");
            throw new IllegalArgumentException(sb.toString());
        }

        List<String> kept = new ArrayList<>();
        for (String t : current) if (!toRemove.contains(t)) kept.add(t);

        Files.createDirectories(baseDir());
        Path included = baseDir().resolve("tests.included").toAbsolutePath();
        Files.write(included, String.join("\n", kept).getBytes(StandardCharsets.UTF_8));
        cfg.put("tests", included.toString());

        // Accumulate resolved exclusions in config (session-persistent, deduped).
        Set<String> allExcluded = new LinkedHashSet<>();
        String prev = cfg.get("exclude");
        if (prev != null && !prev.isBlank())
            for (String e : prev.split(",")) if (!e.isBlank()) allExcluded.add(e.trim());
        allExcluded.addAll(toRemove);
        cfg.put("exclude", String.join(",", allExcluded));
        saveExclusions(allExcluded);   // persist to <out>/exclude.txt so it survives across launches

        System.out.println("[exclude] removed " + toRemove.size() + ": "
                + toRemove.stream().map(Orchestrator::simple).collect(Collectors.joining(", ")));
        System.out.println("[wired] tests -> " + included + "  (" + kept.size() + " classes remain)");
    }

    /** Resolve a typed name to test classes: exact FQN match if any, else simple-name match(es). */
    private static List<String> matchTests(String token, List<String> tests) {
        List<String> out = new ArrayList<>();
        for (String t : tests) if (t.equals(token)) out.add(t);
        if (!out.isEmpty()) return out;                  // an exact FQN match wins outright
        for (String t : tests) if (simple(t).equals(token)) out.add(t);
        return out;
    }

    /** Suggest up to 3 list entries whose simple name contains the token (case-insensitive). */
    private static String nearMisses(String token, List<String> tests) {
        String lc = token.toLowerCase();
        List<String> hits = new ArrayList<>();
        for (String t : tests) {
            if (simple(t).toLowerCase().contains(lc)) {
                hits.add(simple(t));
                if (hits.size() == 3) break;
            }
        }
        return String.join(", ", hits);
    }

    // ---- approaches ----------------------------------------------------------------------------

    public void approaches(List<String> toggles) throws Exception {
        Set<String> disabled = disabledApproaches();
        if (toggles == null || toggles.isEmpty()) {
            printApproachesState(disabled);
            return;
        }

        for (String tok : toggles) {
            if (tok.isEmpty()) continue;
            if (!Candidates.ALL_NAMES.contains(tok)) {
                System.out.println("   unknown approach: " + tok);
            } else if (Candidates.PROTECTED_NAMES.contains(tok)) {
                System.out.println("   cannot disable (protected): " + tok);
            } else if (disabled.remove(tok)) {
                System.out.println("   enabled:  " + tok);
            } else {
                disabled.add(tok);
                System.out.println("   disabled: " + tok);
            }
        }
        if (disabled.isEmpty()) cfg.remove("skip-candidates");
        else cfg.put("skip-candidates", String.join(",", disabled));
        saveSkipCandidates(disabled);   // persist to <out>/skip-candidates.txt

        printApproachesState(disabled);
    }

    public void printApproachesState(Set<String> disabled) {
        System.out.println();
        System.out.println("--- candidate approaches (used by 'select') ---");
        for (String name : Candidates.ALL_NAMES) {
            boolean prot = Candidates.PROTECTED_NAMES.contains(name);
            boolean on = prot || !disabled.contains(name);
            System.out.printf("  [%s] %-26s%s%n", on ? "on " : "off", name, prot ? " (protected)" : "");
        }
        System.out.println(disabled.isEmpty()
                ? "[approaches] all enabled."
                : "[approaches] disabled: " + String.join(", ", disabled));
    }

    /** The current set of disabled candidate strategies (a fresh mutable copy from config). */
    public Set<String> disabledApproaches() {
        Set<String> out = new LinkedHashSet<>();
        String v = cfg.get("skip-candidates");
        if (v != null) for (String s : v.split("[,\\s]+")) if (!s.isBlank()) out.add(s.trim());
        return out;
    }

    // ---- persisted exclusions ------------------------------------------------------------------

    public Path excludeFile()        { return baseDir().resolve("exclude.txt"); }
    public Path skipCandidatesFile() { return baseDir().resolve("skip-candidates.txt"); }

    /** Write the full deduped set of excluded test-class FQCNs to {@code <out>/exclude.txt}. */
    public void saveExclusions(Set<String> excluded) throws IOException {
        Files.createDirectories(baseDir());
        Files.write(excludeFile(), String.join("\n", excluded).getBytes(StandardCharsets.UTF_8));
    }

    /** Write the disabled candidate strategies to {@code <out>/skip-candidates.txt} (delete when empty). */
    public void saveSkipCandidates(Set<String> disabled) throws IOException {
        if (disabled.isEmpty()) { Files.deleteIfExists(skipCandidatesFile()); return; }
        Files.createDirectories(baseDir());
        Files.write(skipCandidatesFile(), String.join("\n", disabled).getBytes(StandardCharsets.UTF_8));
    }

    /** Restore exclusions persisted by a previous session. */
    public void loadPersistedExclusions() throws IOException {
        Path skipFile = skipCandidatesFile();
        if (Files.exists(skipFile)) {
            Set<String> disabled = new LinkedHashSet<>();
            for (String line : Files.readAllLines(skipFile)) {
                String s = line.trim();
                if (s.isEmpty() || Candidates.PROTECTED_NAMES.contains(s) || !Candidates.ALL_NAMES.contains(s)) continue;
                disabled.add(s);
            }
            if (disabled.isEmpty()) cfg.remove("skip-candidates");
            else {
                cfg.put("skip-candidates", String.join(",", disabled));
                System.out.println("[persist] loaded " + disabled.size() + " disabled approach(es) from " + skipFile);
            }
        }

        Path exFile = excludeFile();
        String testsPath = cfg.get("tests");
        if (!Files.exists(exFile) || testsPath == null) return;
        Path testsFile = Paths.get(testsPath);
        if (!Files.exists(testsFile)) return;

        Set<String> wanted = new LinkedHashSet<>();
        for (String line : Files.readAllLines(exFile)) { String t = line.trim(); if (!t.isEmpty()) wanted.add(t); }
        if (wanted.isEmpty()) return;

        List<String> kept = new ArrayList<>();
        Set<String> applied = new LinkedHashSet<>();
        for (String line : Files.readAllLines(testsFile)) {
            String t = line.trim();
            if (t.isEmpty()) continue;
            if (wanted.contains(t)) applied.add(t); else kept.add(t);
        }
        if (applied.isEmpty()) return;   // nothing in the current list matched; leave tests untouched

        Files.createDirectories(baseDir());
        Path included = baseDir().resolve("tests.included").toAbsolutePath();
        Files.write(included, String.join("\n", kept).getBytes(StandardCharsets.UTF_8));
        cfg.put("tests", included.toString());
        cfg.put("exclude", String.join(",", applied));
        System.out.println("[persist] re-applied " + applied.size() + " test-class exclusion(s) from " + exFile
                + " -> " + included + "  (" + kept.size() + " classes remain)");
    }

    // ---- project autodetect ----------------------------------------------------------------------

    public void loadProject(Path dir, Confirmer confirmer) throws Exception {
        if (!Files.exists(dir.resolve("pom.xml")))
            throw new IllegalStateException("no pom.xml at " + dir.toAbsolutePath() + " (Maven projects only)");
        Path classes = dir.resolve("target/classes");
        Path testClasses = dir.resolve("target/test-classes");
        String mvn = mvnBin(dir);

        if (!Files.isDirectory(testClasses)) {
            boolean shouldCompile = confirmer.confirm("target/test-classes missing — run '" + mvn + " test-compile' now? (Y/n)");
            // -Dmaven.build.cache.enabled=false: the Maven build-cache extension (e.g. Avro) reports
            // BUILD SUCCESS by restoring from cache and SKIPS compiler:testCompile, so target/ is never
            // written to disk. Disabling it forces a real compile that materializes target/test-classes.
            if (shouldCompile)
                runMvn(dir, mvn, "-q", "-Dmaven.build.cache.enabled=false", "test-compile");
        }
        if (!Files.isDirectory(testClasses))
            throw new IllegalStateException("still no target/test-classes after test-compile — compile the "
                    + "project manually (a build-cache extension may be skipping it; try "
                    + "'mvn -Dmaven.build.cache.enabled=false test-compile')");

        // Resolve the dependency classpath into a file, then prepend the project's own output dirs.
        Files.createDirectories(baseDir());
        Path depCp = baseDir().resolve("deps.classpath").toAbsolutePath();
        System.out.println("[project] resolving dependency classpath (mvn)...");
        runMvn(dir, mvn, "-q", "-Dmaven.build.cache.enabled=false", "dependency:build-classpath", "-Dmdep.outputFile=" + depCp);
        String deps = Files.exists(depCp) ? Files.readString(depCp).trim() : "";
        StringBuilder cp = new StringBuilder();
        cp.append(testClasses.toAbsolutePath());
        if (Files.isDirectory(classes)) cp.append(File.pathSeparator).append(classes.toAbsolutePath());
        if (!deps.isEmpty()) cp.append(File.pathSeparator).append(deps);
        String fullCp = ensureJUnitLauncher(cp.toString(), dir, mvn);
        cfg.put("cp", fullCp);

        // Candidate test list: top-level .class files under target/test-classes that Surefire would
        // select per the module pom's <includes>/<excludes> (or Surefire's defaults when it sets none),
        // so the candidate set matches what 'mvn test' runs rather than every compiled helper class.
        SurefireTestFilter filter = SurefireTestFilter.fromPom(dir.resolve("pom.xml"));
        List<String> names = new ArrayList<>();
        int[] dropped = {0};
        try (Stream<Path> s = Files.walk(testClasses)) {
            s.filter(f -> f.toString().endsWith(".class"))
             .map(f -> testClasses.relativize(f).toString().replace(File.separatorChar, '/'))
             .filter(rel -> !rel.contains("$"))            // skip inner/anonymous classes
             .sorted()
             .forEach(rel -> {
                 if (filter.matches(rel))
                     names.add(rel.substring(0, rel.length() - ".class".length()).replace('/', '.'));
                 else
                     dropped[0]++;
             });
        }
        Path testsFile = baseDir().resolve("tests.all").toAbsolutePath();
        Files.write(testsFile, String.join("\n", names).getBytes(StandardCharsets.UTF_8));
        cfg.put("tests", testsFile.toString());
        cfg.put("workdir", dir.toAbsolutePath().toString());

        System.out.printf("[project] %s%n", dir.toAbsolutePath());
        System.out.printf("[project]   cp:    %d entries%n", fullCp.split(File.pathSeparator).length);
        System.out.printf("[project]   surefire selectors: %d include(s) (%s), %d exclude(s)%n",
                filter.includeGlobs.size(), filter.usedDefaultIncludes ? "surefire defaults" : "pom",
                filter.excludeGlobs.size());
        System.out.printf("[project]   tests: %d candidate classes (%d dropped by surefire selectors) -> %s%n",
                names.size(), dropped[0], testsFile);
        System.out.printf("[project]   workdir: %s%n", dir.toAbsolutePath());
        System.out.println("[project] next: run 'discover' to filter to runnable tests, then 'full pipeline'.");
    }

    private String ensureJUnitLauncher(String cp, Path dir, String mvn) throws Exception {
        if (cp.contains("junit-platform-launcher")) return cp;
        String anchor = null;
        for (String e : cp.split(File.pathSeparator)) {
            if (e.contains("junit-platform-commons")) { anchor = e; break; }
            if (anchor == null && e.contains("junit-platform-engine")) anchor = e;
        }
        if (anchor == null) return cp;
        Path launcher = Paths.get(anchor.replace("junit-platform-commons", "junit-platform-launcher")
                                        .replace("junit-platform-engine", "junit-platform-launcher"));
        if (!Files.exists(launcher)) {
            String fn = launcher.getFileName().toString();
            String ver = fn.substring("junit-platform-launcher-".length(), fn.length() - ".jar".length());
            System.out.println("[project] fetching junit-platform-launcher:" + ver + " (Surefire-provided, not a project dep)...");
            try { runMvn(dir, mvn, "-q", "dependency:get", "-Dartifact=org.junit.platform:junit-platform-launcher:" + ver); }
            catch (Throwable t) { System.out.println("[warn] could not fetch junit-platform-launcher: " + t); }
        }
        if (Files.exists(launcher)) {
            System.out.println("[project]   +junit-platform-launcher");
            return cp + File.pathSeparator + launcher.toAbsolutePath();
        }
        System.out.println("[warn] junit-platform-launcher not on classpath; JUnit 5 trace runs will fail to find a runner.");
        return cp;
    }

    private static String mvnBin(Path dir) {
        boolean win = System.getProperty("os.name", "").toLowerCase().contains("win");
        Path wrapper = dir.resolve(win ? "mvnw.cmd" : "mvnw");
        return Files.isExecutable(wrapper) ? wrapper.toAbsolutePath().toString() : "mvn";
    }

    private static void runMvn(Path dir, String... cmd) throws Exception {
        ProcessBuilder pb = new ProcessBuilder(cmd).directory(dir.toFile()).inheritIO();
        int code = pb.start().waitFor();
        if (code != 0) throw new IllegalStateException(cmd[0] + " exited " + code + " in " + dir);
    }

    // ---- helpers ---------------------------------------------------------------------------------

    private Map<String, String> args(String... keys) {
        Map<String, String> a = new LinkedHashMap<>();
        for (String k : keys) {
            String v = cfg.get(k);
            if (v != null && !v.isBlank()) a.put(k, v);
        }
        return a;
    }

    private void require(String key) throws IOException {
        String v = cfg.get(key);
        if (v == null || v.isBlank()) {
            throw new IllegalStateException("missing required configuration: " + key);
        }
    }

    private void requireFile(String key) throws IOException {
        require(key);
        Path p = Paths.get(cfg.get(key));
        if (!Files.exists(p)) {
            throw new IllegalStateException(key + " file not found: " + p
                    + (key.equals("trace") ? " — run 'trace' first" : key.equals("facts") ? " — run 'analyze' first" : ""));
        }
    }

    private void warnNonGreen(Path traceJsonl) throws IOException {
        Map<String, String> nonGreen = new LinkedHashMap<>();
        int rows = 0;
        for (String line : Files.readAllLines(traceJsonl)) {
            line = line.trim();
            if (line.isEmpty()) continue;
            rows++;
            String status = strField(line, "status");
            String test = strField(line, "test");
            if (test != null && status != null && !status.equals("PASS")) nonGreen.putIfAbsent(test, status);
        }
        if (nonGreen.isEmpty()) {
            System.out.println("[trace] all classes green across all orders (" + rows + " rows).");
            return;
        }
        System.out.println("[warn] " + nonGreen.size() + " class(es) NOT green — selection can only ship an order "
                + "in which these are green, so they cap the achievable speedup:");
        for (Map.Entry<String, String> e : nonGreen.entrySet())
            System.out.printf("   %-8s %s%n", e.getValue(), simple(e.getKey()));
    }

    private void printFirstLogError(Path logDir) {
        try (Stream<Path> s = Files.list(logDir)) {
            Path log = s.filter(p -> p.toString().endsWith(".log")).findFirst().orElse(null);
            if (log == null) return;
            String firstErr = null;
            for (String line : Files.readAllLines(log)) {
                String t = line.trim();
                if (t.contains("Caused by:") || t.contains("BUILD FAILURE")
                        || (t.startsWith("[ERROR]") && t.length() > 8 && !t.contains("\tat "))) {
                    firstErr = t;
                    break;
                }
                if (firstErr == null && (t.contains("Exception") || t.contains("ClassNotFound")))
                    firstErr = t;
            }
            if (firstErr != null) System.out.println("   " + log.getFileName() + ": " + firstErr);
        } catch (IOException ignored) {}
    }

    private static String strField(String json, String key) {
        String needle = "\"" + key + "\":\"";
        int i = json.indexOf(needle);
        if (i < 0) return null;
        i += needle.length();
        int j = json.indexOf('"', i);
        return j < 0 ? null : json.substring(i, j);
    }

    public static String simple(String fqn) {
        int i = fqn.lastIndexOf('.');
        return i < 0 ? fqn : fqn.substring(i + 1);
    }

    public void state() {
        System.out.println("--- config ---");
        for (String[] k : CONFIG_KEYS) {
            String v = cfg.get(k[0]);
            if (v != null) System.out.printf("  %-9s = %s%n", k[0], v);
        }
        System.out.println("--- wired artifacts ---");
        for (String k : new String[]{"facts", "trace"}) {
            if (cfg.containsKey(k)) System.out.printf("  %-9s = %s%n", k, cfg.get(k));
        }
        String excluded = cfg.get("exclude");
        if (excluded != null && !excluded.isBlank()) {
            String[] ex = excluded.split(",");
            System.out.printf("  %-9s = %d class(es): %s%s%n", "exclude", ex.length,
                    Stream.of(ex).map(Orchestrator::simple).collect(Collectors.joining(", ")),
                    Files.exists(excludeFile()) ? "  (persisted)" : "");
        }
        Set<String> disabled = disabledApproaches();
        if (!disabled.isEmpty())
            System.out.printf("  %-9s = %d disabled: %s%s%n", "approaches", disabled.size(),
                    String.join(", ", disabled), Files.exists(skipCandidatesFile()) ? "  (persisted)" : "");
        System.out.println("  base out  = " + baseDir());
        reportRunnerStatus();
    }

    public void reportRunnerStatus() {
        Path ext = cfg.containsKey("surefire-ext") ? Paths.get(cfg.get("surefire-ext")) : Csto2.defaultSurefireExt();
        if (ext != null && Files.exists(ext)) {
            System.out.println("[surefire] testorder fork: " + ext);
        } else {
            System.out.println("[surefire] NOT FOUND — measurement needs the testorder fork. Build & install it");
            System.out.println("           (mvn install -DskipTests -Drat.skip -Denforcer.skip in the maven-surefire fork),");
            System.out.println("           or set 'surefire-ext' via configure.");
        }
        Path agent = locateAgent();
        System.out.println("[surefire] instrumentation agent: "
                + (agent != null && Files.exists(agent) ? agent : "(missing — runtime+status only)"));
    }

    public Path locateAgent() {
        try {
            Path self = Paths.get(Orchestrator.class.getProtectionDomain().getCodeSource().getLocation().toURI());
            return self.getParent() == null ? null : self.getParent().resolve("csto2-agent.jar");
        } catch (Exception e) { return null; }
    }
}
