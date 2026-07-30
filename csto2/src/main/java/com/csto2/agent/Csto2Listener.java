package com.csto2.agent;

import com.csto2.util.Json;
import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.engine.TestSource;
import org.junit.platform.engine.support.descriptor.ClassSource;
import org.junit.platform.engine.support.descriptor.MethodSource;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;

import java.lang.management.ClassLoadingMXBean;
import java.lang.management.CompilationMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.TimeZone;

/**
 * JUnit Platform listener (ServiceLoader-registered by {@link Csto2Agent}) that records, per top-level
 * test class, the same durable-state deltas the legacy TraceRunner captured: classes loaded, JIT
 * compile time, GC count/time, allocated bytes, thread delta — plus per-class JFR facts via
 * {@link JfrProbe}. Output is merged back into the Surefire trace by {@code SurefireOrchestrator}.
 *
 * <p>Depth counting collapses {@code @Nested} classes into their enclosing top-level class window, so
 * each top-level class yields exactly one row. Assumes sequential execution (required anyway, since
 * cross-class carryover is what we measure).
 */
public final class Csto2Listener implements TestExecutionListener {

    private static volatile Path outFile;
    private static volatile String orderId = "order";

    /** Called from the agent premain before the launcher builds. */
    static void configure(String out, String order) {
        outFile = out == null ? null : Paths.get(out);
        if (order != null) orderId = order;
    }

    private final ClassLoadingMXBean cl = ManagementFactory.getClassLoadingMXBean();
    private final CompilationMXBean comp = ManagementFactory.getCompilationMXBean();
    private final ThreadMXBean threads = ManagementFactory.getThreadMXBean();
    private final List<GarbageCollectorMXBean> gcs = ManagementFactory.getGarbageCollectorMXBeans();
    private final List<Map<String, Object>> rows = new ArrayList<>();

    private int depth = 0, pos = 0, curPos = 0;
    private String curClass;
    private Object curJfrEvent;
    private Object curMethodJfrEvent;
    private String curMethod;
    private int methodPos = 0;
    private RuntimeState state0;
    private List<Map<String, Object>> threadState0;
    private long loaded0, jit0, thr0, gcCount0, gcMs0, alloc0, t0;

    @Override
    public void executionStarted(TestIdentifier id) {
        if (isMethod(id)) {
            curMethod = methodName(id);
            curMethodJfrEvent = JfrTestClassEvent.begin(orderId, methodPos++, curMethod);
            return;
        }
        if (!isClass(id)) return;
        if (depth++ == 0) {
            curClass = className(id);
            curPos = pos++;

            loaded0 = cl.getTotalLoadedClassCount();
            jit0 = comp == null ? 0 : comp.getTotalCompilationTime();
            long[] g = gcSnapshot();
            gcCount0 = g[0];
            gcMs0 = g[1];
            thr0 = threads.getThreadCount();
            alloc0 = allocBytes();
            state0 = RuntimeState.capture();
            threadState0 = threadSnapshot();
            t0 = System.nanoTime();
            curJfrEvent = JfrTestClassEvent.begin(orderId, curPos, curClass);
        }
    }

    @Override
    public void executionFinished(TestIdentifier id, TestExecutionResult result) {
        if (isMethod(id)) {
            JfrTestClassEvent.finish(curMethodJfrEvent, result.getStatus().name(), 0, 0, 0, 0, 0);
            curMethodJfrEvent = null;
            curMethod = null;
            return;
        }
        if (!isClass(id)) return;
        if (--depth == 0 && curClass != null) {

            long[] g = gcSnapshot();
            long classesLoaded = cl.getTotalLoadedClassCount() - loaded0;
            long jitMs = (comp == null ? 0 : comp.getTotalCompilationTime()) - jit0;
            long gcCount = g[0] - gcCount0;
            long gcMs = g[1] - gcMs0;
            long allocated = Math.max(0, allocBytes() - alloc0);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("test", curClass);
            row.put("position", curPos);
            row.put("agentRuntimeMs", (System.nanoTime() - t0) / 1e6);
            row.put("classesLoaded", classesLoaded);
            row.put("jitMs", jitMs);
            row.put("gcCount", gcCount);
            row.put("gcMs", gcMs);
            row.put("allocBytes", allocated);
            row.put("threadDelta", threads.getThreadCount() - thr0);
            row.put("threadsBefore", threadState0);
            row.put("threadsAfter", threadSnapshot());
            row.put("stateChanges", state0 == null
                    ? Collections.emptyList()
                    : state0.diff(RuntimeState.capture()));
            rows.add(row);
            JfrTestClassEvent.finish(
                    curJfrEvent,
                    result.getStatus().name(),
                    allocated,
                    classesLoaded,
                    jitMs,
                    gcCount,
                    gcMs);
            curJfrEvent = null;
            state0 = null;
            threadState0 = null;
            curClass = null;

        }
    }

