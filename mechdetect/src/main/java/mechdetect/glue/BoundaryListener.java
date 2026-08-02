package mechdetect.glue;

import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.engine.support.descriptor.ClassSource;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;

/**
 * Harness glue: marks top-level test-class boundaries (depth counting collapses @Nested/inner
 * containers) and forwards them to the probes. Assumes sequential execution.
 */
public final class BoundaryListener implements TestExecutionListener {

    private int depth = 0;
    private String current;

    @Override
    public void executionStarted(TestIdentifier id) {
        if (id.isTest()) { mechdetect.Probes.methodStarted(); return; }
        if (!isClass(id)) return;
        if (depth++ == 0) {
            current = className(id);
            mechdetect.Probes.classStarted(current);
        }
    }

    @Override
    public void executionFinished(TestIdentifier id, TestExecutionResult result) {
        if (!isClass(id)) return;
        if (--depth == 0 && current != null) {
            mechdetect.Probes.classFinished(current, result.getStatus().name());
            current = null;
        }
    }

    @Override
    public void testPlanExecutionFinished(TestPlan plan) {
        mechdetect.Probes.flush();
    }

    private static boolean isClass(TestIdentifier id) {
        return id.getSource().map(s -> s instanceof ClassSource).orElse(false);
    }

    private static String className(TestIdentifier id) {
        return id.getSource().map(s -> s instanceof ClassSource ? ((ClassSource) s).getClassName() : null)
                .orElse(id.getLegacyReportingName());
    }
}
