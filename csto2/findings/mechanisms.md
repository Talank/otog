# Mechanisms That Change Test-Suite Run Time

Date: 2026-07-30

## 1. Purpose

This report describes mechanisms that make one test order faster than another test order.
The report uses measured examples.
The report also gives the exact code flow for each example.

This report uses these terms:

- A **test fork** is one Java Virtual Machine (JVM) process that runs tests.
- A **producer** is a test that changes shared process state.
- A **consumer** is a later test that uses that state.
- **Persistent state** is state that stays after one test class ends.
- **Cold state** means that a class or a code path did not run in the test fork.
- **Warm state** means that an earlier test initialized the class or the code path.
- A **green order** is an order in which all tests pass.
- A **baseline run** uses the original project code.

All confirmed examples use one reused test fork.
The mechanisms do not cross a new JVM process.

For some checks, this study changes one item in the code that may cause the difference.
For example, a check can clear one cache or stop compilation of one class.
The changed run is not part of the baseline result.
Instead, if the original time gap becomes much smaller, the result supports the
proposed cause.

The general model is:

```text
producer -> persistent state -> consumer -> run-time change
```

Not all mechanisms have one producer.
Many small tests can make a later consumer warm.

## 2. Summary of confirmed mechanisms

| Mechanism | Project | Measured effect | Direction |
|---|---|---:|---|
| Retained shared cache | OpenPojo | 59.57% lower pair run time in the paper | Run the cache consumer before the cache producer |
| Leaked semantic configuration | JavaParser | Polluted pair is 3.56 times slower | Run the configuration producer after its consumers |
| Shared first-use initialization | SnakeYAML | Warm order is 5.72% faster across 20 pairs | Run cheap initializers before large consumers |
| Shared optimized code | JavaParser symbol solver | Moving one consumer to the end saves 4.73% | Run a large repeated consumer after tests that compile its code paths |
| Persistent inline-mock instrumentation | Commons Text | The instrumented consumer is 2.04 times slower | Run tests that mock a hot type after its large consumers |
| Cached diagnostic policy | AsyncHttpClient | The fast two-class median is 35.58% lower | Initialize Netty before a test enables `PARANOID`, or set the level at JVM start |
| Leaked connection policy | AsyncHttpClient | `allowPooling -> maxRedirects` has a 13.95% lower median | Clear the property cache after a test restores a property |
| Shared iterator optimization | Gson | `LinkedTreeMap -> JsonObject` has a 4.33% lower median on Java 8 | Run the larger generated map suite before the smaller suite |
| Compiler-queue delay plus recursive-map uncommon trap | SnakeYAML | `References -> Stress` has a 518.5 ms lower paired median across 12 Java 8 pairs | Run the recursive-map test before the compiler-heavy emitter test |
| Java 8 compact-notation regular expression | SnakeYAML | Moving one class to the front has a 567.5 ms lower paired median across 10 Java 8 pairs | Run the compact-notation error test before the other 348 classes |

## 3. OpenPojo: retained shared cache

One test fills a shared cache with thousands of entries, and a
later test that scans the whole package must work through that retained cache,
so the scan is faster when it runs before the cache is filled.

### 3.1 Result

The paper compares these two orders:

```text
slow: IdentityFactoryRaceConditionTest -> StructuralTest
fast: StructuralTest -> IdentityFactoryRaceConditionTest
```

The slow order takes approximately 5.54 seconds.
The fast order takes approximately 2.24 seconds.
The paper reports a 59.57% run-time reduction.

### 3.2 Producer

`IdentityFactoryRaceConditionTest.runWithManyThreads` creates 1,500 worker threads.
See `openpojo/src/test/java/com/openpojo/business/identity/impl/IdentityFactoryRaceConditionTest.java:48-68`.

Each worker calls `PojoClassFactory.getPojoClass`.
See the same file at lines 107-111.

The call flow is:

```text
IdentityFactoryRaceConditionTest.runWithManyThreads
  -> Worker.run
  -> PojoClassFactory.getPojoClass
  -> DefaultPojoClassLookupService.getPojoClass
  -> PojoCache.getPojoClass
  -> construct PojoClassImpl on a cache miss
  -> PojoCache.addPojoClass
```

`PojoClassFactory.getPojoClass` selects the registered lookup service.
See `openpojo/src/main/java/com/openpojo/reflection/impl/PojoClassFactory.java:41-43`.

`DefaultPojoClassLookupService.getPojoClass` reads the shared cache at line 64.
It constructs metadata at lines 65-73.
It writes the result to the cache at line 74.
See `openpojo/src/main/java/com/openpojo/reflection/service/impl/DefaultPojoClassLookupService.java:63-76`.

`PojoCache` stores the shared cache in a static field.
See `openpojo/src/main/java/com/openpojo/reflection/cache/PojoCache.java:30-32`.
Its `getPojoClass`, `addPojoClass`, and `clear` methods are at lines 40-61.

### 3.3 Consumer

`StructuralTest.allTestsMustEndWithTest` scans the complete `com.openpojo` package.
See `openpojo/src/test/java/com/openpojo/StructuralTest.java:98-102`.

This scan calls the same class lookup service.
The scan reads and changes the same `PojoCache`.

The paper reports that the cache is cleared between the classes in the fast order.
The cache is not cleared between the classes in the slow order.
The retained cache makes the later structural scan slower.

### 3.4 Abstraction

This is a retained-data mechanism.
The producer puts many entries in a shared cache.
The consumer traverses a large class set and uses the same cache.
More retained data does not always make a consumer faster.
The data structure can add lookup, reference, cleanup, or memory-management cost.

The directed order constraint is:

```text
StructuralTest -> IdentityFactoryRaceConditionTest
```

The paper provides this example.
The current study did not repeat its experiment.

## 4. JavaParser: leaked lexical-preservation configuration

One test switches the shared parser into an expensive mode and
never switches it back, so every later test that parses pays for extra work it
does not use.

### 4.1 Result

The experiment uses two classes:

```text
clean:    JavadocExtractorTest -> Issue4488Test
polluted: Issue4488Test -> JavadocExtractorTest
```

Five interleaved runs were green.

| Order | Run times | Median |
|---|---:|---:|
| Clean | 3602, 3899, 4052, 5007, 5582 ms | 4052 ms |
| Polluted | 13801, 14259, 14669, 14415, 20259 ms | 14415 ms |

The polluted median is 3.56 times the clean median.
The median penalty is 10.36 seconds.

### 4.2 Producer

`Issue4488Test` creates a parser configuration.
The test enables lexical preservation.
The test installs the configuration in `StaticJavaParser`.
See:

`javaparser-core-testing/src/test/java/com/github/javaparser/printer/lexicalpreservation/Issue4488Test.java:16-18`.

The test does not restore the old configuration.

`StaticJavaParser` stores the configuration in a static `ThreadLocal`.
A `ThreadLocal` is state that belongs to one thread.
See:

`javaparser-core/src/main/java/com/github/javaparser/StaticJavaParser.java:52-54`.

The getter is at lines 69-71.
The setter is at lines 77-80.

Surefire runs both classes on the same test thread.
Thus, the configuration stays after `Issue4488Test` ends.

The producer flow is:

```text
Issue4488Test
  -> ParserConfiguration.setLexicalPreservationEnabled(true)
  -> StaticJavaParser.setConfiguration
  -> ThreadLocal.set
```

### 4.3 Consumer

`JavadocExtractorTest.canParseAllJavadocsInJavaParser` starts a recursive scan at the parent directory.
See:

`javaparser-core-testing/src/test/java/com/github/javaparser/javadoc/JavadocExtractorTest.java:36-39`.

`processDir` visits each subdirectory.
It sends each Java file to `processFile`.
See the same file at lines 56-63.

`processFile` calls the static parser at line 43.
Thus, this test reads the configuration that the producer left in the test thread.

The parser runs a post-processor after each successful parse.
The post-processor checks the lexical-preservation flag.
It calls `LexicalPreservingPrinter.setup` when the flag is true.
See:

`javaparser-core/src/main/java/com/github/javaparser/ParserConfiguration.java:361-370`.

The exact consumer flow is:

```text
JavadocExtractorTest.canParseAllJavadocsInJavaParser
  -> processDir
  -> processFile for each Java file
  -> StaticJavaParser.parse
  -> ParserConfiguration post-processor
  -> LexicalPreservingPrinter.setup
  -> LexicalPreservingPrinter.storeInitialText
  -> Node.findByRange
  -> Node.isPhantom
```

The Javadoc test does not use the lexical printer.
Thus, the extra tree work has no value for this test.

