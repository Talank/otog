# JIT vs. Alloc Overlap Analysis

This report documents the correlation and overlap between the heaviest memory allocators (targeted by `alloc-front` / `alloc-sort`) and the heaviest JIT compilation tests (targeted by `jit-front` / `jit-sort`) across four target modules.

## Overlap Findings (Top 10 Classes)

Across all scanned modules, there is a consistent **70% to 90% overlap** between the top 10 allocators and the top 10 compilation-heavy test classes.

---

### 1. `javaparser-core-testing`
*   **Total Tracked Tests**: 287
*   **Overlap in Top 10**: **7 / 10 (70%)**
*   **Shared Top 10 Classes**:
    *   `JavadocExtractorTest` (Alloc Rank #1, JIT Rank #1)
    *   `BulkParseTest` (Alloc Rank #2, JIT Rank #2)
    *   `Issue2627Test` (Alloc Rank #3, JIT Rank #3)
    *   `GenericVisitorWithDefaultsTest` (Alloc Rank #6, JIT Rank #4)
    *   `GenericListVisitorAdapterTest` (Alloc Rank #4, JIT Rank #5)
    *   `ParserCollectionStrategyTest` (Alloc Rank #5, JIT Rank #6)
    *   `ObjectIdentityHashCodeVisitorTest` (Alloc Rank #7, JIT Rank #8)

---

### 2. `javaparser-symbol-solver-testing`
*   **Total Tracked Tests**: 294
*   **Overlap in Top 10**: **9 / 10 (90%)**
*   **Shared Top 10 Classes**:
    *   `SymbolSolverCollectionStrategyTest` (Alloc Rank #3, JIT Rank #1)
    *   `JavaParserClassDeclarationTest` (Alloc Rank #1, JIT Rank #2)
    *   `JavaParserTypeSolverTest` (Alloc Rank #5, JIT Rank #3)
    *   `JavaParserEnumDeclarationTest` (Alloc Rank #4, JIT Rank #4)
    *   `SymbolSolverTest` (Alloc Rank #6, JIT Rank #5)
    *   `Issue3038Test` (Alloc Rank #8, JIT Rank #6)
    *   `JavaParserInterfaceDeclarationTest` (Alloc Rank #2, JIT Rank #7)
    *   `MethodReferenceResolutionTest` (Alloc Rank #9, JIT Rank #8)
    *   `MethodsResolutionLogicTest` (Alloc Rank #7, JIT Rank #9)

---

### 3. `commons-lang`
*   **Total Tracked Tests**: 394
*   **Overlap in Top 10**: **8 / 10 (80%)**
*   **Shared Top 10 Classes**:
    *   `ExtendedMessageFormatTest` (Alloc Rank #3, JIT Rank #1)
    *   `FastDateParserTest` (Alloc Rank #2, JIT Rank #2)
    *   `FastDateParser_TimeZoneStrategyTest` (Alloc Rank #1, JIT Rank #3)
    *   `FastDateParserJava15BugTest` (Alloc Rank #6, JIT Rank #4)
    *   `DurationFormatUtilsTest` (Alloc Rank #4, JIT Rank #5)
    *   `HashCodeBuilderAndEqualsBuilderTest` (Alloc Rank #10, JIT Rank #6)
    *   `LocaleUtilsTest` (Alloc Rank #7, JIT Rank #7)
    *   `ClassUtilsOssFuzzTest` (Alloc Rank #5, JIT Rank #10)

---

### 4. `commons-text`
*   **Total Tracked Tests**: 24
*   **Overlap in Top 10**: **7 / 10 (70%)**
*   **Shared Top 10 Classes**:
    *   `ExtendedMessageFormatTest` (Alloc Rank #1, JIT Rank #1)
    *   `StringSubstitutorWithInterpolatorStringLookupTest` (Alloc Rank #4, JIT Rank #2)
    *   `ResourceBundleStringLookupTest` (Alloc Rank #6, JIT Rank #3)
    *   `OssFuzzTest` (Alloc Rank #2, JIT Rank #4)
    *   `TextStringBuilderAppendInsertTest` (Alloc Rank #5, JIT Rank #5)
    *   `StringEscapeUtilsTest` (Alloc Rank #3, JIT Rank #7)
    *   `RandomStringGeneratorTest` (Alloc Rank #8, JIT Rank #9)

---

## Physical Rationale

The heavy overlap is driven by physical execution patterns inside the JVM:
1.  **Code Path Scope**: Test suites that execute deep code paths (e.g., parsing large codebases, complex symbol resolution, or text formatting benchmarks) trigger massive class loading and JIT compiling overhead (`jitMs`).
2.  **Allocation Overhead**: The same complex execution paths construct large numbers of short-lived objects (such as ASTs, type mappings, or string builders), resulting in very high allocation metrics (`allocBytes`).
3.  **Optimization Consequence**: Because the top allocators are also the top JIT targets, front-loading them warms up JIT compilation and resolves class loading early for the entire suite, while also placing them on a clean, low-fragmentation heap.

---

## Comparison of pkg-alloc-front vs pkg-rt-front

The package-level candidate orders `pkg-alloc-front` and `pkg-rt-front` share an identical first 6 classes because the packages `com.github.javaparser.javadoc`, `com.github.javaparser.manual`, and `com.github.javaparser.issues` rank highest on both aggregate allocation and runtime metrics.

### Package-Level Metrics (Javaparser Core)

| Package | Agg. Alloc (Rank) | Agg. Runtime (Rank) |
|---|---|---|
| `com.github.javaparser.javadoc` | 7432.73 MB (**#1**) | 5361.00 ms (**#1**) |
| `com.github.javaparser.manual` | 3714.27 MB (**#2**) | 1968.00 ms (**#2**) |
| `com.github.javaparser.issues` | 1820.01 MB (**#3**) | 1018.50 ms (**#3**) |
| `com.github.javaparser.utils` | 203.44 MB (**#4**) | 323.50 ms (**#5**) |
| `com.github.javaparser.ast.visitor` | 165.66 MB (**#6**) | 482.50 ms (**#4**) |
| `com.github.javaparser.printer.lexicalpreservation` | 200.84 MB (**#5**) | 261.50 ms (**#6**) |

The sequences diverge at the 7th class due to ranking differences in subsequent packages:
*   `pkg-alloc-front` positions `com.github.javaparser.utils` 4th and `com.github.javaparser.printer.lexicalpreservation` 5th.
*   `pkg-rt-front` positions `com.github.javaparser.ast.visitor` 4th and `com.github.javaparser.utils` 5th.