    @Override
    public void testPlanExecutionFinished(TestPlan testPlan) {
        try {
            if (outFile != null) {
                if (outFile.getParent() != null) Files.createDirectories(outFile.getParent());
                StringBuilder sb = new StringBuilder();
                for (Map<String, Object> r : rows) sb.append(Json.write(r)).append('\n');
                Files.write(outFile, sb.toString().getBytes(StandardCharsets.UTF_8));
            }

        } catch (Throwable t) {
            System.err.println("[csto2-agent] failed to write facts: " + t);
        }
    }

    private static boolean isClass(TestIdentifier id) {
        return id.getSource().map(s -> s instanceof ClassSource).orElse(false);
    }

    private static boolean isMethod(TestIdentifier id) {
        return id.getSource().map(s -> s instanceof MethodSource).orElse(false);
    }

    private static String methodName(TestIdentifier id) {
        TestSource source = id.getSource().orElse(null);
        if (source instanceof MethodSource) {
            MethodSource method = (MethodSource) source;
            return method.getClassName() + "#" + method.getMethodName();
        }
        return id.getLegacyReportingName();
    }

    private static String className(TestIdentifier id) {
        TestSource s = id.getSource().orElse(null);
        return s instanceof ClassSource ? ((ClassSource) s).getClassName() : id.getLegacyReportingName();
    }

    private long[] gcSnapshot() {
        long count = 0, ms = 0;
        for (GarbageCollectorMXBean g : gcs) {
            long c = g.getCollectionCount(); if (c > 0) count += c;
            long t = g.getCollectionTime(); if (t > 0) ms += t;
        }
        return new long[]{count, ms};
    }

    /** Sum of allocated bytes across live threads (HotSpot); 0 if unsupported. */
    private long allocBytes() {
        try {
            ThreadMXBean base = ManagementFactory.getThreadMXBean();
            if (base instanceof com.sun.management.ThreadMXBean) {
                com.sun.management.ThreadMXBean cb = (com.sun.management.ThreadMXBean) base;
                if (cb.isThreadAllocatedMemorySupported()) {
                    long[] ids = base.getAllThreadIds();
                    long[] bytes = cb.getThreadAllocatedBytes(ids);
                    long sum = 0;
                    for (long b : bytes) if (b > 0) sum += b;
                    return sum;
                }
            }
        } catch (Throwable ignore) {}
        return 0;
    }

