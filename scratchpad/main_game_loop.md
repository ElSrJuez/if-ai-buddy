# Minimal Main Loop — Notes Only

1. **Setup**
   - Load `config.json` (model name, prompt, streaming toggle).
   - Read `response_schema.json` for the narrator contract.
   - Instantiate the REST helper (it owns every HTTP detail).
   - Ask the helper to start a single session and keep only the returned handle/PID.

2. **Turn Cycle**
   1. Collect the player command from the UI input box.
   2. Hand the command to the helper's `action(pid, text)` (no HTTP calls directly here).
   3. Append raw transcript lines to the interaction log.
   4. Build the simplest possible LLM prompt: last transcript chunk + schema header.
   5. Call the completion service once; expect narration + hints.
   6. Render: left panel = transcript, right panel = narration.

3. **Exit Conditions**
   - Player enters `/quit`.
   - Transcript includes obvious end markers ("*** You have died ***", "The End").
   - REST helper throws unrecoverable error.

4. **Teardown**
   - Ask the helper to stop the session/PID.
   - Flush logs, close files.
