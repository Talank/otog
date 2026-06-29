package com.csto2.surefire;

import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Reproduces Maven Surefire's test-class <em>selection</em> from a module's {@code pom.xml}, so the
 * candidate test list we hand the pipeline matches what {@code mvn test} would actually run.
 *
 * <p>Reads the {@code maven-surefire-plugin} {@code <includes>}/{@code <excludes>} from the module
 * pom (preferring {@code build/plugins}, falling back to {@code build/pluginManagement/plugins}). When
 * the pom configures no includes, Surefire's built-in defaults are used:
 * <pre>
 *   **&#47;Test*.java   **&#47;*Test.java   **&#47;*Tests.java   **&#47;*TestCase.java
 * </pre>
 *
 * <p>Patterns are Ant globs. Surefire maps the {@code *.java} patterns onto the compiled
 * {@code *.class} files it scans, so we do the same: a glob's trailing {@code .java} becomes
 * {@code .class} and is matched against the class-file path relative to {@code target/test-classes}
 * (always with {@code /} separators). A class is selected when it matches any include and no exclude.
 *
 * <p>Best-effort: property interpolation ({@code ${...}}), profiles, parent-pom inheritance, and
 * {@code includesFile}/{@code excludesFile} are not resolved — only the module pom's own static
 * surefire config. Surefire's implicit inner-class exclusion is handled by the caller (it already
 * drops {@code $}-bearing names).
 */
public final class SurefireTestFilter {

    /** Surefire's built-in default includes, used when a project configures none. */
    public static final List<String> DEFAULT_INCLUDES = List.of(
            "**/Test*.java", "**/*Test.java", "**/*Tests.java", "**/*TestCase.java");

    public final List<String> includeGlobs;
    public final List<String> excludeGlobs;
    /** True when no {@code <includes>} were found in the pom and the Surefire defaults are in effect. */
    public final boolean usedDefaultIncludes;

    private final List<Pattern> includePatterns;
    private final List<Pattern> excludePatterns;

    private SurefireTestFilter(List<String> includeGlobs, List<String> excludeGlobs, boolean usedDefaultIncludes) {
        this.includeGlobs = includeGlobs;
        this.excludeGlobs = excludeGlobs;
        this.usedDefaultIncludes = usedDefaultIncludes;
        this.includePatterns = compile(includeGlobs);
        this.excludePatterns = compile(excludeGlobs);
    }

    /** Build a filter from a module's {@code pom.xml}, falling back to Surefire defaults on any error. */
    public static SurefireTestFilter fromPom(Path pomXml) {
        List<String> inc = new ArrayList<>();
        List<String> exc = new ArrayList<>();
        try {
            Element cfg = surefireConfiguration(pomXml);
            if (cfg != null) {
                inc.addAll(values(cfg, "includes", "include"));
                exc.addAll(values(cfg, "excludes", "exclude"));
            }
        } catch (Exception ignored) {
            // Malformed pom or no XML access — fall through to defaults.
        }
        boolean usedDefaults = inc.isEmpty();
        if (usedDefaults) inc = new ArrayList<>(DEFAULT_INCLUDES);
        return new SurefireTestFilter(inc, exc, usedDefaults);
    }

    /** True when the class-file path (relative to test-classes, '/'-separated) is a Surefire test. */
    public boolean matches(String relClassPath) {
        String p = relClassPath.replace('\\', '/');
        for (Pattern e : excludePatterns) if (e.matcher(p).matches()) return false;
        for (Pattern i : includePatterns) if (i.matcher(p).matches()) return true;
        return false;
    }

    // ---- pom parsing -----------------------------------------------------------------------------

    private static Element surefireConfiguration(Path pomXml) throws Exception {
        if (pomXml == null || !pomXml.toFile().isFile()) return null;
        DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
        f.setNamespaceAware(false); // poms commonly omit it, but be tolerant of either
        org.w3c.dom.Document doc = f.newDocumentBuilder().parse(pomXml.toFile());
        Element project = doc.getDocumentElement();
        if (project == null) return null;
        Element build = child(project, "build");
        if (build == null) return null;
        // Active config lives in build/plugins; pluginManagement only supplies defaults.
        Element cfg = surefireConfigIn(child(build, "plugins"));
        if (cfg == null) cfg = surefireConfigIn(child(child(build, "pluginManagement"), "plugins"));
        return cfg;
    }

    private static Element surefireConfigIn(Element plugins) {
        if (plugins == null) return null;
        for (Element plugin : children(plugins, "plugin")) {
            String artifact = text(child(plugin, "artifactId"));
            if ("maven-surefire-plugin".equals(artifact)) return child(plugin, "configuration");
        }
        return null;
    }

    /** Collect the text of every {@code <wrapper><item>...} grandchild, trimmed and non-blank. */
    private static List<String> values(Element cfg, String wrapper, String item) {
        List<String> out = new ArrayList<>();
        Element w = child(cfg, wrapper);
        if (w == null) return out;
        for (Element e : children(w, item)) {
            String v = text(e);
            if (v != null && !v.isBlank()) out.add(v.trim());
        }
        return out;
    }

    // ---- glob -> regex ---------------------------------------------------------------------------

    private static List<Pattern> compile(List<String> globs) {
        List<Pattern> out = new ArrayList<>();
        for (String g : globs) out.add(Pattern.compile(antToRegex(toClassGlob(g))));
        return out;
    }

    /** Surefire scans .class files, so a *.java pattern selects the matching *.class file. */
    private static String toClassGlob(String glob) {
        return glob.endsWith(".java") ? glob.substring(0, glob.length() - ".java".length()) + ".class" : glob;
    }

    /**
     * Translate an Ant-style path glob to a regex: {@code **&#47;} spans any number of directories
     * (including none), {@code **} spans anything, {@code *} any run of non-separator chars, {@code ?}
     * one non-separator char.
     */
    static String antToRegex(String glob) {
        StringBuilder sb = new StringBuilder("^");
        for (int i = 0; i < glob.length(); i++) {
            char c = glob.charAt(i);
            if (c == '*') {
                boolean dbl = i + 1 < glob.length() && glob.charAt(i + 1) == '*';
                if (dbl) {
                    boolean slash = i + 2 < glob.length() && glob.charAt(i + 2) == '/';
                    if (slash) { sb.append("(?:[^/]*/)*"); i += 2; } // **/ -> zero or more dir segments
                    else { sb.append(".*"); i += 1; }
                } else {
                    sb.append("[^/]*");
                }
            } else if (c == '?') {
                sb.append("[^/]");
            } else if ("\\.[]{}()+-^$|".indexOf(c) >= 0) {
                sb.append('\\').append(c);
            } else {
                sb.append(c);
            }
        }
        return sb.append('$').toString();
    }

    // ---- tiny DOM helpers ------------------------------------------------------------------------

    private static Element child(Element parent, String name) {
        if (parent == null) return null;
        for (Element e : children(parent, name)) return e;
        return null;
    }

    private static List<Element> children(Element parent, String name) {
        List<Element> out = new ArrayList<>();
        if (parent == null) return out;
        NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node n = nodes.item(i);
            if (n.getNodeType() == Node.ELEMENT_NODE && localName(n).equals(name)) out.add((Element) n);
        }
        return out;
    }

    private static String localName(Node n) {
        String ln = n.getLocalName();
        if (ln != null) return ln;
        String nn = n.getNodeName();
        int colon = nn.indexOf(':');
        return colon < 0 ? nn : nn.substring(colon + 1);
    }

    private static String text(Element e) {
        return e == null ? null : e.getTextContent();
    }
}