### 4.4 Profile evidence

| Javadoc test state | Run time | Allocated memory | Garbage collection |
|---|---:|---:|---:|
| Clean | 8.438 s | 3.62 GiB | 13 events and 188 ms |
| Polluted | 27.532 s | 30.89 GiB | 59 events and 627 ms |

The polluted interval has these execution samples:

- 2,567 samples have `Node.findByRange` as the first application frame.
- 1,158 samples have `Node.isPhantom` as the first application frame.
- 257 samples have `storeInitialTextForOneNode` as the first application frame.

The clean interval does not have these paths.

Garbage collection uses 627 ms in the polluted interval.
The measured interval difference is 19.1 seconds.
Thus, garbage collection is a result of the extra tree work.
It is not the main cause.

### 4.5 Abstraction

This is a semantic-configuration mechanism.
The producer changes the meaning of each later parse.
The consumer repeats the changed operation over a large input set.
The consumer amplifies one small state leak.

The harmful edge is:

```text
Issue4488Test
  -- enables lexical preservation -->
later StaticJavaParser consumers
```

The best fix is to restore the old configuration.
If a source fix is not possible, CSTO2 must put this producer after its consumers.

## 5. SnakeYAML: shared first-use initialization

The first test to use a library path pays its one-time
class-loading and setup cost; when many small tests run first, they pay those
costs in small pieces, and the big tests that repeat the same operations
thousands of times run cheaper.

### 5.1 Result

Both complete-suite orders contain the same 349 test classes.
The cold order puts ten large consumers first.
The warm order puts the same ten consumers after 339 other tests.
The ten consumers keep the same internal order.

Across 20 paired runs:

- The cold total is 63,663 ms.
- The warm total is 60,021 ms.
- The warm order saves 3,642 ms.
- The mean saving is 5.72%.
- The warm order wins 18 of 20 pairs.
- The two-sided sign-test value is approximately 0.0004.

The raw measurements are in:

The largest repeatable class effects are:

| Consumer | Mean saving | Warm wins |
|---|---:|---:|
| `PyEmitterTest` | 68.2 ms | 20 of 20 |
| `BigDataLoadTest` | 53.0 ms | 19 of 20 |
| `ReferencesTest` | 46.5 ms | 17 of 20 |
| `PrintableUnicodeTest` | 37.2 ms | 14 of 20 |
| `JacksonTest` | 15.9 ms | 19 of 20 |
| `VelocityTest` | 9.2 ms | 13 of 20 |
| `PyStructureTest` | 6.0 ms | 19 of 20 |

The effect is not equal for all classes.
The effect is in tests that repeat common YAML operations.

### 5.2 `PyEmitterTest` execution flow

`PyEmitterTest._testEmitter` reads each PyYAML fixture.
It parses the fixture into events.
It emits the events to text.
It parses the new text.
It compares all events.

See:

`snakeyaml/src/test/java/org/pyyaml/PyEmitterTest.java:57-117`.

`testEmitterStyles` repeats parse and emit operations for many style combinations.
See the same file at lines 120-175 and later.

The exact application flow is:

```text
PyEmitterTest._testEmitter or testEmitterStyles
  -> StreamReader
  -> ParserImpl.peekEvent or ParserImpl.getEvent
  -> ScannerImpl.checkToken
  -> ScannerImpl.fetchMoreTokens
  -> ParserImpl.parseNode
  -> parser-state produce methods
  -> Emitter.emit
  -> Emitter.expectNode
  -> Emitter.processTag
  -> Emitter.analyzeScalar
  -> Emitter write methods
```

### 5.3 Other large consumers

`StressEmitterTest.testPerformance` first loads an object graph.
It then makes 6,001 dump calls.
It reuses one `Yaml` object for some calls.
It creates a new `Yaml` object for other calls.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/stress/StressEmitterTest.java:33-73`.

The flow is:

```text
Yaml.loadAs
  -> ParserImpl
  -> Composer
  -> BaseConstructor

Yaml.dump or Yaml.dumpAsMap
  -> Representer.representJavaBean
  -> Serializer.serializeNode
  -> Emitter.emit
```

`BigDataLoadTest` creates 5,000 beans.
It writes them into one large YAML document.
It parses the document two times.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/issues/issue102/BigDataLoadTest.java`.

This test uses the same representer, serializer, emitter, reader, scanner, parser, and constructor paths.

### 5.4 Profile evidence

The profiles are for cause attribution.
The unprofiled paired runs give the effect size.

For `PyEmitterTest`:

| Position | Run time | Class-load events | Allocation | Compiler time |
|---|---:|---:|---:|---:|
| First | 217 ms | 234 | 69.9 MiB | 989 ms |
| After 339 tests | 99 ms | 2 | 62.9 MiB | 386 ms |

The cold test loads parser-state classes.
It loads scanner-token classes.
It loads emitter-state classes.
It also loads reader, character-set, tag, URI, constructor, and JUnit support classes.

The warm test loads only two application classes in the measured interval.
Earlier small tests loaded the other classes.

A separate check disables the just-in-time (JIT) compiler with `-Xint`.
The results are:

- `PyEmitterTest` takes 2,653 ms when cold and 2,586 ms when warm.
- `BigDataLoadTest` takes 42,589 ms when cold and 42,222 ms when warm.
- `PrintableUnicodeTest` takes 44,292 ms when cold and 44,155 ms when warm.

The `PyEmitterTest` saving is 67 ms without the JIT compiler.
Its normal mean saving is 68.2 ms.
Thus, first-use class and static initialization is the main cause for this class.
The JIT compiler can still affect other consumers.

### 5.5 Abstraction

This is a many-to-one initialization mechanism.
Many small tests initialize parts of one shared library path.
A later high-volume consumer uses the initialized path many times.

The useful order pattern is:

```text
cheap tests with shared YAML paths
  -> initialize classes and static state
  -> large repeated YAML consumers
```

CSTO2 must measure application-call-path overlap.
It must also measure the cost of a possible predecessor.
A cheap predecessor with high path overlap is useful.
A costly predecessor with low path overlap is not useful.

This mechanism does not support a rule that puts all costly tests first.

## 6. JavaParser symbol solver: shared optimized code

Earlier tests make the JVM compile the parser into fast machine
code, so a test that parses heavily is much faster at the end of the suite than
at the start, where it must run the parser in slow, not-yet-compiled form.

### 6.1 Result

The experiment uses the complete symbol-solver suite.
Both orders contain the same 257 classes.
Only `JavaParserTypeSolverTest` moves.

```text
cold order: JavaParserTypeSolverTest -> the other 256 classes
warm order: the other 256 classes -> JavaParserTypeSolverTest
```

Three interleaved pairs were green.

| Order | Suite run times | Median |
|---|---:|---:|
| Cold | 19144, 18386, 17999 ms | 18386 ms |
| Warm | 17517, 17811, 15924 ms | 17517 ms |

The warm order is 4.73% faster.
The median for `JavaParserTypeSolverTest` is 2,098 ms in the cold order.
It is 1,624 ms in the warm order.
The class is 22.6% faster in the warm order.

This local result supports an earlier remote result.
The remote optimized order is 16.8% faster than its initial order across ten pairs.
The complete remote gain has more than one class contribution.
This section makes a causal claim only for the one-class move.

### 6.2 Consumer execution flow

`JavaParserTypeSolverTest` creates a type solver for a JavaParser source tree.
See:

`javaparser-symbol-solver-testing/src/test/java/com/github/javaparser/symbolsolver/resolution/typesolvers/JavaParserTypeSolverTest.java:44-50`.

The test class contains a test that JUnit repeats 25 times.
See the same file at lines 162-191.

Each repetition creates a new `JavaParserTypeSolver`.
It starts four `CompletableFuture` tasks.
Each task calls `tryToSolveType` on the same solver.

The exact test flow is:

```text
JavaParserTypeSolverTest.testTryToSolveTypeWithMultipleThreads
  -> create a new JavaParserTypeSolver
  -> start four CompletableFuture tasks
  -> StressRunnable.run
  -> JavaParserTypeSolver.tryToSolveType
  -> JavaParserTypeSolver.tryToSolveTypeUncached
  -> JavaParserTypeSolver.parse or parseDirectory
  -> JavaParser.parse
  -> GeneratedJavaParser.CompilationUnit
  -> generated parser look-ahead methods
  -> GeneratedJavaParserTokenManager
  -> AST construction and validation
```

`JavaParserTypeSolver.tryToSolveType` first reads its `foundTypes` cache.
See:

