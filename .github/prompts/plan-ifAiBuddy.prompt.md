# Plan: Complete IF AI Buddy Implementation

This is a TUI-based interactive fiction companion that adds AI narration and guidance to a text adventure game (via the dfrotz REST engine). The core work involves: (1) building the missing UI layer using Textual, (2) implementing the AI completion helper for structured narration, (3) building the episodic memory system with TinyDB, and (4) wiring everything together in the game controller. The codebase has config, REST plumbing, and stubs in place; we're filling in the complete game flow.

## Implementation Steps

### 1. Create `ui_helper.py` with Textual TUI layout

**Responsibilities:**
- Define `AIStatus` and `EngineStatus` enums (IDLE, BUSY, READY, ERROR)
- Define `StatusSnapshot` dataclass to hold player, game, room, moves, score, and status values
- Implement `IFBuddyTUI` class wrapping a Textual app with:
  - Two-column main layout: left column for game transcript (scrollable `RichLog`), right column for narration/tabs (switchable `ContentSwitcher`)
  - Footer strip with:
    - Command input field (always focused after turns)
    - Status bar showing player (clickable), room, moves, score, engine status, AI status
  - Header with title and key bindings
  - Tab placeholder widgets (Items tree, Visited Rooms, Achievements, Todo List) for future implementation
- Implement `create_app()` factory function accepting initial status and callbacks (on_command, on_player_rename, on_restart)
- Methods for adding transcript output, narration text, hints; updating status; resetting sections; managing engine/AI status

**Key Design Patterns:**
- Use Textual `worker` decorator for async operations (REST calls, LLM completions)
- Status updates should trigger re-renders via callback/binding patterns
- All UI strings should be from config (placeholder logic for now)
- Keep widget tree simple: Header, Container(Left/Right), Footer

---

### 2. Create `ai_buddy_memory.py` with TinyDB-backed memory

**Responsibilities:**
- Define `EpisodicMemory` dataclass: `[{ turn: int, command: str, transcript: str, timestamp: datetime }]` (keep last N=10 turns, FIFO)
- Define `GameState` dataclass: `{ rooms: [{name, description, items}], inventory: [items], npcs: [(name, location)], objectives: [tasks], recent_changes: [events] }`
- Implement `GameMemoryStore` class:
  - Initialize TinyDB at player-scoped path (from config template)
  - `add_episodic_event(turn, command, transcript)` → appends to episodic ring, ages out old turns
  - `extract_and_promote_state(transcript)` → parse game output for rooms, items, inventory hints; promote stable facts to GameState; log conflicts
  - `get_context_for_prompt()` → return last N episodic turns + current GameState as structured dict
  - `log_state_update(event_type, change)` → write to game-scoped JSONL
  - Clear/reset methods for player changes
- Implement simple regex/heuristic parsers for detecting:
  - Room transitions (capitalized lines followed by descriptions)
  - Inventory state (match "You are carrying:" patterns)
  - Item interactions (verbs like "taken", "dropped", "used")
- Ensure all updates are logged to JSONL with timestamp per my_logging rules

**Key Design Patterns:**
- Episodic memory is volatile (FIFO ring); in-game state is stable but validated/updated per turn
- Do NOT embed TinyDB queries in GameAPI or controller; all memory ops live here
- Log memory conflicts (e.g., inventory mismatch) to system log at DEBUG level
- Keep regex patterns configurable (load from JSON if needed later)

---

### 3. Create `completions_helper.py` with LLM orchestration

**Responsibilities:**
- Implement `CompletionsHelper` class:
  - Constructor accepts `config: dict`, `response_schema: dict`, `llm_client: openai.OpenAI | FoundryLocalClient`
  - `run(transcript_chunk: str, context: dict) -> dict` → builds prompt, calls LLM, parses response
- Build prompt from:
  - System prompt (from config `system_prompt`, interpolate `{response_schema}` JSON string)
  - User prompt (from config `user_prompt_template`, interpolate `{game_log}` as recent transcript)
  - Optional context (episodic memory, current state) embedded in user message
