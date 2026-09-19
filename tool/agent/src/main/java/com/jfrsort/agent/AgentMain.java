package com.jfrsort.agent;

import java.io.File;
import java.lang.instrument.Instrumentation;
import java.util.jar.JarFile;

/**
 * Appends this jar to the system classloader so the JUnit Platform's
 * ServiceLoader can discover {@link JfrsortListener} inside the Surefire fork.
 * Loading in a JVM that never runs the JUnit Platform (e.g. the Maven
 * launcher, which also picks up JAVA_TOOL_OPTIONS) is harmless: the listener
 * class is never instantiated there.
 */
public final class AgentMain {
    public static void premain(String args, Instrumentation inst) throws Exception {
        File self = new File(AgentMain.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        inst.appendToSystemClassLoaderSearch(new JarFile(self));
    }
}
