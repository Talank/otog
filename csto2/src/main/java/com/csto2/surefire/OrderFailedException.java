package com.csto2.surefire;

import java.util.List;

/**
 * Thrown by {@link SurefireOrchestrator#runOrder} the instant an order run is not fully green -- any
 * failing/erroring test class, or a crashed/incomplete fork (a class that produced no report at all).
 *
 * <p>csto2 fails early on this: the caller drops the offending order/strategy from all further
 * measurement and from the report rather than measuring a doomed candidate to completion or (worse)
 * crediting its truncated total as a speedup.
 */
public class OrderFailedException extends RuntimeException {
    private final String orderId;
    private final List<String> failedClasses;   // FAIL/TIMEOUT/MISSING class names
    private final int exitCode;

    public OrderFailedException(String orderId, List<String> failedClasses, int exitCode) {
        super("order " + orderId + " not green (mvn exit=" + exitCode + "): "
                + (failedClasses.isEmpty() ? "fork failed" : String.join(", ", failedClasses)));
        this.orderId = orderId;
        this.failedClasses = failedClasses;
        this.exitCode = exitCode;
    }

    public String orderId() { return orderId; }
    public List<String> failedClasses() { return failedClasses; }
    public int exitCode() { return exitCode; }
}