- Call LLM based on `config.llm_provider` (`openai` or `foundry`):
  - Use `response_format=schema` for strict JSON output
  - Respect `config.llm_temperature`, `config.max_tokens`
  - Handle `stream=False` for now (streaming in Phase 2)
- Parse response:
  - Extract JSON from response.content (strip markdown fences if present)
  - Validate against schema; log parse failures
  - Fallback to minimal narration ("The game continues...") if parse fails
  - Return dict with keys: `payload` (validated JSON), `raw_response` (SDK response), `diagnostics` (latency, tokens, model)
- Inject `llm_client` as dependency for testability
- Log all requests/responses to completions JSONL via my_logging

**Key Design Patterns:**
- Fail gracefully on parse errors; log fully for debugging
- Schema enforcement is non-negotiable (use SDK strict mode)
- Don't retry on failure (caller responsibility)
- Return structured dict always, never raise on schema mismatch (downgrade quality instead)

---

### 4. Refactor `game_controller.py` to wire the full flow

**Responsibilities:**
- Add instance vars:
  - `_rest_client: DfrotzClient` (async)
  - `_game_api: GameAPI` (async)
  - `_memory: GameMemoryStore` (sync TinyDB wrapper)
  - `_completions: CompletionsHelper` (sync or wrapped async)
  - `_session: GameSession | None`
- Implement `async def _initialize_session()`:
  - Create DfrotzClient with base_url from config
  - Create GameAPI
  - Call GameAPI.start() to get intro text
  - Add intro to TUI transcript
  - Set engine status to READY
- Implement `_handle_command(command: str)`:
  - Log command via my_logging
  - Set engine status to BUSY
  - Schedule async task to:
    - Call GameAPI.send(command) → TurnOutcome
    - Parse moves/score from transcript via regex
    - Update memory with turn + extract state
    - Call completions_helper.run(transcript, memory context)
    - Add transcript to TUI left column
    - Add narration to TUI right column
    - Update status (moves, score, room, engine/AI status)
    - Set engine/AI status to READY
  - Use Textual `worker` or `call_later` for non-blocking
- Implement `_handle_player_rename(new_name: str)`:
  - Stop current session
  - Reinitialize memory with new player name
  - Restart GameAPI with new label
  - Clear TUI transcript and narration
  - Add intro text
- Implement `_handle_restart()`:
  - Stop current session
  - Reset memory state
  - Restart GameAPI
  - Clear TUI
- Add regex parsers for:
  - `Score: \d+ Moves: \d+` patterns
  - Room transitions (heuristic: capitalized line at start of output)
- Ensure all status transitions emit via TUI callbacks

**Key Design Patterns:**
- Keep controller as thin orchestrator; delegate actual work to helpers
- Use async/await properly; wrap in Textual workers if needed
- All user-facing errors should be logged and shown in TUI (never raise silently)
- Status updates must be atomic and consistent (use TUI.update_status() as single source)

---

### 5. Extend `my_logging.py` with memory-scoped logs

**Responsibilities:**
- Add helper functions:
  - `log_memory_event(event_type: str, data: dict) -> None` → write to game-scoped JSONL with timestamp
  - `log_state_change(field: str, old_value: Any, new_value: Any) -> None` → specialized log for state diffs
  - `log_memory_conflict(description: str, evidence: str) -> None` → log conflicts to system log at WARNING level
- Ensure all player-scoped log paths use `_ENGINE_LOG_PATH`, `_COMPLETIONS_LOG_PATH` computed at init with player_name
- When player name changes, re-initialize log paths (caller responsibility in controller)
- Keep JSON format consistent: `{ "timestamp": "...", "type": "...", ...data }`

**Key Design Patterns:**
- Log at DEBUG level by default; always write to JSONL (not stdout)
- Memory module calls these helpers; they abstract file I/O
- No in-function file opens; all paths pre-computed at init

---

### 6. Update `main.py` to initialize all layers

**Responsibilities:**
- Load config and fail fast if missing required keys (per 00_coding_principles.md)
- Initialize logging with player_name from config
- Verify dfrotz_base_url and response_schema.json exist and are valid
- Create GameController with config
- Catch and log any bootstrap errors; exit cleanly with clear message
- Keep main.py thin: ~40 lines max

