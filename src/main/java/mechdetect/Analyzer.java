package mechdetect;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Reads one profiled run (profile.jsonl + recording.jfr) and emits (test, front|back, flags). */
public final class Analyzer {

    static final class Row {
        String test;
        double runtimeMs;
        long startMs, endMs, threadsStarted, methods;
        List<String> propWrites, retransformed, stateChanges;
        int samples, platformSamples, classLoads, deopts;
        long compileMs;
        Map<String, Integer> leafCount = new HashMap<>();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Paths.get(args[0]);
        List<Row> rows = parse(dir.resolve("profile.jsonl"));
        if (Files.exists(dir.resolve("recording.jfr"))) bin(dir.resolve("recording.jfr"), rows);

        // rare-write filters: state/property churn seen at many boundaries is infrastructure
        Map<String, Integer> stateFreq = new HashMap<>(), propFreq = new HashMap<>();
        Map<String, List<String>> writersOf = new HashMap<>();
        for (Row r : rows) {
            for (String c : new HashSet<>(fields(r.stateChanges))) {
                bump(stateFreq, c);
                writersOf.computeIfAbsent(c, k -> new ArrayList<>()).add(r.test);
            }
            for (String p : new HashSet<>(r.propWrites)) bump(propFreq, p);
        }
        // more than a handful of distinct writers = suite-wide convention, not a mechanism
        int maxFreq = Math.max(2, Math.min(8, rows.size() / 10));
        StringBuilder metrics = new StringBuilder("test\truntimeMs\tsamples\tplatFrac\tcompileMs\tloads\tdeopts\tthreads\tstateW\tpropW\tretrans\n");
        for (Row r : rows) {
            List<String> keep = new ArrayList<>();
            for (String c : r.stateChanges) if (stateFreq.get(fieldOf(c)) <= maxFreq) keep.add(c);
            r.stateChanges = keep;
            List<String> props = new ArrayList<>();
            for (String p : r.propWrites) if (propFreq.get(p) <= maxFreq) props.add(p);
            r.propWrites = props;
            metrics.append(String.format("%s\t%.0f\t%d\t%.2f\t%d\t%d\t%d\t%d\t%d\t%d\t%d%n",
                    r.test, r.runtimeMs, r.samples, frac(r.platformSamples, r.samples), r.compileMs,
                    r.classLoads, r.deopts, r.threadsStarted, new HashSet<>(fields(r.stateChanges)).size(),
                    new HashSet<>(r.propWrites).size(), r.retransformed.size()));
        }
        Files.write(dir.resolve("metrics.tsv"), metrics.toString().getBytes());

        // how many windows have each leaf as their TOP leaf: a leaf that tops many windows is
        // suite-wide harness work (e.g. a per-test thread dump), not a test-specific hot path
        Map<String, Integer> topLeafWindows = new HashMap<>();
        for (Row r : rows)
            r.leafCount.entrySet().stream().max(Map.Entry.comparingByValue())
                    .ifPresent(e -> bump(topLeafWindows, e.getKey()));

        // rank = severity of the strongest flag; back-movers run in ascending rank (worst last)
        List<Object[]> back = new ArrayList<>(), front = new ArrayList<>();
        for (Row r : rows) {
            List<String> flags = new ArrayList<>();
            int rank = 0;
            // drop same-window sweeps: >=4 changed fields holding the same value class is
            // crosscutting framework churn (log counters), not a test-specific mechanism
            Map<String, Integer> byValClass = new HashMap<>();
            for (String c : r.stateChanges) bump(byValClass, valClass(c));
            List<String> muts = new ArrayList<>(), news = new ArrayList<>(), tls = new ArrayList<>();
            for (String c : r.stateChanges) {
                if (byValClass.get(valClass(c)) >= 4) continue;
                if (c.substring(c.indexOf('|') + 1).contains("tl:")) tls.add(fieldOf(c));
                else (c.contains("|<new>|") ? news : muts).add(fieldOf(c));
            }
            if (!news.isEmpty()) { flags.add("STATE_NEW:" + news); rank = Math.max(rank, 1); }
            if (!r.propWrites.isEmpty()) { flags.add("PROP_WRITER:" + new HashSet<>(r.propWrites)); rank = Math.max(rank, 1); }
            if (!muts.isEmpty()) { flags.add("STATE_MUT:" + muts); rank = Math.max(rank, 2); }
            // compile demand above the test's own runtime: it both feeds and waits on the JIT;
            // warm code from earlier tests helps it, and its queue load can starve later tests
            if (r.compileMs > Math.max(r.runtimeMs, 150)) { flags.add("JIT_HUNGRY:" + r.compileMs + "ms"); rank = Math.max(rank, 2); }
            // a ThreadLocal left holding a value: per-thread config leaked to whoever runs next
            if (!tls.isEmpty()) { flags.add("STATE_TL:" + tls); rank = Math.max(rank, 3); }
            if (r.threadsStarted >= 64) { flags.add("THREAD_CHURNER:" + r.threadsStarted); rank = Math.max(rank, 3); }
            if (!r.retransformed.isEmpty()) { flags.add("RETRANSFORMER:" + r.retransformed.size() + "types"); rank = Math.max(rank, 4); }
            int topLeaf = r.leafCount.values().stream().max(Integer::compare).orElse(0);
            String topLeafM = r.leafCount.entrySet().stream()
                    .max(Map.Entry.comparingByValue()).map(Map.Entry::getKey).orElse("");
            // hot path concentrated in one platform-library method: profile pollution and
            // compiler-queue delay from the rest of the suite hit it hardest, so run it first
            boolean cold = r.samples >= 10 && frac(r.platformSamples, r.samples) >= 0.9
                    && frac(topLeaf, r.samples) >= 0.4 && platform(topLeafM) && r.runtimeMs >= 200
                    && topLeafWindows.getOrDefault(topLeafM, 0) <= 2;
            // a lone mutation with no corroborating signal (no compile demand, threads, TL,
            // retransform, or created state) is too weak to justify displacing the test
            boolean weakMutOnly = flags.size() == 1 && flags.get(0).startsWith("STATE_MUT");
            if (cold && rank == 0) { flags.add("COLD_FAVORED"); front.add(new Object[]{r, 0, flags}); }
            else if (rank > 0 && !weakMutOnly) back.add(new Object[]{r, rank, flags});
        }
        back.sort((a, b) -> {
            int byRank = Integer.compare((int) a[1], (int) b[1]);
            if (byRank != 0) return byRank;
            // equally-ranked JIT-hungry suites: the one with more cases warms shared code
            // fastest and gains least from running late, so it goes first
            int byMethods = Long.compare(((Row) b[0]).methods, ((Row) a[0]).methods);
            return byMethods != 0 ? byMethods : Double.compare(((Row) a[0]).runtimeMs, ((Row) b[0]).runtimeMs);
        });
        List<String> out = new ArrayList<>();
        for (Object[] c : front) out.add(((Row) c[0]).test + "\tfront\t" + c[1] + "\t" + c[2]);
        for (Object[] c : back) out.add(((Row) c[0]).test + "\tback\t" + c[1] + "\t" + c[2]);

        // coupled hot-code pairs: two sample-heavy tests whose leaf histograms overlap share the
        // code the JIT specializes; which of them shapes the shared profile first can matter in
        // either direction, so emit the SWAP of their current relative order and let the
        // measurement filter keep or kill it. Top 2 pairs per suite.
        List<Object[]> swaps = new ArrayList<>();
        for (int i = 0; i < rows.size(); i++) {
            Row a = rows.get(i);
            if (a.samples < 30 || a.runtimeMs < 500) continue;
            for (int j = i + 1; j < rows.size(); j++) {
                Row b = rows.get(j);
                if (b.samples < 30 || b.runtimeMs < 500) continue;
                int shared = 0;
                for (Map.Entry<String, Integer> e : a.leafCount.entrySet()) {
                    Integer other = b.leafCount.get(e.getKey());
                    if (other != null) shared += Math.min(e.getValue(), other);
                }
                double overlap = (double) shared / Math.min(a.samples, b.samples);
                if (overlap >= 0.4) swaps.add(new Object[]{a, b, overlap, a.samples + b.samples});
            }
        }
        swaps.sort((x, y) -> Integer.compare((int) y[3], (int) x[3]));
        for (Object[] s : swaps.subList(0, Math.min(2, swaps.size())))
            out.add(((Row) s[0]).test + "\tswap:" + ((Row) s[1]).test + "\t0\t"
                    + String.format("[COUPLED_PAIR:overlap=%.2f]", (double) s[2]));

        // churn block: when a shared field has MANY writers (a package that keeps mutating a
        // config), the last writer leaves its state over everything after it. No single move
        // helps — the whole writer block goes to the tail, behind the consumers it pollutes.
        // One block = one candidate. Largest block only.
        String blockField = null;
        for (Map.Entry<String, List<String>> e : writersOf.entrySet())
            if (e.getValue().size() > maxFreq && e.getValue().size() >= 5
                    && (blockField == null || e.getValue().size() > writersOf.get(blockField).size()))
                blockField = e.getKey();
        if (blockField != null && writersOf.get(blockField).size() < rows.size() / 2)
            out.add(blockField + "\tblockback\t5\t[CHURN_BLOCK:" + writersOf.get(blockField).size()
                    + "writers members=" + String.join(",", writersOf.get(blockField)) + "]");
        String result = String.join("\n", out) + "\n";
        System.out.print(metrics + "\n" + result);
        Files.write(dir.resolve("candidates.tsv"), result.getBytes());
        System.err.println("[analyzer] " + out.size() + " candidates of " + rows.size() + " classes");
    }

    static void bin(Path jfr, List<Row> rows) throws Exception {
        for (RecordedEvent e : RecordingFile.readAllEvents(jfr)) {
            Row r = windowAt(rows, e.getStartTime().toEpochMilli());
            if (r == null) continue;
            String type = e.getEventType().getName();
            if (type.equals("jdk.Compilation")) r.compileMs += e.getDuration().toMillis();
            else if (type.equals("jdk.ClassLoad")) r.classLoads++;
            else if (type.equals("jdk.Deoptimization")) r.deopts++;
        }
    }

    static boolean platform(String cls) {
        return cls.startsWith("java.") || cls.startsWith("jdk.") || cls.startsWith("sun.")
                || cls.startsWith("com.sun.");
    }

    static Row windowAt(List<Row> rows, long t) {
        int lo = 0, hi = rows.size() - 1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            if (t < rows.get(mid).startMs) hi = mid - 1;
            else if (t > rows.get(mid).endMs) lo = mid + 1;
            else return rows.get(mid);
        }
        return null;
    }

    static double frac(int a, int b) { return b == 0 ? 0 : (double) a / b; }

    static void bump(Map<String, Integer> m, String k) { m.merge(k, 1, Integer::sum); }

    /** Class of the value a change left behind ("a.b.C@1f:hash" -> a.b.C), or "" for scalars. */
    static String valClass(String change) {
        String after = change.substring(change.lastIndexOf('|') + 1);
        int at = after.indexOf('@');
        return at > 0 && after.lastIndexOf('.', at) > 0 ? after.substring(0, at) : "";
    }

    static String fieldOf(String change) {
        int i = change.indexOf('|');
        return i < 0 ? change : change.substring(0, i);
    }

    static List<String> fields(List<String> changes) {
        List<String> out = new ArrayList<>();
        for (String c : changes) out.add(fieldOf(c));
        return out;
    }

    static List<Row> parse(Path file) throws Exception {
        List<Row> rows = new ArrayList<>();
        for (String line : Files.readAllLines(file)) {
            if (line.trim().isEmpty()) continue;
            Row r = new Row();
            Matcher m = Pattern.compile("\"test\":\"(.*?)\"").matcher(line);
            if (m.find()) r.test = m.group(1);
            r.runtimeMs = num(line, "runtimeMs");
            r.startMs = (long) num(line, "startMs");
            r.endMs = (long) num(line, "endMs");
            r.threadsStarted = (long) num(line, "threadsStarted");
            r.methods = (long) num(line, "methods");
            r.propWrites = strList(line, "propWrites");
            r.retransformed = strList(line, "retransformed");
            r.stateChanges = strList(line, "stateChanges");
            Matcher lm = Pattern.compile("\"sampleLeaves\":\\{(.*?)}").matcher(line);
            if (lm.find() && !lm.group(1).isEmpty())
                for (String kv : lm.group(1).split(",")) {
                    int i = kv.lastIndexOf(':');
                    String cls = kv.substring(1, i - 1);
                    int n = Integer.parseInt(kv.substring(i + 1));
                    r.leafCount.merge(cls, n, Integer::sum);
                    r.samples += n;
                    if (platform(cls)) r.platformSamples += n;
                }
            rows.add(r);
        }
        return rows;
    }

    static double num(String line, String key) {
        Matcher m = Pattern.compile("\"" + key + "\":([-0-9.]+)").matcher(line);
        return m.find() ? Double.parseDouble(m.group(1)) : 0;
    }

    static List<String> strList(String line, String key) {
        List<String> out = new ArrayList<>();
        Matcher m = Pattern.compile("\"" + key + "\":\\[(.*?)]").matcher(line);
        if (m.find() && !m.group(1).isEmpty())
            for (String s : m.group(1).split("\",\""))
                out.add(s.replaceAll("^\"|\"$", "").replace("\\\"", "\"").replace("\\\\", "\\"));
        return out;
    }

    private Analyzer() {}
}
