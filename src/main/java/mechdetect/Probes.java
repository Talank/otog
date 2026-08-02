package mechdetect;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;
import java.util.WeakHashMap;
import java.util.concurrent.ConcurrentHashMap;

/** In-fork probes. One profiled run produces profile.jsonl: one row per top-level test class. */
public final class Probes {

    private static Instrumentation inst;
    private static Path outDir;
    private static final List<String> rows = new ArrayList<>();
    private static volatile String currentTest;
    private static int position = 0, methodCount = 0;
    private static long startMs, startNs, loaded0, jit0, gc0, alloc0, thr0;
    private static final List<String> propWrites = new ArrayList<>(), retransformed = new ArrayList<>();
    private static final Map<String, String> fingerprints = new HashMap<>();
    private static final Map<Class<?>, Field[]> fieldCache = new WeakHashMap<>(), instFieldCache = new WeakHashMap<>();
    private static boolean propsHooked = false;

    // own stack sampler: the JFR method sampler is unreliable on some JVM builds
    private static final Map<String, Integer> leafCounts = new ConcurrentHashMap<>();
    private static volatile Thread samplerThread;

    private static void startSampler() {
        samplerThread = new Thread(() -> {
            java.lang.management.ThreadMXBean tb = ManagementFactory.getThreadMXBean();
            Map<Long, Long> cpuPrev = new HashMap<>();
            while (true) {
                try {
                    Thread.sleep(5);
                    boolean active = currentTest != null;
                    for (Map.Entry<Thread, StackTraceElement[]> e : Thread.getAllStackTraces().entrySet()) {
                        Thread t = e.getKey();
                        if (t == samplerThread) continue;
                        // sample only threads that burned CPU since the last tick: a thread blocked
                        // in native IO reports RUNNABLE but accrues no CPU time
                        long cpu = tb.getThreadCpuTime(t.getId());
                        Long prev = cpuPrev.put(t.getId(), cpu);
                        if (!active || prev == null || cpu <= prev || t.getState() != Thread.State.RUNNABLE) continue;
                        StackTraceElement[] st = e.getValue();
                        if (st.length == 0) continue;
                        String leaf = st[0].getClassName() + "." + st[0].getMethodName();
                        if (!leaf.startsWith("mechdetect")) leafCounts.merge(leaf, 1, Integer::sum);
                    }
                } catch (InterruptedException stop) {
                    return;
                } catch (Throwable ignore) {}
            }
        }, "mechdetect-sampler");
        samplerThread.setDaemon(true);
        samplerThread.start();
    }

