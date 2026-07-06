# REPL ↔ Headless CLI Parity via Shared Orchestrator

Date: 2026-07-06

This document outlines the design to extract a shared Orchestrator from `Repl` to run all CSTO v2 menu options headless, using a persisted config.

## Goals

1. **Shared Orchestrator (`com.csto2.cli.Orchestrator`)**:
   - Holds shared configuration `cfg`.
   - Contains all orchestration actions (`loadProject`, `discover`, `analyze`, `trace`, `select`, `validate`, `fullPipeline`, `scientific`, `exclude`, `approaches`, `state`, `configure`).
   - No interactive prompting. Inputs are passed as parameters (e.g. `boolean autoYes` for compilation or list of tokens for exclude). Missing required config throws an exception.
2. **Config Persistence**:
   - Save configuration to `<out>/config.properties` using standard Java Properties file format.
   - Automatically save config after mutating actions (`configure`, `project`, `exclude`, `approaches`).
   - Load config and overlay CLI flags when executing headless commands.
3. **Headless CLI Surface (`Csto2.dispatch`)**:
   - Add new subcommands: `configure`, `state`, `exclude`, `approaches`, `project`, `pipeline` (runs `fullPipeline`), `scientific`.
   - Maintain compatibility of existing subcommand cases (`analyze`, `discover`, `trace`, `validate`, `select`) but route them through the Orchestrator when appropriate, or retain raw stage cases to prevent infinite recursion.
4. **Refactored `Repl`**:
   - Thin interactive wrapper that handles prompt-based input and delegates to `Orchestrator`.

## Design Details

### 1. The `Orchestrator` Class
We will create `com.csto2.cli.Orchestrator`. It will hold:
```java
public final class Orchestrator {
    public interface Confirmer {
        boolean confirm(String message) throws IOException;
    }
    
    public final Map<String, String> cfg = new LinkedHashMap<>();
    // methods moved from Repl:
    // loadProject(Path dir, Confirmer confirmer)
    // discover(), analyze(), trace(), select(), validate()
    // fullPipeline(), scientific()
    // exclude(List<String> tokens)
    // approaches(List<String> toggles)
    // loadConfig(), saveConfig()
    // loadPersistedExclusions()
    // ...
}
```

### 2. Configuration Persistence
The configuration will be persisted in `<out>/config.properties`.
- **`loadConfig()`**: Reads `config.properties` (if present) into `cfg`.
- **`saveConfig()`**: Writes all keys in `cfg` (both CONFIG_KEYS and derived artifacts/exclusions) into the properties file.
- **CLI Flow**:
  1. Determine `<out>` (default `.csto2`, or overridden by CLI flags).
  2. Instantiate `Orchestrator` and call `loadConfig()`.
  3. Overlay any CLI flags on top of the loaded `cfg`.
  4. Run the requested action.
  5. Call `saveConfig()` at completion.

### 3. Headless CLI Verification & Verb Mapping
Headless subcommands maps 1:1 to REPL actions:
- `csto2 configure --cp ... --tests ...` -> overlays flags and saves config.
- `csto2 state` -> shows resolved config and artifacts.
- `csto2 exclude <classes>` -> resolves and persists exclusions.
- `csto2 approaches <toggles>` -> resolves and persists candidate strategies.
- `csto2 project --dir <dir>` -> autodetects Maven project configuration.
- `csto2 pipeline` -> runs discover -> trace -> select.
- `csto2 scientific` -> runs pipeline at repeats=10 + Wilcoxon signed-rank report.

Existing subcommands (`discover`, `analyze`, `trace`, `select`, `validate`) remain available as low-level stages for direct executions.