`javaparser-symbol-solver-core/src/main/java/com/github/javaparser/symbolsolver/resolution/typesolvers/JavaParserTypeSolver.java:246-256`.

On a miss, `tryToSolveTypeUncached` looks for the source file.
It parses the file or the package directory.
See the same file at lines 259-310.

`parse` reads its file cache at lines 174-180.
It calls `JavaParser.parse` at lines 188-197.
It writes the result to the cache at line 198.

The four tasks share one parser for one repetition.
The `parse` method locks this parser at line 189.
Thus, slow parser work also causes monitor wait time in the other tasks.

The test creates a new solver at each repetition.
Its three solver caches are instance fields.
See `JavaParserTypeSolver.java:64-66`.
Thus, these caches do not pass data from one test class to the next test class.
They are not the cross-class mechanism.

### 6.3 Profile evidence

The JFR experiment moves only the consumer.
| Consumer state | Run time | Class loads | Compiler time | Monitor wait | Garbage collection |
|---|---:|---:|---:|---:|---:|
| Cold | 2.065 s | 1,358 events and 74.2 ms | 2,865 events and 6,340.9 ms | 619.4 ms | 38.8 ms |
| Warm | 1.340 s | 12 events and 0.7 ms | 205 events and 1,351.5 ms | 36.9 ms | 20.7 ms |

Compiler time is the sum of work on compiler threads.
Thus, it can be longer than the consumer wall time.

The cold execution samples are in the real parser flow.
The largest leaf is `GeneratedJavaParser.jj_scan_token`.
Other samples are in:

- `GeneratedJavaParser` look-ahead methods;
- `GeneratedJavaParserTokenManager`;
- `LineEndingProcessingProvider.read`;
- AST iteration and validation;
- `JavaParserTypeSolver.parse` and `parseDirectory`.

The compiler runs while the consumer uses these methods.
The warm order enters the same flow after earlier tests compiled much of it.

The cold interval allocates 1,818.9 MiB.
The warm interval allocates 1,963.5 MiB.
The warm interval allocates more memory but is faster.
Thus, a lower allocation total does not explain this result.

Garbage collection saves only 18.1 ms in the warm interval.
The consumer saves 725 ms in the profiled run.
Thus, garbage collection is not the main cause.

### 6.4 Check

A second experiment limits compilation to compiler level C1.
The JVM option is:

```text
-XX:TieredStopAtLevel=1
```

This option prevents the higher C2 optimization level.
It keeps class loading and C1 compilation.

Two interleaved pairs give these suite medians:

| Order | Median |
|---|---:|
| Cold | 21,518 ms |
| Warm | 21,526 ms |

The warm-minus-cold effect is -0.04%.
The normal 4.73% suite effect is absent.
`JavaParserTypeSolverTest` still saves 196 ms at the end with C1.
First-use class loading and basic compilation can explain this smaller part.
The complete suite does not save time because other classes offset this part.

This check shows that shared higher-level compiled code causes the complete-order
gain.
This mechanism is different from the main SnakeYAML mechanism.
The SnakeYAML `PyEmitterTest` gain stays when the JIT compiler is disabled.

### 6.5 Abstraction

This is a shared optimized-code mechanism.
Earlier tests run parser methods.
The JVM compiles hot methods to optimized machine code.
A later high-volume consumer uses this code many times.

The consumer also uses four concurrent tasks.
A slow cold parse holds the shared parser lock for more time.
This increases monitor wait time.
Thus, compilation state changes both execution time and lock wait time.

The useful order pattern is:

```text
tests with shared parser paths
  -> compile hot parser methods
  -> repeated concurrent parser consumer
```

CSTO2 must not use compiler time as a fixed property of one test.
Compiler time depends on which tests ran first.
CSTO2 can use shared stack paths to find possible predecessor tests.
It must confirm the proposed edge with a paired order experiment.

## 7. Commons Text: persistent inline-mock instrumentation

The test for `TextStringBuilder` rewrites `TextStringBuilder`'s
own code in the running JVM to support mocking and leaves it rewritten, so a
later test that calls `TextStringBuilder` millions of times runs about twice as
slow.

### 7.1 Result

The experiment uses these two classes:

```text
slow: TextStringBuilderAppendInsertTest -> StringSubstitutorFilterReaderTest
fast: StringSubstitutorFilterReaderTest -> TextStringBuilderAppendInsertTest
```

Ten interleaved pairs were green.

| Order | Suite run times | Median |
|---|---:|---:|
| Slow | 3867, 3749, 4092, 3744, 3764, 4553, 4211, 4289, 4223, 4377 ms | 4151.5 ms |
| Fast | 2011, 2043, 2102, 2084, 2067, 2504, 2575, 2388, 2417, 2434 ms | 2245 ms |

The fast order reduces the two-class median by 45.92%.
The fast order wins all ten pairs.
The consumer median is 3334.5 ms in the slow order.
The consumer median is 1630.5 ms in the fast order.
Thus, prior mock instrumentation makes the consumer 2.04 times slower.

A larger prefix experiment confirms that this class explains most of a complete-order effect.
The complete prefix suite is 18.06% faster when the reader moves from position 26 to position 1.
### 7.2 Producer

`TextStringBuilderAppendInsertTest` creates Mockito spies of `TextStringBuilder`.
The first call is at:

`src/test/java/org/apache/commons/text/TextStringBuilderAppendInsertTest.java:591-600`.

The class creates more spies at lines 603-623 and 658-743.

The Java 11 build uses Mockito 5.2.0 and `mockito-inline`.
See:

`pom.xml:474-490`.

The inline mock maker uses a Byte Buddy Java agent.
The agent calls `Instrumentation.retransformClasses`.
It changes the already loaded `TextStringBuilder` class.
The changed class stays active after the producer ends.

The producer flow is:

```text
TextStringBuilderAppendInsertTest.testAppendln_CharArray
  -> Mockito.spy(new TextStringBuilder())
  -> Mockito inline mock maker
  -> Byte Buddy agent
  -> Instrumentation.retransformClasses(TextStringBuilder)
  -> add a mock-dispatch check to TextStringBuilder methods
```

The original `TextStringBuilder.size()` method has this effective code:

```text
return this.size;
```

The changed method first calls:

```text
MockMethodDispatcher.get(identifier, this)
```

It then checks `isMocked` and `isOverridden`.
It can call `MockMethodDispatcher.handle`.
Only after these checks does it read the `size` field.

The same change occurs in `charAt`, `length`, `isEmpty`, `midString`,
`readFrom`, `drainChars`, and many other methods.
Normal `TextStringBuilder` objects are not mocks.
The dispatch test returns the normal path for these objects.
However, each call still executes the added dispatch code.

### 7.3 Consumer

`StringSubstitutorFilterReaderTest` extends `StringSubstitutorTest`.
See:

`src/test/java/org/apache/commons/text/io/StringSubstitutorFilterReaderTest.java:43`.

The override at lines 49-54 adds a step-by-step reader test to each inherited
no-replacement test.
The first loop uses target sizes from 1 through 8192.
The second nested loop uses 400 target sizes and each valid target index.
See the same file at lines 56-70.

Each loop operation creates a `StringSubstitutorReader`.
See lines 80-89 and 122-130.
The reader creates one `TextStringBuilder` buffer.
See:

`src/main/java/org/apache/commons/text/io/StringSubstitutorReader.java:47-48`.

The reader calls `readFrom` at lines 83-86.
It calls `length`, `drainChars`, and `isEmpty` at lines 102-109.
Its main read loop also calls `size` and related buffer methods.
See the same file at lines 173-303.

The consumer also calls `StringSubstitutor.replaceIn`.
That path calls `TextStringBuilder.charAt`, `midString`, and other methods.

The consumer flow is:

```text
inherited StringSubstitutorTest test
  -> StringSubstitutorFilterReaderTest.doTestNoReplace
  -> doTestNoReplaceInSteps
  -> doTestReplaceInCharArraySteps
     or doTestReplaceInCharArrayAtSteps
  -> new StringSubstitutorReader
  -> new TextStringBuilder buffer
  -> StringSubstitutorReader.read
  -> TextStringBuilder methods
  -> MockMethodDispatcher.get
  -> normal method body
```

The consumer allocates approximately 9.7 GiB in both orders.
Thus, the work volume is nearly the same.
The changed execution path performs the mock dispatch checks many times.

### 7.4 Profile evidence

