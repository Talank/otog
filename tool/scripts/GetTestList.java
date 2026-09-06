import java.io.IOException;
import java.io.PrintWriter;
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.Charset;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Extract the test list (pkg.Class#method, one per line) from a module's
 * COMPILED test classes, using reflection -- without running a single test.
 *
 * Why this exists alongside get_test_list.py. That script reads surefire XML,
 * so it can only tell you what the suite contains AFTER you have run the suite.
 * That is circular: we need the test list in order to build the random orders
 * we want to run. This tool breaks the cycle -- compile the module, ask the
 * class files what tests they declare, generate orders from that.
 *
 * Usage:
 *   javac -d <tmp> GetTestList.java
 *   java -cp "<module test classpath>:<tmp>" GetTestList <test-classes-dir> <out-file>
 *
 * The module's FULL test classpath must be on -cp: reflecting on a class means
 * resolving its supertypes and annotations, which needs its dependencies.
 * scripts/extract_test_list.sh assembles that classpath with maven and calls us.
 *
 * Deliberately has no dependency of its own -- not even JUnit. Annotations are
 * matched BY NAME through Annotation#annotationType, so one build of this tool
 * handles JUnit 4, JUnit 5 and TestNG, and never has to agree with the version
 * of JUnit the subject happens to use.
 */
public final class GetTestList {

    /** A method carrying any of these is a test. Matched by name, never imported. */
    private static final Set<String> TEST_METHOD_ANNOTATIONS = new HashSet<String>(Arrays.asList(
            "org.junit.Test",                              // JUnit 4
            "org.junit.jupiter.api.Test",                  // JUnit 5
            "org.junit.jupiter.api.RepeatedTest",
            "org.junit.jupiter.api.TestFactory",
            "org.junit.jupiter.api.TestTemplate",
            "org.junit.jupiter.params.ParameterizedTest",
            "org.testng.annotations.Test"));               // TestNG

    /**
     * TestNG allows @Test on the CLASS, which promotes every public method to a
     * test -- except the lifecycle hooks. JUnit has no such rule, so this only
     * matters down the TestNG path.
     */
    private static final Set<String> TESTNG_LIFECYCLE_ANNOTATIONS = new HashSet<String>(Arrays.asList(
            "org.testng.annotations.BeforeSuite",
            "org.testng.annotations.AfterSuite",
            "org.testng.annotations.BeforeTest",
            "org.testng.annotations.AfterTest",
            "org.testng.annotations.BeforeGroups",
            "org.testng.annotations.AfterGroups",
            "org.testng.annotations.BeforeClass",
            "org.testng.annotations.AfterClass",
            "org.testng.annotations.BeforeMethod",
            "org.testng.annotations.AfterMethod",
            "org.testng.annotations.DataProvider",
            "org.testng.annotations.Factory"));

    /** How far to chase meta-annotations (@ApiTest -> @Test and the like). */
    private static final int MAX_ANNOTATION_DEPTH = 4;

    private static int classesScanned = 0;
    private static int classesUnloadable = 0;

    public static void main(String[] args) throws IOException {
        if (args.length < 2) {
            System.err.println("usage: GetTestList <test-classes-dir> <out-file>");
            System.exit(2);
        }

        Path testClassesDir = Paths.get(args[0]);
        Path outFile = Paths.get(args[1]);

        if (!Files.isDirectory(testClassesDir)) {
            System.err.println("not a directory: " + testClassesDir
                    + " (has the module been compiled?)");
            System.exit(2);
        }

        Set<String> tests = new TreeSet<String>();
        for (String className : findClassNames(testClassesDir)) {
            collectTestsFrom(className, tests);
        }

        Path parent = outFile.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        PrintWriter writer = new PrintWriter(Files.newBufferedWriter(outFile, Charset.forName("UTF-8")));
        try {
            for (String test : tests) {
                writer.println(test);
            }
        } finally {
            writer.close();
        }

        // A class that will not load is usually a missing classpath entry, and it
        // silently costs us every test in it -- so make it loud rather than
        // letting a short list look like a small module.
        if (classesUnloadable > 0) {
            System.err.println("WARNING: " + classesUnloadable + " of " + classesScanned
                    + " classes could not be loaded; the classpath is probably incomplete");
        }

        // Same shape as get_test_list.py's last line, so the two are diffable.
        System.out.println(tests.size() + " tests -> " + outFile);
    }

    /** Every class file under the directory, as a fully qualified class name. */
    private static List<String> findClassNames(final Path root) throws IOException {
        final List<String> names = new ArrayList<String>();

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                String fileName = file.getFileName().toString();
                if (!fileName.endsWith(".class")) {
                    return FileVisitResult.CONTINUE;
                }
                if (fileName.equals("package-info.class") || fileName.equals("module-info.class")) {
                    return FileVisitResult.CONTINUE;
                }

                String relative = root.relativize(file).toString();
                String className = relative
                        .substring(0, relative.length() - ".class".length())
                        .replace(java.io.File.separatorChar, '.')
                        .replace('/', '.');

                // Anonymous classes (Outer$1) are never test classes. Named inner
                // classes ARE kept: JUnit 5 @Nested lives in them, and surefire
                // reports those as Outer$Nested.
                if (isAnonymous(className)) {
                    return FileVisitResult.CONTINUE;
                }

                names.add(className);
                return FileVisitResult.CONTINUE;
            }
        });

        Collections.sort(names);
        return names;
    }

    private static boolean isAnonymous(String className) {
        int dollar = className.lastIndexOf('$');
        return dollar >= 0
                && dollar + 1 < className.length()
                && Character.isDigit(className.charAt(dollar + 1));
    }

    private static void collectTestsFrom(String className, Set<String> tests) {
        classesScanned++;

        Class<?> type;
        try {
            // initialize=false matters: we want to READ the class, not run its
            // static initializers. Some test classes spin up servers in theirs.
            type = Class.forName(className, false, GetTestList.class.getClassLoader());
        } catch (Throwable t) {
            // ClassNotFoundException, NoClassDefFoundError, LinkageError, ...
            classesUnloadable++;
            System.err.println("  could not load " + className + ": " + t);
            return;
        }

        if (!isCandidateClass(type)) {
            return;
        }

        boolean classLevelTestNg = hasClassLevelTestNgTest(type);

        for (Method method : uniqueMethods(type)) {
            if (isAnnotatedAsTest(method.getAnnotations())) {
                tests.add(type.getName() + "#" + method.getName());
            } else if (classLevelTestNg && isTestNgPromotedMethod(method)) {
                tests.add(type.getName() + "#" + method.getName());
            }
        }
    }

    private static boolean isCandidateClass(Class<?> type) {
        // Abstract classes are excluded on purpose: surefire does not run them
        // either. Their @Test methods still show up, attributed to each concrete
        // subclass, because uniqueMethods() walks up the hierarchy.
        return !type.isInterface()
                && !type.isAnnotation()
                && !type.isEnum()
                && !type.isSynthetic()
                && !type.isAnonymousClass()
                && !type.isLocalClass()
                && !Modifier.isAbstract(type.getModifiers());
    }

    /**
     * Declared methods of the class and of every superclass, with subclass
     * overrides winning. getMethods() would miss inherited protected/package
     * test methods, which JUnit does run.
     */
    private static List<Method> uniqueMethods(Class<?> type) {
        Map<String, Method> bySignature = new LinkedHashMap<String, Method>();

        for (Class<?> current = type; current != null && current != Object.class;
                current = current.getSuperclass()) {
            for (Method method : safeDeclaredMethods(current)) {
                if (method.isSynthetic() || method.isBridge()) {
                    continue;
                }
                if (Modifier.isAbstract(method.getModifiers())) {
                    continue;
                }

                String signature = method.getName() + Arrays.toString(method.getParameterTypes());
                if (!bySignature.containsKey(signature)) {
                    bySignature.put(signature, method);
                }
            }
        }

        return new ArrayList<Method>(bySignature.values());
    }

    private static Method[] safeDeclaredMethods(Class<?> type) {
        try {
            return type.getDeclaredMethods();
        } catch (Throwable t) {
            // A method signature referencing an absent type throws here rather
            // than at Class.forName. Same cause, same handling.
            classesUnloadable++;
            System.err.println("  could not read methods of " + type.getName() + ": " + t);
            return new Method[0];
        }
    }

    private static boolean hasClassLevelTestNgTest(Class<?> type) {
        for (Class<?> current = type; current != null && current != Object.class;
                current = current.getSuperclass()) {
            for (Annotation annotation : safeAnnotations(current)) {
                if ("org.testng.annotations.Test".equals(annotation.annotationType().getName())) {
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean isTestNgPromotedMethod(Method method) {
        if (!Modifier.isPublic(method.getModifiers())) {
            return false;
        }
        for (Annotation annotation : method.getAnnotations()) {
            if (TESTNG_LIFECYCLE_ANNOTATIONS.contains(annotation.annotationType().getName())) {
                return false;
            }
        }
        return true;
    }

    private static boolean isAnnotatedAsTest(Annotation[] annotations) {
        return isAnnotatedAsTest(annotations, new HashSet<String>(), 0);
    }

    /**
     * A project can define its own @IntegrationTest that is itself meta-annotated
     * with @Test, so matching only the direct annotations would miss those. The
     * visited set stops the cycles that annotations like @Retention create.
     */
    private static boolean isAnnotatedAsTest(Annotation[] annotations, Set<String> visited, int depth) {
        if (depth > MAX_ANNOTATION_DEPTH) {
            return false;
        }

        for (Annotation annotation : annotations) {
            Class<? extends Annotation> annotationType = annotation.annotationType();
            String name = annotationType.getName();

            if (TEST_METHOD_ANNOTATIONS.contains(name)) {
                return true;
            }
            if (name.startsWith("java.lang.annotation.") || name.startsWith("kotlin.")) {
                continue;
            }
            if (!visited.add(name)) {
                continue;
            }
            if (isAnnotatedAsTest(safeAnnotations(annotationType), visited, depth + 1)) {
                return true;
            }
        }

        return false;
    }

    private static Annotation[] safeAnnotations(Class<?> type) {
        try {
            return type.getAnnotations();
        } catch (Throwable t) {
            // An annotation whose own type is not on the classpath.
            return new Annotation[0];
        }
    }

    private GetTestList() {
    }
}
