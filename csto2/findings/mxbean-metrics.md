# MXBean metrics inventory

Everything the JDK's platform MXBeans (`java.lang.management`, plus the `com.sun.management`
extensions) can measure. ✅ = consumed by candidate generation today. Everything else is available
but unused.

Reading one of these is a counter fetch costing nanoseconds to microseconds. At one sample per test
class, that is negligible. The two rows marked 💥 are the exception.

| MXBean | Metric | Used | What it measures |
|---|---|---|---|
| `CompilationMXBean` | `getTotalCompilationTime` | ✅ `jitMs` | total time the JIT compiler threads have spent compiling (→ `jit-sort`) |
| `ThreadMXBean` (`com.sun`) | `getThreadAllocatedBytes` | ✅ `allocBytes` | total heap bytes each thread has allocated (→ alloc-front, pkg-alloc-front, alloc-sort) |
| `ClassLoadingMXBean` | `getTotalLoadedClassCount` | | number of classes loaded since JVM start |
| `ClassLoadingMXBean` | `getUnloadedClassCount` | | number of classes unloaded since JVM start |
| `GarbageCollectorMXBean` | `getCollectionCount` / `getCollectionTime` | | number of collections and total pause time, reported separately per collector (young vs. full) |
| `GarbageCollectorMXBean` (`com.sun`) | `getLastGcInfo` | | per-pool usage before and after the most recent GC, i.e. how many bytes it reclaimed |
| `MemoryMXBean` | `getHeapMemoryUsage` / `getNonHeapMemoryUsage` | | current heap and non-heap usage (used / committed / max) |
| `MemoryPoolMXBean` | `getPeakUsage` (resettable) | | highest usage each memory pool has reached since the last reset; resetting at each class boundary gives a per-class peak |
| `MemoryPoolMXBean` | `getCollectionUsage` | | usage of each pool immediately after its last GC, which approximates live data |
| `MemoryPoolMXBean` | CodeHeap pools' `getUsage` | | space taken by compiled machine code; growth during a test means the JIT produced new code |
| `ThreadMXBean` | `getThreadCount` / `getTotalStartedThreadCount` | | live thread count and cumulative threads-started count |
| `ThreadMXBean` | `getThreadCpuTime` / `getThreadUserTime` | 💥 | CPU time used by a single thread; costs microseconds per call, which adds up when polling many threads |
| `ThreadMXBean` | blocked/waited counts and times | 💥 | how often and how long each thread sat blocked on locks; off by default, and while enabled it adds bookkeeping to contended lock operations |
| `OperatingSystemMXBean` (`com.sun`) | `getProcessCpuTime` | | total CPU time used by the whole JVM process; CPU time in excess of a test's wall-clock time was spent on background threads (JIT compiler, GC) |
| `OperatingSystemMXBean` (`com.sun`) | `getSystemCpuLoad` / memory / swap | | system-wide CPU load, physical memory, and swap |
| `UnixOperatingSystemMXBean` | `getOpenFileDescriptorCount` | | number of open file descriptors |
| `BufferPoolMXBean` | `getMemoryUsed` / `getTotalCapacity` | | memory held by direct and memory-mapped NIO buffers; off-heap, so `getThreadAllocatedBytes` does not count it |
| `RuntimeMXBean` | `getUptime` / `getInputArguments` | | JVM uptime and launch arguments |