The instrumented consumer interval runs 3.269 seconds.
The same interval without instrumentation runs 1.682 seconds.
Allocation and garbage collection are almost identical in both orders.
Thus, the work volume is the same and neither explains the difference.
Compiler time doubles in the instrumented interval, from 970.8 to 2,019.6 ms.

The slow interval compiles `MockMethodDispatcher.get`.
It also compiles the changed `TextStringBuilder` methods.
The changed methods are much larger than the original methods.
The change adds direct execution cost and compilation cost.

The application stack paths are the same in both orders.
They are in `StringSubstitutorReader`, `StringSubstitutor`, and
`TextStringBuilder`.
The slow order adds mock-dispatch work inside the last type.

### 7.5 Check

This check changes Mockito from its inline mock maker to its subclass mock
maker:

```text
mockito-extensions/org.mockito.plugins.MockMaker
  contains:
mock-maker-subclass
```

The subclass mock maker creates a separate mock subclass.
It does not change the bytecode of the normal `TextStringBuilder` class.

Ten interleaved pairs give these suite medians:

| Order | Median |
|---|---:|
| Producer first | 1998 ms |
| Consumer first | 1984 ms |

The order difference is 0.70%.
Thus, the 45.92% penalty is absent.
With this change, the consumer median is 1462.5 ms when it runs second.
It is 1504 ms when it runs first.

This check changes the mock implementation and keeps the test behavior.
It shows that inline bytecode transformation causes the slowdown.

### 7.6 Abstraction

This is a persistent test-tool instrumentation mechanism.
The producer asks a mock framework to instrument a production class.
The framework changes that class in the shared JVM.
The changed code stays after the mock objects are no longer in use.
A later high-volume consumer calls the changed methods many times.

The directed order constraint is:

```text
StringSubstitutorFilterReaderTest
  -> TextStringBuilderAppendInsertTest
```

The important shared state is executable code.
It is not an application field, a property, or a cache.
A state snapshot of static fields cannot find it.

CSTO2 must record which production types an inline mock maker transforms.
It must connect each transformed type to later hot call paths.
It can put the mock producer after large consumers of that type.
It can also test a subclass mock maker when the project permits that change.

## 8. AsyncHttpClient: cached Netty leak-detection policy

Whichever test touches Netty first decides, for the rest of the
run, whether Netty tracks every buffer for leaks; when the leak-checking test
goes first, a later buffer-heavy test pays a tracking cost on every buffer it
allocates.

### 8.1 Result

The experiment uses these two classes:

```text
slow: NettyConnectionResetByPeerTest -> MultipartBodyTest
fast: MultipartBodyTest -> NettyConnectionResetByPeerTest
```

Ten interleaved pairs were green.

| Order | Median pair run time | Pair wins |
|---|---:|---:|
| Fast | 1312.5 ms | 9 of 10 |
| Slow | 1779.5 ms | 1 of 10 |

These values are the sums of the two Surefire XML class durations.
They are not boundary-marker durations.
The slow-order median is 467 ms greater than the fast-order median.
The slow-order median is 35.58% greater than the fast-order median.
The median of the ten paired differences is 637 ms.

The complete unmodified totals are:

| Pair | Fast order | Slow order | Slow minus fast |
|---:|---:|---:|---:|
| 1 | 1202 ms | 2529 ms | 1327 ms |
| 2 | 2085 ms | 3718 ms | 1633 ms |
| 3 | 1440 ms | 2270 ms | 830 ms |
| 4 | 1325 ms | 1420 ms | 95 ms |
| 5 | 1300 ms | 2758 ms | 1458 ms |
| 6 | 1145 ms | 1505 ms | 360 ms |
| 7 | 905 ms | 1744 ms | 839 ms |
| 8 | 1442 ms | 1388 ms | -54 ms |
| 9 | 1440 ms | 1815 ms | 375 ms |
| 10 | 1128 ms | 1572 ms | 444 ms |

The median for `MultipartBodyTest` is 735.5 ms in the fast order.
It is 1165 ms in the slow order.
The median for `NettyConnectionResetByPeerTest` changes from 559.5 ms to
614.5 ms.
Thus, the additional multipart work is not a transfer of the reset-test cost.
All ten fast-order logs show this value:

```text
io.netty.leakDetection.level: simple
```

All ten slow-order logs show this value:

```text
io.netty.leakDetection.level: paranoid
```

### 8.2 Policy producer

`NettyConnectionResetByPeerTest` uses `NettyLeakDetectorExtension`.
See:

`client/src/test/java/org/asynchttpclient/netty/NettyConnectionResetByPeerTest.java:39`.

The extension has a static initializer.
If the system property is not set, the initializer sets
`io.netty.leakDetection.level` to `paranoid`.
The initializer then installs a leak listener.
See `NettyLeakDetectorExtension.java:14-23` in:

`netty-leak-detector-junit-extension-0.2.0-sources.jar`.

The producer flow is:

```text
JUnit loads NettyConnectionResetByPeerTest
  -> JUnit loads NettyLeakDetectorExtension
  -> extension static initializer
  -> System.setProperty("io.netty.leakDetection.level", "paranoid")
  -> ByteBufUtil.setLeakListener
```

The extension also calls `System.gc()` until a weak reference clears.
It sleeps for 10 ms between calls.
See `NettyLeakListener.java:32-67` in the same source archive.
This work occurs at extension boundaries.
It does not explain the large difference inside `MultipartBodyTest`.

### 8.3 Policy cache

Netty initializes `ResourceLeakDetector` on its first use.
Its static initializer reads `io.netty.leakDetection.level`.
It saves the value in the static `level` field.
See:

`common/src/main/java/io/netty/util/ResourceLeakDetector.java:99-132`.

The later property write does not update this field.

`ResourceLeakDetector.track0` makes one `DefaultResourceLeak` tracker for
each object at the `PARANOID` level.
At other enabled levels, it samples objects.
See:

`common/src/main/java/io/netty/util/ResourceLeakDetector.java:266-273`.

Thus, first use selects a process-wide policy:

```text
MultipartBodyTest first
  -> initialize ResourceLeakDetector at SIMPLE
  -> extension writes the property too late
  -> later allocations use SIMPLE

NettyConnectionResetByPeerTest first
  -> extension writes PARANOID
  -> initialize ResourceLeakDetector at PARANOID
  -> later allocations use PARANOID
```

### 8.4 Consumer

`MultipartBodyTest.transferWithCopy` creates a Netty buffer with
`Unpooled.buffer`.
It transfers the multipart body and then releases the buffer.
See:

`client/src/test/java/org/asynchttpclient/request/body/multipart/MultipartBodyTest.java:83-94`.

The test repeats this operation for each buffer length from 1 to the maximum
multipart-content estimate.
It repeats the complete test five times.
See the same file at lines 128-135.

The consumer flow at the slow policy is:

```text
MultipartBodyTest.transferWithCopy
  -> Unpooled.buffer
  -> ByteBuf allocator
  -> ResourceLeakDetector.track0
  -> new DefaultResourceLeak for each buffer
  -> multipart transfer
  -> ByteBuf.release
  -> DefaultResourceLeak.close
```

The test allocates and releases many buffers.
Thus, it amplifies the cost of the selected policy.

### 8.5 Profile evidence

| `MultipartBodyTest` policy | Run time | Attributed allocation |
|---|---:|---:|
| `SIMPLE` | 0.426 s | 41.8 MiB |
| `PARANOID` | 0.929 s | 394.0 MiB |

The `PARANOID` recording has this sampled execution path:

```text
ResourceLeakDetector$DefaultResourceLeak.close
  -> SimpleLeakAwareByteBuf.closeLeak
  -> SimpleLeakAwareByteBuf.release
  -> AdvancedLeakAwareByteBuf.release
```

The `SIMPLE` recording does not have this per-buffer close path.

Garbage collection differs by only 2 ms between the two policies.
It cannot explain the 342.4-ms median difference for the consumer.
The leak-tracker allocation and close path is the direct cause.

### 8.6 Check

This check sets this JVM option before any test class loads:

```text
-Dio.netty.leakDetection.level=simple
```

The extension does not replace an existing property.
Therefore, both orders use `SIMPLE`.

Ten interleaved pairs were green.

| Order | Median pair run time | Pair wins |
|---|---:|---:|
| `MultipartBodyTest` first | 1001.5 ms | 0 of 10 |
| `NettyConnectionResetByPeerTest` first | 704.5 ms | 10 of 10 |

The original slow direction is absent.
It reverses in all ten pairs.
After this change, ordinary Netty initialization by the first class can
help the second class.
This check changes the selected Netty leak-detection policy.
It does not change the multipart input or the assertions.
It confirms that policy selection causes the original order difference.

