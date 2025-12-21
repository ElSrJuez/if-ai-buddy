# Game Controller Helper — Replacement Design

## Goals
- Remain a thin orchestrator between the TUI, the dfrotz REST engine, and the AI companion helper.
- Respect new logging rules: only game and completion logs are player-scoped; canonical system log paths come straight from config.
- Provide identity management inside the TUI (no CLI prompts). Player name changes must reset the game session cleanly.
- **Enforce the canonical turn lifecycle** so every component (heuristics, memory, logging, completions) follows the same deterministic flow and there are no scattered hooks or race conditions.

## Canonical Turn Lifecycle Contract

Every turn (including the initial welcome) must follow this sequence, and no component may deviate:

1. **Parse**: `GameController` receives the raw engine transcript and calls `game_engine_heuristics.parse_engine_facts(transcript)` once, producing a single authoritative `EngineFacts` object.
2. **Record**: Before building any prompt, immediately call `GameMemoryStore.update_from_engine_facts(facts, command, previous_room)`. This is the single write point where:
   - The turn is incremented in the memory store
   - A new or existing `Scene` is updated with the parsed facts
   - TinyDB persistence happens atomically
   - JSONL memory transaction events are emitted (via `my_logging.log_memory_event`)
   - The controller's status fields (room, moves, score) are derived from the same `EngineFacts`
3. **Context**: Call `GameMemoryStore.get_context_for_prompt()` to retrieve the fresh memory context now that the turn has been recorded. This context reflects the current state and is passed to the AI helper.
4. **Prompt & Completion**: Pass the transcript and context to `CompletionsHelper.run(...)`, which normalizes the LLM response via `ai_engine_parsing.normalize_ai_payload` and returns the narration.
5. **Append Narration**: Call `GameMemoryStore.append_narration(room, narration)` to store the AI-generated narration in the scene's narration list and emit the corresponding JSONL event.

### Why this order matters:
- No component re-parses the transcript; `game_engine_heuristics` is the sole source of truth.
- Memory is never stale: prompts always see the latest recorded turn before being constructed.
- Logging (engine JSONL, memory JSONL, completion logs) happens at predictable points, so the transaction history is coherent.
- The turn is atomically recorded before any side effects (narration, prompt building) occur, avoiding half-finished states.
- Every module respects the same sequence, so future contributors cannot accidentally add hooks in the wrong place.

### Initial session (turn 0):
The welcome transcript from `GameAPI.start()` is treated identically: parse it, call `update_from_engine_facts` to record the introduction scene, then emit the "Let's begin your adventure..." narration via `append_narration`. This ensures the initial state is already in memory when the first player command arrives.

### Scope:
This contract applies to every turn flow—standard player commands, restarts, and any future async paths. If a new feature needs to modify the game state, it must insert at the appropriate step (usually as a new turn record) rather than bypassing the contract.

## Responsibilities
1. **Session Lifecycle**
   - Read defaults (`player_name`, `default_game`) from config.
   - Create the `GameAPI` client with a session label equal to the current player name.
   - Expose `start_session(player_name: str | None = None)` which reboots the engine when the user changes their name.

2. **Status Model**
   - Track a simple status dataclass: `{ player, game, engine_status, ai_status, score, moves }`.
   - Emit status updates to the TUI so it can render the split status line.
   - `engine_status` reflects dfrotz connectivity; `ai_status` reflects last AI request/response; both default to `Idle`.

3. **Logging Hooks**
   - Use `system_log`, `game_jsonl`, `game_engine_jsonl_filename_template`, `llm_completion_jsonl_filename_template` from config.
   - When the player name changes, re-compute the templated filenames and reopen the rotating logs.

4. **Player Interaction**
   - Provide `controller.change_player(new_name: str)` called when the TUI name label is clicked.
   - The rename flow now: close the existing session, reset `GameMemoryStore`, restart transcripts/narrations, rebuild player-scoped logs (engine/completions/memory) via `my_logging.update_player_logs`, then swing into a fresh `start_session` against the renamed `GameAPI` label so logs, memory, and engine state never cross player boundaries.

5. **Turn Flow**
    - `controller.play_turn(command: str)`
       - Send command to `GameAPI`
       - Parse the returned transcript via `game_engine_heuristics` into `EngineFacts`
       - Immediately call `GameMemoryStore.record_turn` (or the existing `update_from_engine_facts`) with the parsed facts, command, and previous room so the memory JSONL transaction and TinyDB update happen *before* any prompt is constructed
       - Use the fresh memory context for the prompt, send it to `CompletionsHelper`, receive narration, append that narration through `GameMemoryStore.append_narration`, and only then consider the turn fully logged
       - Update status struct with the parsed room/moves/score and emit signals so the UI can render the split status bar based on the canonical heuristics output

6. **Status Line Layout (for TUI integration)**
   - Provide a tuple/dict the UI can render as: `AI: <ai_status> | Engine: <engine_status> | Game: <game_name> | Player: <player_name> | Moves: <moves> | Score: <score>`
   - Ensure `player_name` entries can be clicked; expose a callback or signal to controller.

## Status Update Rules
- **Room name**: first non-empty line of transcript after the command.
- **Moves/Score**: regex capture (`Score: X Moves: Y`).
- **Engine status**: Busy when awaiting REST response; Ready after success; Error on REST failure.
- **AI status**: Working when narration requested; Ready when narration returns; Idle when no narration; Error if LLM call fails.
- **Palette**: static label until palette picker is implemented.
- **Player name**: button label updates after rename flow; clicking prompts for new name and restarts session.


## Open TODOs
- Wire up the new AI helper once rebuilt.
- Decide whether score/move parsing happens via regex or a small parser helper.
- Provide events back to TUI when status changes so it can re-render the split status bar.