    /**
     * Record named application and ZooKeeper threads at class boundaries. The top frame is enough
     * to distinguish a server thread that is still doing work from a parked executor worker.
     */
    private static List<Map<String, Object>> threadSnapshot() {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map.Entry<Thread, StackTraceElement[]> entry : Thread.getAllStackTraces().entrySet()) {
            Thread thread = entry.getKey();
            String name = thread.getName();
            if (isInfrastructureThread(name)) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", thread.getId());
            row.put("name", name);
            row.put("daemon", thread.isDaemon());
            row.put("state", thread.getState().name());
            StackTraceElement[] stack = entry.getValue();
            row.put("top", stack.length == 0 ? "" : stack[0].toString());
            result.add(row);
        }
        result.sort((left, right) -> {
            int byName = String.valueOf(left.get("name")).compareTo(String.valueOf(right.get("name")));
            return byName != 0 ? byName : Long.compare((Long) left.get("id"), (Long) right.get("id"));
        });
        return result;
    }

    private static boolean isInfrastructureThread(String name) {
        return "main".equals(name)
                || "Reference Handler".equals(name)
                || "Finalizer".equals(name)
                || "Signal Dispatcher".equals(name)
                || "Common-Cleaner".equals(name)
                || "Notification Thread".equals(name)
                || name.startsWith("process reaper");
    }

    /**
     * Small snapshot of process-wide state that tests commonly mutate. Property values whose names
     * look credential-bearing are redacted before they reach the artifact.
     */
    private static final class RuntimeState {
        private final Map<String, String> properties;
        private final String locale;
        private final String displayLocale;
        private final String formatLocale;
        private final String timeZone;
        private final String contextClassLoader;
        private final String securityManager;
        private final String defaultUncaughtHandler;
        private final String systemIn;
        private final String systemOut;
        private final String systemErr;

        private RuntimeState(
                Map<String, String> properties,
                String locale,
                String displayLocale,
                String formatLocale,
                String timeZone,
                String contextClassLoader,
                String securityManager,
                String defaultUncaughtHandler,
                String systemIn,
                String systemOut,
                String systemErr) {
            this.properties = properties;
            this.locale = locale;
            this.displayLocale = displayLocale;
            this.formatLocale = formatLocale;
            this.timeZone = timeZone;
            this.contextClassLoader = contextClassLoader;
            this.securityManager = securityManager;
            this.defaultUncaughtHandler = defaultUncaughtHandler;
            this.systemIn = systemIn;
            this.systemOut = systemOut;
            this.systemErr = systemErr;
        }

        static RuntimeState capture() {
            Map<String, String> properties = new HashMap<>();
            try {
                Properties source = System.getProperties();
                for (String key : source.stringPropertyNames()) {
                    properties.put(key, safePropertyValue(key, source.getProperty(key)));
                }
            } catch (Throwable ignored) {
                // A SecurityManager may forbid access. The other state probes remain useful.
            }
            return new RuntimeState(
                    properties,
                    safe(() -> Locale.getDefault().toLanguageTag()),
                    safe(() -> Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag()),
                    safe(() -> Locale.getDefault(Locale.Category.FORMAT).toLanguageTag()),
                    safe(() -> TimeZone.getDefault().getID()),
                    identity(safeObject(() -> Thread.currentThread().getContextClassLoader())),
                    identity(safeObject(() -> System.getSecurityManager())),
                    identity(safeObject(Thread::getDefaultUncaughtExceptionHandler)),
                    identity(System.in),
                    identity(System.out),
                    identity(System.err));
        }

        List<Map<String, Object>> diff(RuntimeState after) {
            List<Map<String, Object>> changes = new ArrayList<>();
            List<String> keys = new ArrayList<>();
            keys.addAll(properties.keySet());
            for (String key : after.properties.keySet()) {
                if (!properties.containsKey(key)) keys.add(key);
            }
            Collections.sort(keys);
            for (String key : keys) {
                addChange(changes, "systemProperty", key, properties.get(key), after.properties.get(key));
            }
            addChange(changes, "runtime", "locale.default", locale, after.locale);
            addChange(changes, "runtime", "locale.display", displayLocale, after.displayLocale);
            addChange(changes, "runtime", "locale.format", formatLocale, after.formatLocale);
            addChange(changes, "runtime", "timezone.default", timeZone, after.timeZone);
            addChange(
                    changes,
                    "runtime",
                    "thread.contextClassLoader",
                    contextClassLoader,
                    after.contextClassLoader);
            addChange(changes, "runtime", "securityManager", securityManager, after.securityManager);
            addChange(
                    changes,
                    "runtime",
                    "thread.defaultUncaughtExceptionHandler",
                    defaultUncaughtHandler,
                    after.defaultUncaughtHandler);
            addChange(changes, "runtime", "system.in", systemIn, after.systemIn);
            addChange(changes, "runtime", "system.out", systemOut, after.systemOut);
            addChange(changes, "runtime", "system.err", systemErr, after.systemErr);
            return changes;
        }

        private static void addChange(
                List<Map<String, Object>> changes,
                String kind,
                String key,
                String before,
                String after) {
            if (before == null ? after == null : before.equals(after)) return;
            Map<String, Object> change = new LinkedHashMap<>();
            change.put("kind", kind);
            change.put("key", key);
            change.put("before", before);
            change.put("after", after);
            changes.add(change);
        }

        private static String safePropertyValue(String key, String value) {
            String lower = key.toLowerCase(Locale.ROOT);
            if (lower.contains("password")
                    || lower.contains("passwd")
                    || lower.contains("secret")
                    || lower.contains("token")
                    || lower.contains("credential")) {
                return value == null ? null : "<redacted>";
            }
            return value;
        }

        private static String identity(Object value) {
            return value == null
                    ? null
                    : value.getClass().getName() + "@"
                            + Integer.toHexString(System.identityHashCode(value));
        }

        private static String safe(StringSupplier supplier) {
            try {
                return supplier.get();
            } catch (Throwable ignored) {
                return "<unavailable>";
            }
        }

        private static Object safeObject(ObjectSupplier supplier) {
            try {
                return supplier.get();
            } catch (Throwable ignored) {
                return null;
            }
        }
    }

    private interface StringSupplier {
        String get();
    }

    private interface ObjectSupplier {
        Object get();
    }
}
