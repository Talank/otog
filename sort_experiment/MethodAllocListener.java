package sortexp;

import java.io.BufferedWriter;
import java.io.FileWriter;
import java.lang.management.ManagementFactory;
import java.util.Optional;
import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.engine.support.descriptor.MethodSource;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;

/**
 * Records per-method allocated bytes (all threads) to a JSONL file named by -Dmethodalloc.out.
 * Auto-discovered by the JUnit Platform Launcher via META-INF/services, so it runs inside the real
 * Surefire fork (correct working dir, JDK, and JVM flags). Trace only; controls nothing about timing.
 */
public class MethodAllocListener implements TestExecutionListener {
    private final com.sun.management.ThreadMXBean tb =
            (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private final ThreadLocal<Long> start = new ThreadLocal<Long>();
    private BufferedWriter w;

    private long alloc() {
        long[] ids = tb.getAllThreadIds();
        long[] a = tb.getThreadAllocatedBytes(ids);
        long s = 0; for (long x : a) if (x > 0) s += x; return s;
    }

    public MethodAllocListener() {
        String out = System.getProperty("methodalloc.out");
        try { if (out != null) w = new BufferedWriter(new FileWriter(out, true)); } catch (Exception e) { }
    }

    @Override public void executionStarted(TestIdentifier id) {
        if (id.isTest()) start.set(alloc());
    }

    @Override public void executionFinished(TestIdentifier id, TestExecutionResult r) {
        if (!id.isTest() || w == null) return;
        Long s = start.get();
        long a = s == null ? 0 : Math.max(0, alloc() - s);
        Optional<org.junit.platform.engine.TestSource> src = id.getSource();
        if (!src.isPresent() || !(src.get() instanceof MethodSource)) return;
        MethodSource ms = (MethodSource) src.get();
        try {
            synchronized (w) {
                w.write("{\"test\":\"" + ms.getClassName() + "#" + ms.getMethodName()
                        + "\",\"allocBytes\":" + a + "}");
                w.newLine(); w.flush();
            }
        } catch (Exception e) { }
    }
}