### 8.7 Abstraction

This is a cached-policy mechanism.
A test tool writes a system property.
A production class reads the property one time in a static initializer.
The first class to initialize the production class selects the policy for the
test fork.
A later property write cannot change the cached field.

The harmful edge is:

```text
NettyConnectionResetByPeerTest
  -- selects PARANOID before Netty initialization -->
MultipartBodyTest
```

The best fix is to set the required leak-detection level at JVM start.
If the build must keep the late extension behavior, CSTO2 must put large
buffer consumers before the first extension test.

## 9. AsyncHttpClient: leaked connection-pool policy

One test leaves "do not reuse connections" cached in the
client's configuration, so later tests open and close a fresh network
connection for every request instead of reusing pooled ones.

### 9.1 Result

This experiment uses six methods from the paper test set.
Both orders keep the four consumer methods in the same order.
The orders change only the first two methods:

```text
order A:
  AsyncHttpClientDefaultsTest.testDefaultMaxRedirects
  -> AsyncHttpClientDefaultsTest.testDefaultAllowPoolingConnection
  -> FilterTest.loadThrottleTest
  -> ConnectionPoolTest.asyncHandlerOnThrowableTest
  -> MultipartBasicAuthTest.authorizedPreemptiveRealmWorks
  -> MultipartBasicAuthTest.authorizedNonPreemptiveRealmWorksWithExpectContinue

order B:
  AsyncHttpClientDefaultsTest.testDefaultAllowPoolingConnection
  -> AsyncHttpClientDefaultsTest.testDefaultMaxRedirects
  -> the same four consumers
```

All 20 runs were green on Temurin 11.
Each order ran in one reused Surefire fork.

| Test-method order | Test-suite times | Median |
|---|---:|---:|
| `maxRedirects -> allowPooling` | 2158, 2299, 2149, 1215, 2006, 2910, 2571, 2389, 1621, 1457 ms | 2153.5 ms |
| `allowPooling -> maxRedirects` | 1974, 1851, 1785, 1241, 1934, 2250, 2241, 1855, 1572, 1779 ms | 1853.0 ms |

No command-line option or JVM property differs between the two arms.
The test order alone selects the connection-pool policy.

The `allowPooling -> maxRedirects` order has a 13.95% lower median.
It wins 8 of 10 paired runs.
The paired median saving is 257 ms.

The consumer medians also have the same direction:

| Consumer class | `maxRedirects -> allowPooling` | `allowPooling -> maxRedirects` |
|---|---:|---:|
| `FilterTest` | 862.0 ms | 731.0 ms |
| `ConnectionPoolTest` | 200.0 ms | 180.5 ms |
| `MultipartBasicAuthTest` | 1047.0 ms | 884.0 ms |

### 9.2 Producer and cache

`testDefaultAllowPoolingConnection` tests the `keepAlive` property.
See:

`client/src/test/java/org/asynchttpclient/AsyncHttpClientDefaultsTest.java:123-127`.

The original helper does these operations:

```text
save the system property
-> set keepAlive=false
-> clear the configuration cache
-> call defaultKeepAlive
-> cache false
-> restore the system property
-> do not clear the configuration cache
```

See the original helper at lines 176-191.

`AsyncHttpClientConfigHelper.Config` has a process-wide `propsCache`.
See:

`client/src/main/java/org/asynchttpclient/config/AsyncHttpClientConfigHelper.java:53-60`.

`reload` clears this map at lines 62-65.
`getString` reads a system property only on a cache miss.
It then saves the value in the map.
See lines 95-105.

Thus, the helper restores the system property but leaves the old value in the map.
The test leaks `keepAlive=false`.

The second method explains the order difference.
`testDefaultMaxRedirects` calls `reloadProperties` before it reads its property.
Thus, it clears the leaked `keepAlive` value.
When this method runs second, a later call to `defaultKeepAlive` reads the normal value `true`.

The producer flow is:

```text
testDefaultAllowPoolingConnection
  -> testBooleanSystemProperty
  -> System.setProperty(keepAlive, false)
  -> AsyncHttpClientConfigHelper.reloadProperties
  -> Config.propsCache.clear
  -> AsyncHttpClientConfigDefaults.defaultKeepAlive
  -> Config.getString
  -> Config.propsCache stores false
  -> System.clearProperty(keepAlive)
  -> cached false stays in the fork
```

`defaultKeepAlive` reads this helper at:

`client/src/main/java/org/asynchttpclient/config/AsyncHttpClientConfigDefaults.java:198-200`.

### 9.3 Consumer execution flow

Each consumer calls `Dsl.config`.
This call creates a `DefaultAsyncHttpClientConfig.Builder`.
See:

`client/src/main/java/org/asynchttpclient/Dsl.java:91-93`.

The builder initializes its `keepAlive` field from `defaultKeepAlive`.
See:

`client/src/main/java/org/asynchttpclient/DefaultAsyncHttpClientConfig.java:826-829`.

`ChannelManager` uses this field to select the pool:

```text
keepAlive=true  -> DefaultChannelPool
keepAlive=false -> NoopChannelPool
```

See:

`client/src/main/java/org/asynchttpclient/netty/channel/ChannelManager.java:133-142`.

`NoopChannelPool.poll` always returns `null`.
`NoopChannelPool.offer` always returns `false`.
See:

`client/src/main/java/org/asynchttpclient/channel/NoopChannelPool.java:32-46`.

The request sender polls the pool before it opens a channel.
See:

`client/src/main/java/org/asynchttpclient/netty/request/NettyRequestSender.java:556-570`.

After a response, `ChannelManager.tryToOfferChannelToPool` offers the channel.
It closes the channel when the pool rejects it.
See:

`client/src/main/java/org/asynchttpclient/netty/channel/ChannelManager.java:303-321`.

The complete resource flow is:

```text
leaked keepAlive=false
  -> DefaultAsyncHttpClientConfig.Builder.keepAlive=false
  -> ChannelManager selects NoopChannelPool
  -> poll returns null
  -> each request opens a new channel
  -> offer returns false
  -> ChannelManager closes the channel
```

The consumers amplify this policy:

- `FilterTest.loadThrottleTest` starts 200 requests.
  See `client/src/test/java/org/asynchttpclient/filter/FilterTest.java:59-72`.
- `ConnectionPoolTest.asyncHandlerOnThrowableTest` starts 32 requests.
  See `client/src/test/java/org/asynchttpclient/channel/ConnectionPoolTest.java:198-229`.
- The two `MultipartBasicAuthTest` methods each run 20 uploads.
  See `client/src/test/java/org/asynchttpclient/request/body/multipart/MultipartBasicAuthTest.java:85-107`.

### 9.4 Execution and operating-system evidence

The DEBUG log gives the exact channel flow for each green run.

In all ten `maxRedirects -> allowPooling` runs:

- `Using new Channel` occurs 291 or 292 times.
- `Using pooled Channel` does not occur.
- `Closing Channel` occurs 288 to 292 times.

In all ten `allowPooling -> maxRedirects` runs:

- `Using new Channel` occurs 40 to 64 times.
- `Using pooled Channel` occurs 228 to 252 times.
- `Closing Channel` occurs 20 times.

This evidence is not a transfer of a start-up cost.
The same consumer requests use a different connection life cycle.

The macOS process counters also show the resource effect.
The `maxRedirects -> allowPooling` arm has a median of 304.5 voluntary context switches.
The reverse arm has a median of 126.
The first arm has more voluntary context switches in all 10 paired runs.
The paired median difference is 174.

JFR shows this new-channel allocation path:

```text
Bootstrap.init
  -> AbstractBootstrap.initAndRegister
  -> NioSocketChannel.<init>
  -> AbstractChannel.newChannelPipeline
```

The application DEBUG log gives the exact channel counts.
JFR gives the stack path and the test intervals.

### 9.5 Check

This check adds this call after each helper restores its system property:

```java
AsyncHttpClientConfigHelper.reloadProperties();
```

This change keeps the selected methods and inputs the same.
It changes only the state cleanup.

After this fix, both orders use the pool:

| Test-method order | Median new channels | Median pooled channels |
|---|---:|---:|
| `maxRedirects -> allowPooling` | 59 | 233 |
| `allowPooling -> maxRedirects` | 64 | 228 |

The paired median difference in voluntary context switches falls from 174 to 6.
The original run-time direction does not stay.
The `maxRedirects -> allowPooling` order has a median of 1688.5 ms.
The reverse order has a median of 1781.0 ms.
Thus, the first order becomes 5.2% faster.

