# Mechanism 6: JavaParser symbol solver shared optimized code.
# Earlier tests C2-compile the generated parser; JavaParserTypeSolverTest (25 repetitions,
# 4 concurrent tasks) is 22.6% faster when it runs last. Whole-suite arms replicate the
# section 6 one-class move exactly. The pair is a PROXY (the mechanism is many-to-one;
# section 6 had no two-class experiment): one cheap parser-path test before the consumer.
MECHANISM="jps-jit"
NATURAL="jps.natural"
TRACK="com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolverTest"
PAIR_FAST="com.github.javaparser.ast.type.ClassOrInterfaceTypeTest com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolverTest"
PAIR_SLOW="com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolverTest com.github.javaparser.ast.type.ClassOrInterfaceTypeTest"
WHOLE_FAST_MOVES="back:com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolverTest"
WHOLE_SLOW_MOVES="front:com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolverTest"
