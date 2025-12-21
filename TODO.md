# TODO

## Historical summary (brief)
- Base Textual UI (two-column transcript/narration, status bar, command input) is wired through `module/ui_helper` and `module/game_controller`; the runtime launches via `main.py` and respects the existing config/logging structure.
- Core LLM orchestration (`module/completions_helper`) and REST plumbing (`module/game_api`, `module/rest_helper`) are in place, with strict schema enforcement defined in `config/response_schema.json`.
- Configuration loading (`module/my_config`) and logging initialization (`module/my_logging`) already read from `config/config.json` and expose the basic log paths.

## Future work (chronological backlog, grouped hierarchically)

### 1. Foundation: unify configuration and schema awareness
- [x] Consolidate the scattered config validation logic noted in `scratchpad/02_main_game_loop.md`: centralize the static key lists now duplicated across `main.py`, `my_config.py`, and `my_logging.py` into a single validation helper (e.g., one schema-driven registry) so future keys only need to be listed once.
- [x] Introduce explicit config keys for all schema paths (`game_engine_schema_path`, `ai_engine_schema_path`) and ensure `my_config`/`my_logging`/bootstrap load them; this matches the heuristics doc’s insistence that schema paths be config-driven.

### 2. Canonical heuristics/parsing pipeline
- [x] Build `module/game_engine_heuristics.py` (per `scratchpad/04_heuristics.md`): schema-driven parsers for room, score/move metrics, inventory, visible items, description, and metadata, replacing ad-hoc helpers such as `GameController._extract_room`/`_parse_game_metrics`. This module should be the single source of truth so duplicates are eliminated.
- [x] Decide the fate of `GameAPI.EngineTurn.raw_response`: either enrich the heuristics parser by reusing the raw JSON payload or drop the unused field once parsing is centralized.
- [x] Create `module/ai_engine_parsing.py` (or similar) so LLM outputs are validated/normalized before being passed to memory/completions, aligning with the heuristics doc’s recommendation to keep parse logic schema-first.

### 3. Memory & contextual prompt support
- [x] Implement the TinyDB-backed `GameMemoryStore` described in `scratchpad/05_game_memory.md`/plan prompt: episodic history (last N turns), persistent `Scene` objects, and context serialization that provides `get_context_for_prompt()` and `reset()` used by the controller.
- [x] Ensure the new memory module logs conflicts/state changes via `my_logging.log_memory_*` helpers and surface context for `CompletionsHelper` without redundant transcript parsing.

### 4. Controller wiring & session lifecycle hardening
- [x] Wire `GameController` to instantiate the new memory store, feed it `EngineTurn` data, and call `self._memory.get_context_for_prompt()` (instead of the current crash). Populate `_memory` during `_async_init_session`/`_async_play_turn`, and ensure `_handle_restart()` and `player rename` flows reset the memory store.
- [ ] Implement the session lifecycle API from `scratchpad/06_game_controller.md` (clean `start_session`, `change_player`, status events). When status changes (engine/AI/score/moves), emit clear signals so the UI can re-render the split status bar without duplicating logic.
- [x] Ensure `GameController` no longer re-implements heuristics—consume the canonical parsers from step 2 so metrics/room updates propagate consistently and the diagnostics referenced in scratchpad 04 are satisfied.
- [ ] Implementation plan: enforce the **Canonical Turn Lifecycle Contract** (see `scratchpad/06_game_controller.md`)
	- [ ] Treat the `GameAPI.start()` intro transcript as **turn 0**: parse via `game_engine_heuristics`, then call `GameMemoryStore.update_from_engine_facts(...)` *before* any prompt construction or narration so the first player command always has full context.
	- [ ] Add explicit memory transaction envelope events (e.g., `turn_recorded`, `turn_skipped_engine_exception`) to `*_memory_transactions.jsonl` so each turn has a clear begin/end boundary in logs.
	- [ ] Remove or deprecate the `narration` parameter on `GameMemoryStore.update_from_engine_facts` to prevent split narration pathways; enforce that narration storage happens only via `append_narration` after completions.
	- [ ] Add a regression test ensuring ordering: for a single turn, the memory transaction is recorded and `get_context_for_prompt()` reflects the updated `turn_count` **before** `CompletionsHelper.run(...)` is called.

### 5. Logging & observability refinements
- [x] Expand `module/my_logging.py` with the memory-scoped helpers described in the plan (`log_memory_event`, `log_state_change`, `log_memory_conflict`) so memory transitions are captured in JSONL rather than buried.
- [x] Recompute player-scoped log paths (engine/completions) whenever the player name changes, as the controller’s rename flow now needs to reopen those files per plan.
- [ ] Restore the design rule that a player rename forces a full session restart: stop the current dfrotz session, reset `_memory`, clear transcript/narration, recreate the `GameAPI` with the new label, and only then reopen player-scoped logs. Document and wire these steps so logging/memory never straddle two player identities in one session.

### 6. UI/UX polish & optional panels
- [ ] Scaffold the optional tabs from `scratchpad/03_TUI_design.md`/plan prompt: Items tree, Visited Rooms, Achievements, Todo List. Even placeholder widgets should exist so the layout can expand later, and the right column can switch between Narration and the tabbed content.
- [ ] Add the palette picker hook/command palette noted in the plan (e.g., hooking the footer `Palette` cell to an overlay) and ensure the command input placeholder can shift modes (normal vs. system input) in line with the design notes.

### 7. Testing, documentation, and polish
- [ ] Add unit tests for the canonical heuristics parsers: room extraction, score/moves metrics, inventory, and other schema fields using representative transcripts as called out in `scratchpad/04_heuristics.md`.
- [ ] Create example schema files (under `schemas/`) for `game_engine_schema` and `ai_engine_schema`, reference them in `config/config.json`, and document their purpose so future contributors can follow the schema-first principle.
- [ ] Revisit `config.json` extras (`voice_settings`, `enable_image_companion`, `stream_only_narration`) and either implement supportive code paths or remove the dead config fields to keep the config lean, aligning with the “simplicity focus” value list.

## Notes
- Priority order follows the logical bootstrapping sequence: stabilize config/heuristics, add memory, wire controller, then polish logging/UI/testing.
- Historical items are kept minimal here; the backlog now focuses on next steps informed by the collected markdown TODOs and current code gaps.
- Memory transactions now run before prompt building so the LLM context reflects the latest turn, and narration additions append immediately after the completion.

# TODO: Desirable: