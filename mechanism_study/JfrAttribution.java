import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import jdk.jfr.consumer.RecordedClass;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedMethod;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;

/**
 * Attributes JVM events and sampled call paths to the dynamic com.csto2.TestClass intervals.
 *
 * Compile/run with JDK 11+:
 *   javac mechanism_study/JfrAttribution.java
 *   java -cp mechanism_study JfrAttribution run.jfr JavadocExtractorTest BulkParseTest
 */
public final class JfrAttribution {
    private static final String TEST_EVENT = "com.csto2.TestClass";

    private static final class Window {
        final String test;
        final int position;
        final Instant start;
        final Instant end;
        final long allocBytes;
        final long jitMs;
        final long gcCount;
        final long gcMs;
        final Map<String, Aggregate> byType = new LinkedHashMap<>();
        final Map<String, Long> cpuLeaf = new HashMap<>();
        final Map<String, Long> cpuPath = new HashMap<>();
        final Map<String, Long> nativeLeaf = new HashMap<>();
        final Map<String, Long> nativePath = new HashMap<>();
        final Map<String, Long> nativeThread = new HashMap<>();
        final Map<String, Long> allocType = new HashMap<>();
        final Map<String, Long> allocPath = new HashMap<>();
        final Map<String, Long> compiledMethodMs = new HashMap<>();
        final Map<String, Long> loadedClasses = new HashMap<>();
        final List<CompilationDetail> compilations = new ArrayList<>();

        Window(RecordedEvent event) {
            test = event.getString("test");
            position = event.getInt("position");
            start = event.getStartTime();
            end = event.getEndTime();
            allocBytes = event.getLong("allocBytes");
            jitMs = event.getLong("jitMs");
            gcCount = event.getLong("gcCount");
            gcMs = event.getLong("gcMs");
        }

        boolean contains(Instant timestamp) {
            return !timestamp.isBefore(start) && !timestamp.isAfter(end);
        }
    }

    private static final class Aggregate {
        long count;
        long durationNanos;
        long bytes;
    }

    private static final class CompilationDetail {
        final long offsetMs;
        final long durationMs;
        final String method;
        final int level;
        final boolean osr;

        CompilationDetail(Window window, RecordedEvent event, RecordedMethod recordedMethod) {
            offsetMs = Duration.between(window.start, event.getStartTime()).toMillis();
            durationMs = event.getDuration().toMillis();
            method = methodName(recordedMethod);
            level = event.getInt("compileLevel");
            osr = event.getBoolean("isOsr");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: JfrAttribution recording.jfr TestNameSubstring...");
            System.exit(2);
        }
        Path recording = Path.of(args[0]);
        List<String> filters = new ArrayList<>();
        for (int i = 1; i < args.length; i++) filters.add(args[i]);

        List<Window> windows = new ArrayList<>();
        try (RecordingFile file = new RecordingFile(recording)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!TEST_EVENT.equals(event.getEventType().getName())) continue;
                String test = event.getString("test");
                if (filters.stream().anyMatch(test::contains)) windows.add(new Window(event));
            }
        }
        windows.sort(Comparator.comparing(window -> window.start));
        if (windows.isEmpty()) throw new IllegalArgumentException("no matching test windows");

        try (RecordingFile file = new RecordingFile(recording)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (TEST_EVENT.equals(event.getEventType().getName())) continue;
                Window window = find(windows, event.getStartTime());
                if (window == null) continue;
                attribute(window, event);
            }
        }

        System.out.println("Recording: " + recording);
        for (Window window : windows) print(window);
    }

    private static Window find(List<Window> windows, Instant timestamp) {
        for (Window window : windows) {
            if (window.contains(timestamp)) return window;
        }
        return null;
    }

    private static void attribute(Window window, RecordedEvent event) {
        String type = event.getEventType().getName();
        Aggregate aggregate = window.byType.computeIfAbsent(type, ignored -> new Aggregate());
        aggregate.count++;
        aggregate.durationNanos += event.getDuration().toNanos();

        if ("jdk.ExecutionSample".equals(type)) {
            String leaf = firstApplicationFrame(event.getStackTrace());
            String path = applicationPath(event.getStackTrace(), 10);
            window.cpuLeaf.merge(leaf, 1L, Long::sum);
            window.cpuPath.merge(path, 1L, Long::sum);
        } else if ("jdk.NativeMethodSample".equals(type)) {
            String leaf = firstApplicationFrame(event.getStackTrace());
            String path = applicationPath(event.getStackTrace(), 10);
            window.nativeLeaf.merge(leaf, 1L, Long::sum);
            window.nativePath.merge(path, 1L, Long::sum);
            if (event.getThread("sampledThread") != null) {
                window.nativeThread.merge(
                        event.getThread("sampledThread").getJavaName(), 1L, Long::sum);
            }
        } else if ("jdk.ObjectAllocationInNewTLAB".equals(type)
                || "jdk.ObjectAllocationOutsideTLAB".equals(type)) {
            RecordedClass objectClass = event.getClass("objectClass");
            long bytes = event.getLong("allocationSize");
            aggregate.bytes += bytes;
            window.allocType.merge(
                    objectClass == null ? "<unknown>" : objectClass.getName(), bytes, Long::sum);
            window.allocPath.merge(applicationPath(event.getStackTrace(), 10), bytes, Long::sum);
        } else if ("jdk.Compilation".equals(type)) {
            RecordedMethod method = event.getValue("method");
            if (method != null) {
                window.compiledMethodMs.merge(
                        methodName(method),
                        Math.max(1L, event.getDuration().toMillis()),
                        Long::sum);
                window.compilations.add(new CompilationDetail(window, event, method));
            }
        } else if ("jdk.ClassLoad".equals(type)) {
            RecordedClass loaded = event.getClass("loadedClass");
            if (loaded != null) window.loadedClasses.merge(loaded.getName(), 1L, Long::sum);
        } else if (type.startsWith("jdk.File") || type.startsWith("jdk.Socket")) {
            if (event.hasField("bytesRead")) aggregate.bytes += event.getLong("bytesRead");
            if (event.hasField("bytesWritten")) aggregate.bytes += event.getLong("bytesWritten");
        }
    }

    private static String firstApplicationFrame(RecordedStackTrace trace) {
        if (trace == null) return "<no-java-stack>";
        for (RecordedFrame frame : trace.getFrames()) {
            RecordedMethod method = frame.getMethod();
            if (method == null) continue;
            String name = methodName(method);
            if (isApplication(name)) return name;
        }
        return "<runtime-or-native>";
    }

    private static String applicationPath(RecordedStackTrace trace, int limit) {
        if (trace == null) return "<no-java-stack>";
        List<String> frames = new ArrayList<>();
        for (RecordedFrame frame : trace.getFrames()) {
            RecordedMethod method = frame.getMethod();
            if (method == null) continue;
            String name = methodName(method);
            if (isApplication(name)) {
                frames.add(name);
                if (frames.size() == limit) break;
            }
        }
        return frames.isEmpty() ? "<runtime-or-native>" : String.join(" <- ", frames);
    }

    private static boolean isApplication(String method) {
        return method.startsWith("com.github.javaparser.")
                || method.startsWith("com.github.javacc.")
                || method.startsWith("com.github.javaparser.generated.")
                || method.startsWith("org.yaml.snakeyaml.")
                || method.startsWith("org.pyyaml.")
                || method.startsWith("examples.")
                || method.startsWith("org.apache.commons.text.")
                || method.startsWith("org.apache.commons.lang3.")
                || method.startsWith("org.apache.commons.io.")
                || method.startsWith("org.apache.curator.")
                || method.startsWith("java.util.zip.")
                || method.startsWith("io.netty.")
                || method.startsWith("org.springframework.")
                || method.startsWith("okhttp3.")
                || method.startsWith("okio.")
                || method.startsWith("reactor.")
                || method.startsWith("com.fasterxml.jackson.")
                || method.startsWith("tools.jackson.");
    }

    private static String methodName(RecordedMethod method) {
        String type = method.getType() == null ? "<unknown>" : method.getType().getName();
        return type + "." + method.getName();
    }

    private static void print(Window window) {
        System.out.printf(
                "%n=== %s (position %d, duration %.3f s) ===%n",
                window.test,
                window.position,
                Duration.between(window.start, window.end).toNanos() / 1e9);
        System.out.printf(
                "Boundary counters: alloc=%.1f MiB, jit=%d ms, gc=%d/%d ms%n",
                window.allocBytes / 1048576.0,
                window.jitMs,
                window.gcCount,
                window.gcMs);

        for (String type :
                List.of(
                        "jdk.ExecutionSample",
                        "jdk.NativeMethodSample",
                        "jdk.ObjectAllocationInNewTLAB",
                        "jdk.ObjectAllocationOutsideTLAB",
                        "jdk.GarbageCollection",
                        "jdk.GCPhasePause",
                        "jdk.Compilation",
                        "jdk.ClassLoad",
                        "jdk.ThreadPark",
                        "jdk.JavaMonitorEnter",
                        "jdk.FileRead",
                        "jdk.FileWrite")) {
            Aggregate value = window.byType.get(type);
            if (value == null) continue;
            System.out.printf(
                    "%-36s count=%6d duration=%9.3f ms sampled-bytes=%.1f MiB%n",
                    type,
                    value.count,
                    value.durationNanos / 1e6,
                    value.bytes / 1048576.0);
        }

        top("Java execution-sample application leaf methods", window.cpuLeaf, 15, false);
        top("Java execution-sample application paths", window.cpuPath, 12, false);
        top("Native-method sample threads", window.nativeThread, 15, false);
        top("Native-method sample application leaf methods", window.nativeLeaf, 15, false);
        top("Native-method sample application paths", window.nativePath, 12, false);
        top("Sampled allocation object types", window.allocType, 15, true);
        top("Sampled allocation application paths", window.allocPath, 12, true);
        top("Compilation time by method", window.compiledMethodMs, 12, false);
        printCompilationTimeline(window);
        top("Classes loaded during test", window.loadedClasses, 100, false);
    }

    private static void printCompilationTimeline(Window window) {
        System.out.println("Compilation timeline (start offset, duration, tier, method):");
        for (CompilationDetail detail : window.compilations) {
            System.out.printf(
                    "  +%5d ms %5d ms L%d%s  %s%n",
                    detail.offsetMs,
                    detail.durationMs,
                    detail.level,
                    detail.osr ? " OSR" : "",
                    detail.method);
        }
    }

    private static void top(String title, Map<String, Long> values, int limit, boolean bytes) {
        System.out.println(title + ":");
        List<Map.Entry<String, Long>> entries = values.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .limit(limit)
                .collect(Collectors.toList());
        for (Map.Entry<String, Long> entry : entries) {
            String value = bytes
                    ? String.format("%9.2f MiB", entry.getValue() / 1048576.0)
                    : String.format("%9d", entry.getValue());
            System.out.printf("  %s  %s%n", value, entry.getKey());
        }
    }
}
