# Minimal Main Loop — Notes Only

1. **Setup**
   - Ask the config module to self init and load the config and schema jsons
   - Ask the logging module to self init and load the config and schema jsons
   - Instantiate the REST helper (it owns every HTTP detail) to self init and init the game engine
   - Ask the game controller helper to self init with all its internal objectives and states
   - Ask the TUI helper to self init and draw
- TODO: Collapse and centralize configuration validation and loading flows. Remove duplicated static key lists across `main.py`, `my_config`, and `my_logging`; unify into a single, maintainable mechanism.

2. **Turn Cycle**
   1. Minimal orchestration between modules

3. **Exit Conditions**
   - Player enters `/quit` or other UI exit actions

4. **Teardown**
   - Ask the helper to stop the session/PID.
   - Flush logs, close files.