    public static void install(Instrumentation instrumentation, String out) {
        inst = instrumentation;
        outDir = Paths.get(out == null ? "mechdetect-out" : out);
        startSampler();
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader l, String name, Class<?> beingRedefined,
                                    ProtectionDomain pd, byte[] bytes) {
                if (beingRedefined != null && currentTest != null && name != null)
                    synchronized (retransformed) { retransformed.add(name.replace('/', '.')); }
                return null;
            }
        }, true);
    }

    public static void methodStarted() { methodCount++; }

    public static synchronized void classStarted(String name) {
        if (!propsHooked) { hookProperties(); walkStatics(); propsHooked = true; }
        currentTest = name;
        methodCount = 0;
        startMs = System.currentTimeMillis();
        startNs = System.nanoTime();
        loaded0 = ManagementFactory.getClassLoadingMXBean().getTotalLoadedClassCount();
        jit0 = jitMs();
        gc0 = gcMs();
        alloc0 = allocBytes();
        thr0 = ManagementFactory.getThreadMXBean().getTotalStartedThreadCount();
    }

    public static synchronized void classFinished(String name, String status) {
        long endMs = System.currentTimeMillis();
        double runtimeMs = (System.nanoTime() - startNs) / 1e6;
        List<String> stateChanges = walkStatics();
        StringBuilder b = new StringBuilder();
        b.append("{\"test\":\"").append(esc(name)).append("\",\"position\":").append(position++)
                .append(",\"status\":\"").append(status).append("\",\"startMs\":").append(startMs)
                .append(",\"endMs\":").append(endMs).append(",\"runtimeMs\":").append(String.format("%.1f", runtimeMs))
                .append(",\"loadedDelta\":").append(ManagementFactory.getClassLoadingMXBean().getTotalLoadedClassCount() - loaded0)
                .append(",\"jitMsDelta\":").append(jitMs() - jit0).append(",\"gcMsDelta\":").append(gcMs() - gc0)
                .append(",\"allocDelta\":").append(Math.max(0, allocBytes() - alloc0))
                .append(",\"methods\":").append(methodCount)
                .append(",\"threadsStarted\":").append(ManagementFactory.getThreadMXBean().getTotalStartedThreadCount() - thr0);
        appendList(b, "propWrites", drain(propWrites));
        appendList(b, "retransformed", drain(retransformed));
        appendList(b, "stateChanges", stateChanges);
        b.append(",\"sampleLeaves\":{");
        Map<String, Integer> leaves = new HashMap<>(leafCounts);
        leafCounts.clear();
        boolean first = true;
        for (Map.Entry<String, Integer> e : leaves.entrySet()) {
            if (!first) b.append(',');
            first = false;
            b.append('"').append(esc(e.getKey())).append("\":").append(e.getValue());
        }
        rows.add(b.append("}}").toString());
        currentTest = null;
    }

    public static synchronized void flush() {
        try {
            Files.createDirectories(outDir);
            StringBuilder sb = new StringBuilder();
            for (String r : rows) sb.append(r).append('\n');
            Files.write(outDir.resolve("profile.jsonl"), sb.toString().getBytes("UTF-8"));
        } catch (Throwable t) {
            System.err.println("[mechdetect] flush failed: " + t);
        }
    }

    /** Delegating system Properties that attributes every write to the running test. */
    private static void hookProperties() {
        try {
            Properties logging = new Properties() {
                @Override
                public synchronized Object put(Object k, Object v) { log(k); return super.put(k, v); }
                @Override
                public synchronized Object remove(Object k) { log(k); return super.remove(k); }
                private void log(Object k) {
                    if (currentTest != null)
                        synchronized (propWrites) { propWrites.add(String.valueOf(k)); }
                }
            };
            for (Map.Entry<Object, Object> e : System.getProperties().entrySet()) logging.put(e.getKey(), e.getValue());
            System.setProperties(logging);
        } catch (Throwable t) {
            System.err.println("[mechdetect] property hook failed: " + t);
        }
    }

    /** Fingerprint static fields of loaded non-JDK classes; return changes since last walk. */
    private static List<String> walkStatics() {
        List<String> changes = new ArrayList<>();
        if (inst == null) return changes;
        for (Class<?> cls : inst.getAllLoadedClasses()) {
            String cn = cls.getName();
            if (cls.isArray() || cls.isPrimitive() || skip(cn) || !initialized(cls)) continue;
            Field[] fields = fieldCache.get(cls);
            if (fields == null) {
                try { fields = cls.getDeclaredFields(); } catch (Throwable t) { fields = new Field[0]; }
                fieldCache.put(cls, fields);
            }
            for (Field f : fields) {
                if (!Modifier.isStatic(f.getModifiers())) continue;
                String key = cn + "#" + f.getName(), fp = fingerprint(f), prev = fingerprints.put(key, fp);
                if (prev == null) {
                    // first sight: report non-final fields already holding data (a final field's
                    // content is its <clinit> default), and any ThreadLocal already holding a
                    // value — ThreadLocals start empty, so a present value was written in-window
                    boolean data = !Modifier.isFinal(f.getModifiers()) && fp != null
                            && (fp.contains(";S=") || (fp.startsWith("size=") && !fp.equals("size=0")));
                    boolean tl = fp != null && fp.startsWith("tl:") && !fp.startsWith("tl:absent");
                    if (data || tl) changes.add(key + "|<new>|" + fp);
                } else if (!Objects.equals(prev, fp)) {
                    changes.add(key + "|" + prev + "|" + fp);
                }
            }
        }
        return changes;
    }

    private static boolean skip(String cn) {
        return cn.startsWith("java.") || cn.startsWith("javax.") || cn.startsWith("jdk.")
                || cn.startsWith("sun.") || cn.startsWith("com.sun.") || cn.startsWith("mechdetect");
    }

    private static String fingerprint(Field f) {
        try {
            f.setAccessible(true);
            int[] sizes = new int[1];
            String fp = fp(f.get(null), 0, sizes);
            return sizes[0] > 0 ? fp + ";S=" + sizes[0] : fp;
        } catch (Throwable t) {
            return null;  // inaccessible: excluded from diffing
        }
    }

    /** Content-sensitive shallow fingerprint; descends two levels so state one hop inside an
     *  opaque holder object (a cache wrapper, a config singleton) still registers. Accumulates
     *  reachable collection sizes so a non-empty first sight is distinguishable. */
    private static String fp(Object v, int depth, int[] sizes) {
        try {
            if (v == null) return "null";
            if (v instanceof ThreadLocal) {
                Object inner = threadLocalValue((ThreadLocal<?>) v);
                return inner == null ? "tl:absent" : "tl:" + fp(inner, depth + 1, sizes);
            }
            Class<?> t = v.getClass();
            if (v instanceof String || v instanceof Number || v instanceof Boolean
                    || v instanceof Character || t.isEnum()) {
                String s = String.valueOf(v);
                return s.length() > 60 ? s.substring(0, 60) : s;
            }
            if (v instanceof Collection) { int n = ((Collection<?>) v).size(); sizes[0] += n; return "size=" + n; }
            if (v instanceof Map) { int n = ((Map<?, ?>) v).size(); sizes[0] += n; return "size=" + n; }
            if (t.isArray()) return "arr:" + java.lang.reflect.Array.getLength(v);
            String id = t.getName() + "@" + Integer.toHexString(System.identityHashCode(v));
            if (depth >= 2 || skip(t.getName())) return id;
            Field[] fields = instanceFields(t);
            if (fields.length == 0) return id;
            int hash = 0;
            for (Field f : fields) hash = hash * 31 + String.valueOf(fp(f.get(v), depth + 1, sizes)).hashCode();
            return id + ":" + Integer.toHexString(hash);
        } catch (Throwable t) {
            return "err";
        }
    }

    private static Field[] instanceFields(Class<?> t) {
        Field[] cached = instFieldCache.get(t);
        if (cached != null) return cached;
        List<Field> out = new ArrayList<>();
        try {
            for (Field f : t.getDeclaredFields())
                if (!Modifier.isStatic(f.getModifiers())) { f.setAccessible(true); out.add(f); }
        } catch (Throwable ignore) {}
        cached = out.toArray(new Field[0]);
        instFieldCache.put(t, cached);
        return cached;
    }

    /** Read a ThreadLocal's value for this thread WITHOUT triggering initialValue(). */
    private static Object threadLocalValue(ThreadLocal<?> tl) {
        try {
            Field mapField = Thread.class.getDeclaredField("threadLocals");
            mapField.setAccessible(true);
            Object map = mapField.get(Thread.currentThread());
            if (map == null) return null;
            Method getEntry = map.getClass().getDeclaredMethod("getEntry", ThreadLocal.class);
            getEntry.setAccessible(true);
            Object entry = getEntry.invoke(map, tl);
            if (entry == null) return null;
            Field value = entry.getClass().getDeclaredField("value");
            value.setAccessible(true);
            return value.get(entry);
        } catch (Throwable t) {
            return null;
        }
    }

    private static final ConcurrentHashMap<Class<?>, Boolean> initCache = new ConcurrentHashMap<>();
    private static Object unsafe;
    private static Method shouldBeInit;

    /** True when the class's static initializer has already run (never forces it). */
    private static boolean initialized(Class<?> cls) {
        if (Boolean.TRUE.equals(initCache.get(cls))) return true;
        try {
            if (unsafe == null) {
                Class<?> uc;
                try {
                    uc = Class.forName("sun.misc.Unsafe");
                    uc.getMethod("shouldBeInitialized", Class.class);
                } catch (NoSuchMethodException gone) {  // removed on modern JDKs
                    uc = Class.forName("jdk.internal.misc.Unsafe");
                }
                Field f = uc.getDeclaredField("theUnsafe");
                f.setAccessible(true);
                unsafe = f.get(null);
                shouldBeInit = uc.getMethod("shouldBeInitialized", Class.class);
            }
            boolean init = !(Boolean) shouldBeInit.invoke(unsafe, cls);
            if (init) initCache.put(cls, Boolean.TRUE);
            return init;
        } catch (Throwable t) {
            return false;  // cannot tell: stay safe, do not touch the class
        }
    }

    private static long jitMs() {
        try { return ManagementFactory.getCompilationMXBean().getTotalCompilationTime(); }
        catch (Throwable t) { return 0; }
    }

    private static long gcMs() {
        long ms = 0;
        for (java.lang.management.GarbageCollectorMXBean g : ManagementFactory.getGarbageCollectorMXBeans())
            if (g.getCollectionTime() > 0) ms += g.getCollectionTime();
        return ms;
    }

    private static long allocBytes() {
        try {
            com.sun.management.ThreadMXBean tb = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
            long sum = 0;
            for (long b : tb.getThreadAllocatedBytes(tb.getAllThreadIds())) if (b > 0) sum += b;
            return sum;
        } catch (Throwable t) { return 0; }
    }

    private static List<String> drain(List<String> list) {
        synchronized (list) {
            List<String> copy = new ArrayList<>(list);
            list.clear();
            return copy;
        }
    }

    private static void appendList(StringBuilder b, String key, List<String> values) {
        b.append(",\"").append(key).append("\":[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) b.append(',');
            b.append('"').append(esc(values.get(i))).append('"');
        }
        b.append(']');
    }

    /** JSON string escape incl. control characters (state values can hold anything). */
    private static String esc(String s) {
        StringBuilder o = new StringBuilder(s.length());
        for (char c : s.toCharArray()) {
            if (c == '\\') o.append("\\\\");
            else if (c == '"') o.append("\\\"");
            else if (c < 0x20 || c == 0x7f) o.append(String.format("\\u%04x", (int) c));
            else o.append(c);
        }
        return o.toString();
    }

    private Probes() {}
}
