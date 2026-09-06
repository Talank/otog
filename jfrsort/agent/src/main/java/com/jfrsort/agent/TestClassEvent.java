package com.jfrsort.agent;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;

/**
 * One event per top-level test class, spanning its execution: begin() at
 * container start, commit() at container finish, so the event's startTime and
 * duration define the class's attribution window in the recording.
 */
@Name("jfrsort.TestClass")
@Label("Test Class")
@Category("jfrsort")
@StackTrace(false)
public class TestClassEvent extends Event {
    @Label("Test Class")
    public String testClass;
}