This check confirms this causal chain:

```text
missing cache clear
  -> leaked keepAlive=false
  -> NoopChannelPool
  -> more channel open and close operations
  -> more context switches
  -> longer consumer run time
```

### 9.6 Abstraction

This is a leaked resource-policy mechanism.
A test restores the source property but does not clear a derived cache.
A later builder reads the stale value.
The stale value changes the life cycle of an operating-system resource.

This mechanism is different from a retained data cache.
The number of cache entries is not the cost.
One stale Boolean value selects a different implementation.

The harmful edge is:

```text
testDefaultAllowPoolingConnection
  -- leaves keepAlive=false in propsCache -->
later tests that use Dsl.config()
```

The best fix is to clear the cache after the helper restores the property.
If the source fix is not possible, the order generator must put a cache-clearing defaults test after this producer and before network consumers.

## 10. Gson: shared Guava iterator optimization

Two generated suites run the same test-framework code; when the
big suite goes first, it gets that shared code fully compiled sooner, so the
small suite runs almost entirely on fast code and the total is lower.

### 10.1 Result

Gson is project 18 in the paper data.
The `gson` module is module 493 in `sorted_ci_time.csv`.
It is also module 2489 in the 500-project module list.
Gson is not one of the small replication fixtures in `docker_template/replication`.

The confirmed test set has these two generated suites:

```text
com.google.gson.internal.LinkedTreeMapSuiteTest
com.google.gson.JsonObjectAsMapSuiteTest
```

The two orders are:

```text
A: LinkedTreeMapSuiteTest -> JsonObjectAsMapSuiteTest
B: JsonObjectAsMapSuiteTest -> LinkedTreeMapSuiteTest
```

Surefire used a Corretto 8 fork.
Maven used Java 17 because the repository Maven options require Java 9 or later.
The Surefire `jvm` option selected this executable:

```text
/Library/Java/JavaVirtualMachines/amazon-corretto-8.jdk/Contents/Home/bin/java
```

A process capture and `-showversion` output confirm this fork.
The current suite source uses some new Java syntax.
The study used equivalent Java 8 suite containers.
The test generators, Guava features, production types, and test names did not change.

Each arm ran 2,757 green tests:

- `LinkedTreeMapSuiteTest`: 1,854 tests.
- `JsonObjectAsMapSuiteTest`: 903 tests.

Twenty interleaved pairs gave these results:

| Order | Median suite time | Wins |
|---|---:|---:|
| A | 386.5 ms | 18 of 20 |
| B | 404.0 ms | 2 of 20 |

The paired median saving for A is 23.0 ms.
The paired mean saving is 43.05 ms.
The wall-time direction agrees in 16 of 20 pairs.
The paired wall-time median saving is 34.59 ms.

The component medians are:

| Order | Linked suite | Object suite | Sum |
|---|---:|---:|---:|
| A | 351.0 ms | 32.5 ms | 383.5 ms |
| B | 128.5 ms | 274.5 ms | 403.0 ms |

This result is not a fixed first-position cost.
The large suite costs 222.5 ms more when it runs first.
It then saves 242.0 ms in the second suite.
The total is 19.5 ms lower.

### 10.2 Generated suite flow

`LinkedTreeMapSuiteTest.suite()` makes two Guava `MapTestSuiteBuilder` suites.
One suite permits null values.
The other suite does not permit null values.
See:

`gson/src/test/java/com/google/gson/internal/LinkedTreeMapSuiteTest.java:63`.

`JsonObjectAsMapSuiteTest.suite()` makes one Guava map suite.
See:

`gson/src/test/java/com/google/gson/JsonObjectAsMapSuiteTest.java:72`.

The direct suite creates and fills `LinkedTreeMap`.
See:

`gson/src/test/java/com/google/gson/internal/LinkedTreeMapSuiteTest.java:33`.

`JsonObject` also uses the same production map:

```java
private final LinkedTreeMap<String, JsonElement> members = new LinkedTreeMap<>(false);
```

See:

`gson/src/main/java/com/google/gson/JsonObject.java:40`.

`JsonObject.asMap()` returns this map.
See the same file at line 227.

Both suites use these production paths:

```text
MapTestSuiteBuilder generated test
  -> test map operation
  -> LinkedTreeMap.put
  -> LinkedTreeMap.find
  -> LinkedTreeMap.rebalance
```

Both suites also use:

```text
LinkedTreeMap iterator
  -> nextNode
  -> remove
```

See:

- `gson/src/main/java/com/google/gson/internal/LinkedTreeMap.java:114`
- `gson/src/main/java/com/google/gson/internal/LinkedTreeMap.java:151`
- `gson/src/main/java/com/google/gson/internal/LinkedTreeMap.java:338`
- `gson/src/main/java/com/google/gson/internal/LinkedTreeMap.java:562`

### 10.3 Shared iterator engine

The generated tests also use one Guava test engine.
The exact flow is:

```text
CollectionIteratorTester.runIteratorTest
  -> AbstractIteratorTester.test
  -> AbstractIteratorTester.recurse
  -> internalExecuteAndCompare
  -> compareResultsForThisListOfStimuli
```

`test()` calls `recurse(0)`.
`recurse()` enumerates operation combinations.
`compareResultsForThisListOfStimuli()` makes the reference iterator and the target iterator.
It then executes each operation.

See the Guava 33.5.0-jre source:

`com/google/common/collect/testing/AbstractIteratorTester.java:325`.

The source JAR is:

`~/.m2/repository/com/google/guava/guava-testlib/33.5.0-jre/guava-testlib-33.5.0-jre-sources.jar`.

The test fork stays alive between the two suites.
Therefore, these HotSpot items also stay alive:

- method invocation counters;
- loop counters;
- method profiles;
- compiler tasks;
- installed level-3 and level-4 code.

The 1,854-test suite runs the shared iterator engine more times than the 903-test suite.
It changes when the shared methods reach each optimization level.
The second suite then uses this optimized code.

### 10.4 Exact compilation chronology

A Java 8 JFR recording used a zero compilation threshold.
It recorded all compilation events.
The two arms loaded the same 1,344 classes.

For order A, these level-3 compilations occurred before the second suite:

| Method | Time after first suite marker |
|---|---:|
| `internalExecuteAndCompare` | 253.634 ms |
| `recurse` | 266.941 ms |
| `compareResultsForThisListOfStimuli` | 273.814 ms |

`internalExecuteAndCompare` reached level 4 at 459.237 ms.
This event was 85.019 ms after the second suite started.

For order B, the same level-3 methods compiled at:

| Method | Time after first suite marker |
|---|---:|
| `recurse` | 181.351 ms |
| `internalExecuteAndCompare` | 182.371 ms |
| `compareResultsForThisListOfStimuli` | 199.401 ms |

`internalExecuteAndCompare` reached level 4 at 414.312 ms.
This event was 147.065 ms after the second suite started.

Thus, the order changes how long the second suite runs before the shared iterator engine reaches level 4.
The recording also shows level-3 and level-4 changes in `LinkedTreeMap.find`, `put`, `nextNode`, and `entrySet`.

### 10.5 Check

This check disabled compilation only for the shared Guava iterator engine:

```text
-XX:CompileCommand=exclude,com.google.common.collect.testing.AbstractIteratorTester::*
```

The HotSpot `CompilerOracle` output confirms the exclusions.
The excluded methods include:

- `recurse`;
- `internalExecuteAndCompare`;
- `compareResultsForThisListOfStimuli`;
- `iteratorStimuli`.

The check used 40 paired comparisons.
All 80 arms were green.

The result changed as follows:

| Measure | Baseline | Compilation disabled |
|---|---:|---:|
| A wins | 18 of 20 | 22 of 40 |
| Paired median | 23.0 ms | 7.5 ms |
| Paired mean | 43.05 ms | 4.85 ms |

The exclusion removes the stable direction.
It reduces the paired median by approximately 67%.
It reduces the paired mean by approximately 89%.
The host had high load, so the interpreted path had large outliers.
The evidence does not show a stable reverse direction.

This change affects only compilation of the JFR-identified shared class.
It does not change the Gson map configuration or the test set.
This result confirms that the shared iterator optimization is a material cause of the baseline order effect.

### 10.6 Abstraction

This is an asymmetric shared-optimization mechanism.
Two generated suites use the same test engine and the same production data structure.
The suites have different sizes.
The large suite changes the shared optimization state before the small suite starts.
The reverse order produces a different level-4 transition time.

The useful edge is:

```text
large generated suite
  -- optimizes shared iterator engine -->
small generated suite
```

