# Logging Strategy

## Meta-Objective
- Preserve a clean separation between **structured telemetry** (JSONL files meant for replay/analytics) and **narrative event logs** (plain-text `system.log`).
- Keep every log path **config-driven** via `my_logging.init()` so deployments can relocate storage without code edits.
- When `loglevel=DEBUG`, emit **full-fidelity JSON objects** to the JSONL streams (game, engine, completions, REST, GameAPI) while keeping the system log focused on readable sentences about lifecycle, status, and errors.
- Ensure any change to the player identity (rename or restart) **rebinds every player-scoped log** and restarts the dfrotz session so memory, telemetry, and transcripts never mix identities.
- Treat logging as an observability contract: controllers and helpers must prefer the helpers in `module/my_logging.py` instead of writing files directly.

## Existing Guidance (for traceability)
- `scratchpad/00_coding_principles.md` & `scratchpad/02_main_game_loop.md` establish the config-first, fail-fast logging philosophy.
- `scratchpad/06_game_controller.md` mandates that only engine/completion logs are player-scoped and that renames trigger a full session reboot.
- This document supersedes scattered notes; future updates should land here first.

## Log Channels and Expectations

### System Log (`system_log`)
- **Scope:** Whole-application lifecycle, configuration summaries, high-level status changes, warnings/errors.
- **Format:** Plain-text lines with timestamp + level. Even at DEBUG it should describe events (“Renaming player…”) rather than dumping JSON payloads.
- **Writers:** `my_logging.system_*` helpers (controllers, UI, bootstrap, etc.).

### Game JSONL (`gameapi_jsonl` / `log_gameapi_event`)
- **Scope:** Canonical record of GameAPI requests/responses, parsed metadata, and memory events.
- **Format:** One JSON object per line. When DEBUG is disabled, only critical events should be written; with DEBUG enabled we record every stage (`request`, `response`, `parsed`).
- **Writers:** `GameAPI` via `my_logging.log_gameapi_event`, plus memory helpers (`log_memory_event`, `log_state_change`, `log_memory_conflict`).

### Player-Scoped Engine JSONL (`game_engine_jsonl_filename_template` → `log/{player}_game_engine.jsonl`)
- **Scope:** Raw engine I/O tied to the active player: `log_player_input`, `log_player_output`, and eventually parsed turn snapshots.
- **Format:** JSON objects capturing `{type: "input"|"output", command/transcript, pid, timestamp}`.
- **Player Rename Rule:** Any rename must stop the current session, reset memory, and call `update_player_logs(new_name)` only after the restart succeeds.

### Player-Scoped LLM Completions JSONL (`llm_completion_jsonl_filename_template` → `log/{player}_llm_completions.jsonl`)
- **Scope:** Inputs/outputs of `CompletionsHelper`, including payloads, token counts, schema validation results.
- **Format:** JSON entries appended by `log_completion_event`; include timestamps and any extra debugging metadata.

### REST Helper JSONL (`rest_jsonl`)
- **Scope:** Raw HTTP requests/responses between `DfrotzClient` and the dfrotz REST bridge.
- **Format:** JSON entries with method, URL, payload preview, status codes. Enabled only when DEBUG to avoid sensitive leakage in production.
- **Writers:** `module/rest_helper.py` via `log_rest_event`.

### Additional Considerations
- **Memory Module:** Once `GameMemoryStore` exists, every promotion/conflict must emit `log_memory_event`/`log_memory_conflict` so postmortems can reconstruct world-state evolution.
- **UI/Controller Hooks:** Status updates, lifecycle transitions, and user-facing events belong in the system log; structured payloads belong in their respective JSONL streams.
- **Testing/Diagnostics:** When analyzing run issues, inspect JSONL files for structured data and the system log for narrative context.

## Logging Meta-Objective Checklist
1. **Config-Driven Paths:** All log file destinations flow from `config/config.json` and are validated by `my_logging._require`.
2. **Player Identity Integrity:** Engine/completion logs are the only files that vary by player; renames restart the session before new files are opened.
3. **Structured vs. Narrative:** JSONL entries capture data; system log captures prose. Never mix.
4. **Debug Enrichment:** `loglevel=DEBUG` adds more entries but does not change formats. Info/Warn/Error remain meaningful when debug is off.
5. **Helper-Only Access:** Modules must not open files directly—use the helper functions to guarantee timestamps and consistent schema.

## Configured Log Paths (from `config/config.json`)

| Config Key | Resolved Path (player = Adventurer) | Objective & Scope | Canonical Writers |
| --- | --- | --- | --- |
| `system_log` | `log/system.log` | Plain-text lifecycle/status/error narratives for the whole app. | Any module via `my_logging.system_*` (main bootstrap, controller, UI). |
| `gameapi_jsonl` | `log/gameapi.jsonl` | Structured record of GameAPI requests/responses plus memory events. | `GameAPI` (`log_gameapi_event`), memory helpers (`log_memory_event`, etc.). |
| `rest_jsonl` | `log/rest_helper.jsonl` | Raw HTTP request/response metadata for dfrotz REST calls (debug-only). | `DfrotzClient` via `log_rest_event`. |
| `game_engine_jsonl_filename_template` | `log/Adventurer_game_engine.jsonl` | Player-scoped transcript of engine inputs/outputs and turn metadata. | `my_logging.log_player_input` / `log_player_output`, future turn emitters. |
| `llm_completion_jsonl_filename_template` | `log/Adventurer_llm_completions.jsonl` | Player-scoped history of LLM prompts/responses, token stats, schema validation. | `CompletionsHelper` via `log_completion_event`. |
