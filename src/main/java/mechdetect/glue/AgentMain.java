package mechdetect.glue;

import java.lang.instrument.Instrumentation;
import java.util.HashMap;
import java.util.Map;
import java.util.jar.JarFile;

/**
 * Harness glue: -javaagent entry point. Appends this jar to the system classloader so the JUnit
 * Platform ServiceLoader discovers {@link BoundaryListener}, then hands control to the probes.
 * Agent args: {@code out=<dir>} (comma-separated k=v).
 */
public final class AgentMain {

    public static void premain(String args, Instrumentation inst) {
        Map<String, String> opts = parse(args);
        try {
            String self = AgentMain.class.getProtectionDomain().getCodeSource().getLocation().toURI().getPath();
            if (self != null && self.endsWith(".jar")) inst.appendToSystemClassLoaderSearch(new JarFile(self));
        } catch (Throwable t) {
            System.err.println("[mechdetect] could not append agent jar: " + t);
        }
        if (!platformPresent()) {
            System.err.println("[mechdetect] JUnit Platform absent; boundaries unavailable (inject vintage via KP_DEPENDENCIES)");
            return;
        }
        try {
            mechdetect.Probes.install(inst, opts.get("out"));
            System.err.println("[mechdetect] active, out=" + opts.get("out"));
        } catch (Throwable t) {
            System.err.println("[mechdetect] probe install failed: " + t);
            t.printStackTrace();
        }
    }

    private static boolean platformPresent() {
        try {
            Class.forName("org.junit.platform.launcher.TestExecutionListener", false, AgentMain.class.getClassLoader());
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    private static Map<String, String> parse(String args) {
        Map<String, String> m = new HashMap<>();
        if (args == null || args.trim().isEmpty()) return m;
        for (String kv : args.split(",")) {
            int i = kv.indexOf('=');
            if (i > 0) m.put(kv.substring(0, i).trim(), kv.substring(i + 1).trim());
        }
        return m;
    }
}