An order generator must know which generated suites use the same framework code.
It must also know the number of generated cases in each suite.
Class names alone do not show this relation.

## 11. SnakeYAML: compiler-queue delay plus recursive-map uncommon trap

A compiler-heavy test clogs the JIT compiler's queue, so the
next test's hottest method never gets fully optimized and runs in slow form for
the rest of the fork.

### 11.1 Result

This result is separate from the shared first-use initialization in section 5.
It uses two exact test classes from the supplied SnakeYAML paper order:

```text
fast: org.yaml.snakeyaml.issues.issue377.ReferencesTest
      -> org.yaml.snakeyaml.stress.StressEmitterTest

slow: org.yaml.snakeyaml.stress.StressEmitterTest
      -> org.yaml.snakeyaml.issues.issue377.ReferencesTest
```

The test fork used Corretto 8.502.07.1.
The run used one reused fork.
All 24 arms in 12 interleaved pairs were green.
Each arm ran the same four test methods.

The baseline result was:

| Measure | `References -> Stress` | `Stress -> References` |
|---|---:|---:|
| Pair total median | 1,079.0 ms | 1,594.0 ms |
| `ReferencesTest` median | 659.0 ms | 1,080.0 ms |
| `StressEmitterTest` median | 423.5 ms | 505.5 ms |

The fast order won 10 of 12 pairs.
The paired median was 518.5 ms.
The paired mean was 505.5 ms.

This is not a fixed cost that moves from one class to the other.
`ReferencesTest` is slower after `StressEmitterTest`.
`StressEmitterTest` is also slower when it runs first.

The baseline data is in:

### 11.2 Producer

`StressEmitterTest.testPerformance` loads one invoice.
It then makes 6,001 dump calls.
It uses one `Yaml` object for 3,001 calls.
It creates a new `Yaml` object for 3,000 calls.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/stress/StressEmitterTest.java:33-73`.

The main flow is:

```text
StressEmitterTest.testPerformance
  -> Yaml.dump or Yaml.dumpAsMap
  -> BaseRepresenter and Representer
  -> Serializer
  -> Emitter
```

The test finishes while compiler work is still in progress.
In the JFR slow-order recording, the Stress interval was 454 ms.
The boundary counter assigned 1,218 ms of compiler work to this interval.
This compiler work can continue after the test boundary.

### 11.3 Consumer

`ReferencesTest.createDump` creates a nested map.
The depth is 25, 30, or 35.
It also puts the outer map into itself as a key.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/issues/issue377/ReferencesTest.java:34-67`.

All three test methods call `createDump`.
They then load the YAML text.
See the same file at lines 70-128.

The load path must calculate a hash for a recursive map key:

```text
ReferencesTest
  -> Yaml.load
  -> SafeConstructor.processDuplicateKeys
  -> key.hashCode
  -> AbstractMap.hashCode
  -> HashMap$Node.hashCode
```

`SafeConstructor.processDuplicateKeys` calls `key.hashCode()` for a two-step
recursive key.
See:

`snakeyaml/src/main/java/org/yaml/snakeyaml/constructor/SafeConstructor.java:98-115`.

The constructor postpones the insertion of a recursive key.
`BaseConstructor.fillRecursive` later calls `Map.put`.
This call calculates the key hash again.
See:

- `snakeyaml/src/main/java/org/yaml/snakeyaml/constructor/BaseConstructor.java:200-225`;
- `snakeyaml/src/main/java/org/yaml/snakeyaml/constructor/BaseConstructor.java:563-597`.

The nested aliases make this hash path very hot.
In the fast-order JFR recording, 13 of 14 Java execution samples in
`ReferencesTest` were in `BaseConstructor.fillRecursive`.

### 11.4 Compilation chronology

The Java 8 JFR run reproduced the direction:

```text
References -> Stress: 1,090 ms
Stress -> References: 1,517 ms
```

The JFR data is in:

The HotSpot compilation logs give the exact tier changes.
When `ReferencesTest` ran first:

- `HashMap$Node.hashCode` reached level 3 at 0.314 seconds;
- it reached level 4 at 0.338 seconds;
- `AbstractMap.hashCode` reached level 4 at 0.341 seconds.

When `StressEmitterTest` ran first:

- `HashMap$Node.hashCode` entered the compiler queue at level 2 at 1.380 seconds;
- it installed level-2 code at 1.384 seconds;
- it did not reach level 3 or level 4 before the fork ended;
- `AbstractMap.hashCode` moved through level 2, OSR level 3, level 3, and level 4;
- its level-4 code took a `class_check` uncommon trap at 4.152 seconds.

The second `ReferencesTest` therefore runs its critical node-hash method at
level 2.
The first `ReferencesTest` runs the same method at level 4.

A separate logged pair reproduced this timing shape.
`ReferencesTest` took 1,062 ms when it ran first.
It took 2,849 ms after `StressEmitterTest`.
The HotSpot logs are in:

### 11.5 Checks and limits

Three checks tested the compiler explanation.

First, one check disabled compilation of:

```text
java.util.HashMap$Node.hashCode
java.util.AbstractMap.hashCode
```

The compiler output confirmed both exclusions.
The recursive hash path then became very slow.
One complete green pair took 78,795 ms and 77,950 ms.
The slow-order penalty collapsed and changed sign by 845 ms, or about 1.1%.
The check stopped after one complete pair because each arm took about
80 seconds.
One pair is supporting evidence.
It is not a stable effect estimate.

Second, a four-pair check excluded compilation of all `Emitter` and
`Serializer` methods.
All eight arms were green.
Each direction won two pairs.
The paired median was -39 ms.
This change also made the suite much slower and more sensitive to host load.
It shows that the shared dump-pipeline compiler load is necessary for the
stable baseline direction.
It does not identify one emitter method as the cause.

Third, a check increased `CICompilerCount` from 4 to 8.
All 20 arms in 10 pairs were green.
The slow order won 7 of 10 pairs.
The paired median decreased from 518.5 ms to 293.0 ms.
The paired mean changed from +505.5 ms to -132.8 ms.
Three large reverse pairs on a busy host caused the negative mean.
The check reduced the median gap.
It is not a clean removal.

The baseline, JFR, compilation log, and checks support this cause:

```text
StressEmitterTest
  -> large shared compiler queue
  -> delayed tier-4 compilation for HashMap$Node.hashCode
  -> AbstractMap.hashCode class-check trap
  -> slower recursive-map work in ReferencesTest
```

The evidence does not prove that compiler-queue delay explains every baseline
millisecond.
Host contention changed the size of the effect.
The order constraint is still clear:

```text
ReferencesTest -> StressEmitterTest
```

### 11.6 Abstraction

This is a harmful shared-compiler-state mechanism.
A compiler-heavy producer can delay the optimized code that a later consumer
needs.
The later consumer can also take an uncommon trap on its unusual recursive
data shape.

An order generator must record more than shared method names.
It must also record:

- compiler work that continues after a test boundary;
- the tier installed for a later hot method;
- uncommon traps on unusual data shapes;
- asymmetry between an ordinary JavaBean graph and a recursive map graph.

## 12. SnakeYAML: compact-notation regular expression on Java 8

One test spends its time in a regular expression that is
expensive on Java 8, and that path runs measurably slower after the other 348
classes have run; putting the test first saves about half a second per run.

### 12.1 Result

This result uses all 349 exact classes in the supplied SnakeYAML paper order.
The only change moves this class:

```text
org.yaml.snakeyaml.extensions.compactnotation.CompactConstructorErrorsTest
```

The fast order puts the class at position 0.
The slow order puts the class at position 348.
All other classes keep the same relative order.

The test fork used Amazon Corretto 8.0.502.
It used one reused Surefire fork.
All 20 arms in 10 interleaved pairs were green.
Each arm ran the same 349 classes.

The complete-suite times were:

```text
front: 4951, 4788, 5223, 5379, 5008, 4970, 6236, 4575, 4344, 5011 ms
back:  5523, 5415, 5524, 5652, 5571, 5572, 6692, 5165, 5351, 5338 ms
```

The front order won all 10 pairs.
The paired `back - front` differences were:

```text
+572, +627, +301, +273, +563, +602, +456, +590, +1007, +327 ms
```

| Measure | Front | Back |
|---|---:|---:|
| Suite median | 4,989.0 ms | 5,523.5 ms |
| Suite mean | 5,048.5 ms | 5,580.3 ms |
| Moved-class median | 1,375.5 ms | 1,626.0 ms |

