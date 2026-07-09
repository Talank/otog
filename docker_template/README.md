# CSTO v2 Docker Runner

This directory contains the Docker configuration to run CSTO v2 on target projects/modules in scientific mode.

## Available Configurations

The following modules from `modules.tsv` are pre-configured:
* **`1683`** - javaparser/javaparser (javaparser-symbol-solver-testing)
* **`3320`** - apache/curator (curator-recipes) [Excludes `TestWatcherRemovalManager`]
* **`3323`** - apache/curator (curator-framework) [Excludes `TestWatcherRemovalManager`, Configures develocity cache]
* **`33`**   - netty/netty (handler)
* **`3613`** - apache/paimon (paimon-core) [Uses Java 8]
* **`1685`** - javaparser/javaparser (javaparser-core-testing)
* **`20`**   - netty/netty (transport-native-epoll) [Compiles native epoll code]
* **`29`**   - netty/netty (transport)
* **`1778`** - spring-projects/spring-ai (models/spring-ai-openai) [Uses Java 17]
* **`1305`** - AsyncHttpClient/async-http-client (client)

## Building the Docker Image

From the repository root directory, run:

```bash
docker build -t csto2-runner docker_template
```

This will build a self-contained image with all required JDKs (8, 11, 17, 21), native development dependencies, the custom surefire testorder extension, and pre-packaged CSTO binaries and configurations.

## Running the CSTO Pipeline

Run a container for a specific module ID and mount a local folder to receive the results.

```bash
docker run --rm -v $(pwd)/results:/workspace/.csto2 csto2-runner <CONFIG_ID>
```

Replace `<CONFIG_ID>` with one of the available IDs listed above (e.g., `1683`).

### Example

To run the pipeline on `javaparser-symbol-solver-testing` (ID `1683`):

```bash
docker run --rm -v $(pwd)/results_1683:/workspace/.csto2 csto2-runner 1683
```

This will:
1. Clone the `javaparser` repo and checkout the target commit.
2. Load the Java 11 environment.
3. Automatically run Maven dependency resolution and project test compilation.
4. Execute the CSTO scientific pipeline (discovers runnable tests, runs trace measurements, shuffles and runs candidate orders).
5. Output the results and a paired Wilcoxon signed-rank rank test report in your local `results_1683/` folder.
