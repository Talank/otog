package com.jfrsort.agent;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.engine.support.descriptor.ClassSource;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;

/**
 * Emits a {@link TestClassEvent} spanning each top-level test class.
 * Only containers backed by a ClassSource whose class name has no '$' open a
 * window, so @Nested classes and test methods stay inside their top-level
 * class's window. Works for JUnit 5 and JUnit 4 via the vintage engine.
 */
public final class JfrsortListener implements TestExecutionListener {
    private final Map<String, TestClassEvent> open = new ConcurrentHashMap<>();

    @Override
    public void executionStarted(TestIdentifier id) {
        String cls = topLevelClass(id);
        if (cls == null) return;
        open.computeIfAbsent(cls, c -> {
            TestClassEvent e = new TestClassEvent();
            e.testClass = c;
            e.begin();
            return e;
        });
    }

    @Override
    public void executionFinished(TestIdentifier id, TestExecutionResult result) {
        String cls = topLevelClass(id);
        if (cls == null) return;
        TestClassEvent e = open.remove(cls);
        if (e != null) {
            e.end();
            e.commit();
        }
    }

    private static String topLevelClass(TestIdentifier id) {
        return id.getSource()
                .filter(ClassSource.class::isInstance)
                .map(s -> ((ClassSource) s).getClassName())
                .filter(n -> n.indexOf('$') < 0)
                .orElse(null);
    }
}