**Key Design Patterns:**
- Use my_config.load_config() to get dict
- Validate config keys before passing to controller (use try/except, log, re-raise)
- Never silently fall back to hardcoded defaults

---

## Further Considerations

### A. Async vs. Sync Integration
- **Current state:** REST helper and GameAPI are async; Textual run() is sync.
- **Recommendation:** Use Textual's `worker` decorator for async tasks (REST calls, LLM completions). This gives us non-blocking gameplay loop without needing explicit threading.
- **Implementation:** Wrap async functions in controller with `@work(exclusive=True)` for turn handling.

### B. Memory Promotion on Conflict
- **Question:** When new game output contradicts in-game state, do we suppress the conflicting fact, annotate it, or rebuild state from transcript?
- **Recommendation:** Log conflict to system log at DEBUG level, suppress narration using conflicting fact, mark event as `contested: true` in JSONL for post-run review. In-game state remains until explicit game output overrides.
- **Implementation:** Add `_resolve_conflict()` helper in GameMemoryStore; return (resolved_fact, confidence_score).

### C. Optional UI Tabs
- **Current state:** Scratchpad 03_TUI_design.md mentions tabs (Items tree, Visited Rooms, Achievements, Todo List) but marks as "not to be implemented yet."
- **Recommendation:** Scaffold empty widget stubs now (define placeholder Containers) so layout doesn't break when we add content later. Use `ContentSwitcher` to toggle between Narration and Tab views.
- **Implementation:** In ui_helper.py, define a `TabsPanel` with empty tab widgets; wire ContentSwitcher to cycle through them.

### D. Streaming Toggle
- **Current state:** Config has `stream_only_narration: true` but completions_helper notes say "streaming turned off for now."
- **Recommendation:** Implement completions_helper without streaming first (use `stream=False`). Once core flow is stable and tested, add streaming in Phase 2 with proper chunk parsing and TUI rendering.
- **Implementation:** Add `_stream_narration()` method stub; default to `run(stream=False)` in Phase 1.

### E. Error Handling & Observability
- **Logging locations:**
  - System log: controller startup, player actions, status changes, errors
  - Game JSONL: game state snapshots, parsed world state, memory updates
  - Engine JSONL: REST request/response pairs, latency, status codes
  - Completions JSONL: LLM prompts, responses, parsing results, token counts
- **TUI display:** All errors shown in status bar (color-coded red) and logged; gameplay continues unless unrecoverable (e.g., REST endpoint down, config missing).

### F. Testing Strategy (Post-Implementation)
- Unit tests for parsers (game output → state) with example transcripts
- Integration test for full turn cycle (mock REST, mock LLM, check memory updates)
- TUI smoke tests (click buttons, verify callbacks, check widget updates)
- Manual testing with live dfrotz emulator + Foundry/OpenAI

---

## File Dependency Graph

```
main.py
  ├─ my_config.py (load config)
  ├─ my_logging.py (init logging)
  └─ game_controller.py
       ├─ rest_helper.py → DfrotzClient (async)
       ├─ game_api.py → GameAPI (async)
       ├─ ai_buddy_memory.py → GameMemoryStore (TinyDB)
       ├─ completions_helper.py → CompletionsHelper (LLM)
       └─ ui_helper.py → IFBuddyTUI (Textual app)
```

---

## Acceptance Criteria

- [ ] UI renders with two-column layout, footer status bar, command input
- [ ] Player can enter commands; they appear in left column
- [ ] Game transcript streams into left column; room name updates in status
- [ ] AI narration generates from schema-constrained LLM call; appears in right column
- [ ] Score/moves parsed from transcript and displayed in status
- [ ] Player rename flow restarts session cleanly
- [ ] All logs written to config-specified JSONL paths with timestamps
- [ ] No uncaught exceptions; errors logged and shown in TUI
- [ ] Code follows 00_coding_principles.md: config-driven, fail-fast, DRY, clear logging

