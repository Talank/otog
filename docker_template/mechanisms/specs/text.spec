# Mechanism 7: Commons Text persistent inline-mock instrumentation.
# TextStringBuilderAppendInsertTest makes Mockito-inline retransform TextStringBuilder;
# StringSubstitutorFilterReaderTest is 2.04x slower afterwards (10/10 pairs).
MECHANISM="text-mock"
NATURAL="text.natural"
TRACK="org.apache.commons.text.io.StringSubstitutorFilterReaderTest org.apache.commons.text.TextStringBuilderAppendInsertTest"
# Exact pair from mechanisms.md section 7.
PAIR_FAST="org.apache.commons.text.io.StringSubstitutorFilterReaderTest org.apache.commons.text.TextStringBuilderAppendInsertTest"
PAIR_SLOW="org.apache.commons.text.TextStringBuilderAppendInsertTest org.apache.commons.text.io.StringSubstitutorFilterReaderTest"
# Whole-suite: natural already has the reader (pos 27) before the producer (pos 94) = fast.
# Slow arm moves the mock producer to the front so the reader runs instrumented.
WHOLE_FAST_MOVES=""
WHOLE_SLOW_MOVES="front:org.apache.commons.text.TextStringBuilderAppendInsertTest"
