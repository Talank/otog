package com.csto2.agent;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * Optional JFR test-class interval event implemented through reflection so the instrumentation
 * agent remains Java-8-loadable. On Java 11+ it registers a dynamic event named
 * {@code com.csto2.TestClass}; on Java 8 every method is a no-op.
 */
final class JfrTestClassEvent {
    private static final Support SUPPORT = Support.create();

    private JfrTestClassEvent() {}

    static Object begin(String order, int position, String test) {
        return SUPPORT.begin(order, position, test);
    }

    static void finish(
            Object event,
            String status,
            long allocBytes,
            long classesLoaded,
            long jitMs,
            long gcCount,
            long gcMs) {
        SUPPORT.finish(event, status, allocBytes, classesLoaded, jitMs, gcCount, gcMs);
    }

    private static final class Support {
        private final Object factory;
        private final Method newEvent;
        private final Method begin;
        private final Method end;
        private final Method commit;
        private final Method set;

        private Support(
                Object factory, Method newEvent, Method begin, Method end, Method commit, Method set) {
            this.factory = factory;
            this.newEvent = newEvent;
            this.begin = begin;
            this.end = end;
            this.commit = commit;
            this.set = set;
        }

        static Support create() {
            try {
                Class<?> annotationElement = Class.forName("jdk.jfr.AnnotationElement");
                Class<?> valueDescriptor = Class.forName("jdk.jfr.ValueDescriptor");
                Class<?> eventFactory = Class.forName("jdk.jfr.EventFactory");
                Class<?> event = Class.forName("jdk.jfr.Event");
                Class<?> name = Class.forName("jdk.jfr.Name");
                Class<?> label = Class.forName("jdk.jfr.Label");
                Class<?> category = Class.forName("jdk.jfr.Category");

                Constructor<?> annotationValue =
                        annotationElement.getConstructor(Class.class, Object.class);
                List<Object> annotations = new ArrayList<>();
                annotations.add(annotationValue.newInstance(name, "com.csto2.TestClass"));
                annotations.add(annotationValue.newInstance(label, "JUnit test class"));
                annotations.add(
                        annotationValue.newInstance(
                                category, new String[] {"CSTO2", "Test execution"}));

                Constructor<?> field = valueDescriptor.getConstructor(Class.class, String.class);
                List<Object> fields = new ArrayList<>();
                fields.add(field.newInstance(String.class, "order"));
                fields.add(field.newInstance(int.class, "position"));
                fields.add(field.newInstance(String.class, "test"));
                fields.add(field.newInstance(String.class, "status"));
                fields.add(field.newInstance(long.class, "allocBytes"));
                fields.add(field.newInstance(long.class, "classesLoaded"));
                fields.add(field.newInstance(long.class, "jitMs"));
                fields.add(field.newInstance(long.class, "gcCount"));
                fields.add(field.newInstance(long.class, "gcMs"));

                Object factory = eventFactory
                        .getMethod("create", List.class, List.class)
                        .invoke(null, annotations, fields);
                eventFactory.getMethod("register").invoke(factory);
                return new Support(
                        factory,
                        eventFactory.getMethod("newEvent"),
                        event.getMethod("begin"),
                        event.getMethod("end"),
                        event.getMethod("commit"),
                        event.getMethod("set", int.class, Object.class));
            } catch (Throwable ignored) {
                return new Support(null, null, null, null, null, null);
            }
        }

        Object begin(String order, int position, String test) {
            if (factory == null) return null;
            try {
                Object event = newEvent.invoke(factory);
                set.invoke(event, 0, order);
                set.invoke(event, 1, Integer.valueOf(position));
                set.invoke(event, 2, test);
                begin.invoke(event);
                return event;
            } catch (Throwable ignored) {
                return null;
            }
        }

        void finish(
                Object event,
                String status,
                long allocBytes,
                long classesLoaded,
                long jitMs,
                long gcCount,
                long gcMs) {
            if (event == null) return;
            try {
                set.invoke(event, 3, status);
                set.invoke(event, 4, Long.valueOf(allocBytes));
                set.invoke(event, 5, Long.valueOf(classesLoaded));
                set.invoke(event, 6, Long.valueOf(jitMs));
                set.invoke(event, 7, Long.valueOf(gcCount));
                set.invoke(event, 8, Long.valueOf(gcMs));
                end.invoke(event);
                commit.invoke(event);
            } catch (Throwable ignored) {
                // Profiling must never make the test suite fail.
            }
        }
    }
}
