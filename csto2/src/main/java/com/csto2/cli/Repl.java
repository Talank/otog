package com.csto2.cli;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Interactive menu loop that drives the full CSTO v2 pipeline. Delegates all configuration,
 * project autodetection, and stage execution to {@link Orchestrator}.
 */
public final class Repl {

    private final BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    private final Orchestrator orchestrator = new Orchestrator();

    public void run() throws Exception {
        run(Paths.get(System.getProperty("user.dir")));
    }

    /** Launch the REPL; if {@code startDir} (or cwd) looks like a Maven project, offer to load it. */
    public void run(Path startDir) throws Exception {
        System.out.println("CSTO v2 pipeline REPL — type a number, or 'q' to quit.");
        if (startDir != null && Files.exists(startDir.resolve("pom.xml"))) {
            String yn = prompt("Detected Maven project at " + startDir.toAbsolutePath()
                    + " — load classpath + tests now? (Y/n)");
            if (yn == null) return;
            if (!yn.trim().equalsIgnoreCase("n")) {
                try {
                    orchestrator.loadProject(startDir, msg -> {
                        String ans = prompt(msg);
                        return ans != null && !ans.trim().equalsIgnoreCase("n");
                    });
                }
                catch (Throwable t) { System.out.println("[project] autodetect failed: " + t); }
            }
        }
        orchestrator.loadPersistedExclusions();
        orchestrator.reportRunnerStatus();
        loop:
        while (true) {
            printMenu();
            String choice = prompt("choice");
            if (choice == null) break;
            choice = choice.trim().toLowerCase();
            try {
                switch (choice) {
                    case "1": configure(); break;
                    case "2": orchestrator.state(); break;
                    case "e": exclude(); break;
                    case "a": approaches(); break;
                    case "p": project(); break;
                    case "3": orchestrator.discover(); break;
                    case "4": orchestrator.analyze(); break;
                    case "5": orchestrator.trace(); break;
                    case "6": orchestrator.select(); break;
                    case "7": orchestrator.validate(); break;
                    case "8": orchestrator.fullPipeline(); break;
                    case "s": orchestrator.scientific(); break;
                    case "q": case "0": case "quit": case "exit": break loop;
                    case "": break;
                    default: System.out.println("unknown choice: " + choice); break;
                }
            } catch (Throwable t) {
                System.out.println("[error] " + choice + " failed: " + t);
            }
        }
        System.out.println("bye.");
    }

    private void printMenu() {
        System.out.println();
        System.out.println("==== CSTO v2 ====  (base out: " + orchestrator.baseDir() + ")");
        System.out.println("  1) configure        set classpath / tests / JVM args / params");
        System.out.println("  2) state            show current config + produced artifacts");
        System.out.println("  e) exclude          drop test classes from the current test list");
        System.out.println("  a) approaches       enable/disable candidate strategies (select)");
        System.out.println("  p) project          autodetect cp + tests + workdir from a Maven project");
        System.out.println("  --- stages ---");
        System.out.println("  3) discover         filter the test list to runnable classes");
        System.out.println("  4) analyze          static comprehension (WALA) -> static-facts");
        System.out.println("  5) trace            run N orders (with JFR) -> trace.jsonl");
        System.out.println("  6) select           green-gated candidate selection -> ship order");
        System.out.println("  7) validate         slope-model initial-vs-optimized A/B");
        System.out.println("  --- combined ---");
        System.out.println("  8) full pipeline    discover -> trace -> select");
        System.out.println("  s) scientific       full pipeline @ 10 repeats + Wilcoxon signed-rank test");
        System.out.println("  q) quit");
    }

    // ---- exclude -------------------------------------------------------------------------------

    private void exclude() throws Exception {
        String testsPath = orchestrator.cfg.get("tests");
        if (testsPath == null) {
            System.out.println("[exclude] no 'tests' file configured. Run 'project' or configure it first.");
            return;
        }
        Path testsFile = Paths.get(testsPath);
        if (!Files.exists(testsFile)) {
            System.out.println("[exclude] 'tests' file not found: " + testsFile);
            return;
        }
        List<String> current = new ArrayList<>();
        for (String line : Files.readAllLines(testsFile)) {
            String t = line.trim();
            if (!t.isEmpty()) current.add(t);
        }
        if (current.isEmpty()) {
            System.out.println("[exclude] current test list is empty: " + testsFile);
            return;
        }

        String raw = prompt("classes to exclude (FQN or simple name; comma/space separated)");
        if (raw == null || raw.isBlank()) {
            System.out.println("[exclude] nothing entered.");
            return;
        }

        List<String> tokens = new ArrayList<>();
        for (String tok : raw.trim().split("[,\\s]+")) {
            if (!tok.isEmpty()) tokens.add(tok);
        }

        try {
            orchestrator.exclude(tokens);
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }
    }

    // ---- approaches ----------------------------------------------------------------------------

    private void approaches() throws Exception {
        while (true) {
            Set<String> disabled = orchestrator.disabledApproaches();
            orchestrator.printApproachesState(disabled);
            String line = prompt("toggle name(s) to flip, or Enter to finish");
            if (line == null) return;
            line = line.trim();
            if (line.isEmpty()) break;
            List<String> toggles = new ArrayList<>();
            for (String tok : line.split("[,\\s]+")) {
                if (!tok.isEmpty()) toggles.add(tok);
            }
            orchestrator.approaches(toggles);
        }
    }

    // ---- project autodetect ----------------------------------------------------------------------

    private void project() throws Exception {
        String dir = prompt("project dir [" + Paths.get(System.getProperty("user.dir")).toAbsolutePath() + "]");
        if (dir == null) return;
        dir = dir.trim();
        Path p = dir.isEmpty() ? Paths.get(System.getProperty("user.dir")) : Paths.get(dir);
        orchestrator.loadProject(p, msg -> {
            String ans = prompt(msg);
            return ans != null && !ans.trim().equalsIgnoreCase("n");
        });
        orchestrator.loadPersistedExclusions();
    }

    // ---- configure / state --------------------------------------------------------------------------

    private void configure() throws Exception {
        System.out.println("Set values (blank keeps current).");
        Map<String, String> kv = new LinkedHashMap<>();
        for (String[] k : Orchestrator.CONFIG_KEYS) {
            String cur = orchestrator.cfg.get(k[0]);
            String shown = cur == null ? "<unset>" : cur;
            String v = prompt(String.format("%-12s [%s]  (%s)", k[0], shown, k[1]));
            if (v == null) return;
            v = v.trim();
            if (!v.isEmpty()) kv.put(k[0], v);
        }
        orchestrator.configure(kv);
    }

    private String prompt(String label) throws IOException {
        System.out.print(label + "> ");
        System.out.flush();
        return in.readLine();
    }
}