The paired median was 567.5 ms.
The paired mean was 531.8 ms.
The front median was 9.68% lower than the back median.
The two-sided sign-test probability for 10 wins in 10 pairs was 0.001953.

The study excluded the baseline r10 run.
That run overlapped a separate high-load experiment.

### 12.2 Test flow

`CompactConstructorErrorsTest` has nine test methods.
The methods load invalid or unusual compact-notation YAML files.
The helper methods create a `PackageCompactConstructor` and call `Yaml.load`.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/extensions/compactnotation/CompactConstructorErrorsTest.java:27-73`.

`test4` loads this mapping:

```yaml
Table(id12, table):
  - Row(id111, description = text) {size: 15}
```

See:

- `snakeyaml/src/test/java/org/yaml/snakeyaml/extensions/compactnotation/CompactConstructorErrorsTest.java:85-97`;
- `snakeyaml/src/test/resources/compactnotation/error4.yaml:1-2`.

The test checks that SnakeYAML creates a map instead of a `Row`.
Thus, the unusual input is part of the expected test behavior.

### 12.3 Regular-expression flow

`CompactConstructor` stores `GUESS_COMPACT` in a static field.
See:

`snakeyaml/src/main/java/org/yaml/snakeyaml/extensions/compactnotation/CompactConstructor.java:39-40`.

The expression is:

```text
\p{Alpha}.*\s*\((?:,?\s*(?:(?:\w*)|(?:\p{Alpha}\w*\s*=.+))\s*)+\)
```

It has nested variable-length parts.
`getConstructor` applies the expression to scalar mapping keys and scalar
nodes.
See the same file at lines 159-180.

The exact application flow is:

```text
CompactConstructorErrorsTest.test4
  -> load
  -> Yaml.load
  -> BaseConstructor.constructDocument
  -> CompactConstructor$ConstructCompactObject.construct2ndStep
  -> BaseConstructor.constructSequence
  -> SafeConstructor.constructMapping2ndStep
  -> SafeConstructor.flattenMapping
  -> SafeConstructor.processDuplicateKeys
  -> BaseConstructor.constructObject
  -> CompactConstructor.getConstructor
  -> GUESS_COMPACT.matcher(scalar).matches
  -> java.util.regex.Pattern$Curly.match
  -> java.util.regex.Pattern$Loop.match
```

Three repeated Java 8 thread snapshots show `test4` in the recursive
`Pattern$Curly` and `Pattern$Loop` calls.
The snapshots are in:

The boundary counters also show different JVM state at the two positions.
The front interval loaded 371 classes.
It had 336 to 1,028 ms of compiler work.
The back interval loaded one class.
It had 286 to 478 ms of compiler work.
These counters do not identify one compilation tier or one prior test as the
cause.
The confirmed claim is narrower.
The static `GUESS_COMPACT` call is necessary for the repeatable total-time
difference on this Java 8 JVM.

### 12.4 Check

The purpose of the code change was to test whether the initial
`GUESS_COMPACT` gate caused the order difference.
The check replaced only the two calls to:

```java
GUESS_COMPACT.matcher(scalar.getValue()).matches()
```

with a linear shape test.
The shape test checks the first character, the opening parenthesis, and the
closing parenthesis.

The check did not change:

- `CompactConstructor.getCompactData`;
- `FIRST_PATTERN`;
- `PROPERTY_NAME_PATTERN`;
- the YAML files;
- the test methods;
- the assertions.

Thus, the normal compact-data parser still processed each candidate after
the shape test.
This code change was only a check.
It is not a proposed production fix.

Ten interleaved check pairs were green.
Each arm again ran the same 349 classes.
The complete-suite times were:

```text
front: 2988, 3728, 3976, 3759, 3634, 3435, 4073, 3920, 3836, 4046 ms
back:  3582, 3714, 3691, 3707, 3859, 3493, 4046, 3874, 3783, 4121 ms
```

The paired `back - front` differences were:

```text
+594, -14, -285, -52, +225, +58, -27, -46, -53, +75 ms
```

The front order won 4 of 10 pairs.
The paired median was -20.5 ms.
The absolute paired median decreased by 96.4%, from 567.5 to 20.5 ms.
The stable baseline direction was absent.

The check data is in:

### 12.5 Java-version limit

This effect is limited to the tested Corretto 8 JVM.
The same test took only about 7 to 45 ms in the Java 11 and Java 17 runs that
this study inspected.
The study does not claim the same effect on those JVMs.

An order generator must record the target Java version.
It must not apply this Java 8 order constraint to a later JVM without a new
measurement.

The supported Java 8 order constraint is:

```text
CompactConstructorErrorsTest -> the other 348 paper classes
```

### 12.6 Abstraction

This mechanism is in the Java regular-expression library.
One test calls a recursive regular expression that is expensive on the target
Java 8 JVM.
The path is slower after the other test classes have run.
Removing only the initial regular-expression gate removes the stable
complete-suite difference.

An order generator must find hot paths in platform libraries as well as
project code.
It must keep JVM-version-specific constraints separate.

## 13. State leaks without a confirmed run-time effect

These leaks are real.
They do not yet have a measured run-time consumer.
CSTO2 must not use them as speed evidence.

### 13.1 SnakeYAML line separator

`DumperOptionsTest` changes `line.separator` four times.
The last value is `"\n\r"`.
See:

`snakeyaml/src/test/java/org/yaml/snakeyaml/DumperOptionsTest.java:213-240`.

The test does not restore the old value.
Only `DumperOptions.LineBreak.getPlatformLineBreak()` reads this property in the project tests.
No material run-time consumer was found.

### 13.2 Commons Text properties

`StringSubstitutorTest` writes `test_key=test_value`.
See:

`commons-text/src/test/java/org/apache/commons/text/StringSubstitutorTest.java:253`.

The same class writes `doesnotwork=It works!`.
See the same file at line 1063.

The test does not remove these properties.
The deprecated `StrSubstitutorTest` writes the same keys at lines 369 and 780.
Repository search found no other consumer for these exact keys.

### 13.3 Paimon context class loader

`CodeGeneratorContextTest` changes the thread context class loader.
See:

`paimon-codegen/src/test/java/org/apache/paimon/codegen/CodeGeneratorContextTest.java:31-34`.

The test does not restore the old loader.
If this test runs before `EqualiserCodeGeneratorTest`, generated classes use the wrong loader.
This order has 221 test failures.
The reverse order is green.

This is a correctness mechanism.
It is not a speed mechanism.
CSTO2 must reject the failing order before it compares run time.

## 14. Candidates that this study rejected

### 14.1 JavaParser language level

`Issue3577Test` leaves Java 15 as the static parser language level.
A two-class test first showed an approximately 9% difference.
Later pairs changed direction.
Run-slot drift explains the result.
This mechanism is not confirmed.

### 14.2 Commons CSV file cache

`PerformanceTest` reads one large temporary file ten times.
The measured direction changes with host and file-system state.
This is page-cache noise on this host.
This mechanism is not confirmed.

## 15. Requirements for an order generator

The evidence gives these requirements:

1. Use one reused test fork when the production test job uses one reused test fork.
2. Reject each order that has a failure.
3. Record shared-state writes at each class boundary.
4. Find the later code that reads each changed value.
5. Represent a harmful producer-to-consumer relation as a directed edge.
6. Put a harmful producer after its consumers.
7. Find cheap tests that execute the same application paths as a large consumer.
8. Put useful cheap initializers before the large consumer.
9. Find tests that compile the hot paths of a large repeated consumer.
10. Put useful compilation producers before that consumer.
11. Record production types that test tools transform.
12. Put harmful inline-mock producers after large consumers of the transformed type.
13. Use JFR and stack profiles to explain a stable paired result.
14. Do not use total allocation, compilation time, class loads, or garbage collection as proof by itself.
15. Exclude file-system noise and old JVM effects unless the target environment requires them.
16. Record properties that static initializers read.
17. Set diagnostic and instrumentation policies when the test fork starts.
18. Use operating-system counters as supporting evidence, not as causal proof.
19. Record derived configuration caches after a test restores a source property.
20. Treat a change in resource-pool selection as a directed order constraint.
21. Record the shared framework paths and the generated case count for generated suites.
22. Record compiler work that continues after a test boundary.
23. Record the installed tier and uncommon traps for a later hot method.
24. Find expensive paths in platform libraries as well as project code.
25. Apply a JVM-specific order constraint only to the measured JVM version.

The most important distinction is:

```text
harmful persistent state -> producer goes late
useful initialized state -> initializer goes early
```

An optimal order can require both relations at the same time.
