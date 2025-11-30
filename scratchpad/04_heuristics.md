# Heuristics & Parsing Guidelines

This document defines the project rules for all heuristics and AI parsing components. It is the canonical reference for how raw game-engine transcripts and AI-derived parsing should be processed, validated and surfaced to the rest of the application.

Principles
----------
- All heuristics must be schema-driven. Each heuristic implementation must accept/produce data that conforms to a declared JSON Schema.
- Schemas are config-driven. The active schema paths and any per-game schema overrides live in `config.json` (or environment variables) and are loaded by `my_config` at startup.
- Two separated pipelines:
  - `game_engine_heuristics`: processes raw parsing coming from the REST API game engine and direct player responses. These are deterministic, regex/heuristic based, and used to populate `game_memory` (formerly `game_buddy_memory`).
  - `ai_engine_parsing`: processes AI-based parsing related to the meta-game state and history. These are LLM-driven structured outputs (using the project `system_prompt` and `response_schema`), used for higher-level extraction and prompting efficiency.
- Functions must operate on object names and schema-driven properties rather than ad-hoc "extract_X" helpers. I.e., prefer `parse(transcript, schema)` that returns a structured object matching `schema` rather than many discrete `extract_room_name(transcript)` functions.
- Design all heuristics and AI parsing with the explicit aim to maximise AI prompting efficiency: small, high-quality fields (short strings), predictable keys, and no duplicate information across fields.

Modules & Responsibilities
--------------------------
- `game_engine_heuristics` (new module):
  - Input: `TurnOutcome.raw_response` (the complete, un-parsed game engine response).
  - Behavior: run schema-driven heuristics to extract stable, immediate facts (room, score, moves, visible items, short description, transcript text). Parses the raw response into a normalized object conforming to the configured `game_engine_schema`.
  - Output: structured dict conforming to `game_engine_schema` (includes `transcript` as one field among others).
  - Consumers: `game_memory` (for promotion into GameState), `GameController` (for status snapshot), logging.

- `ai_engine_parsing` (new module / reuse `completions_helper`):
  - Input: prompt context + transcript or memory excerpt.
  - Behavior: produce structured outputs aligned with `response_schema` using the LLM. Use compact fields to help subsequent prompts.
  - Output: structured dict conforming to `ai_engine_schema`.
  - Consumers: `game_memory` (for meta-state), `CompletionsHelper` workflows, analytics.

Design patterns
---------------
- Schema-first. Each parser implementation receives a JSON Schema reference and a data object. It returns a validated object. Validation errors are logged and fail-safe (either return `null` for fields or raise a controlled exception depending on config).
- Config-driven schema lookup. `my_config` should expose the schema path(s): e.g. `game_engine_schema_path` and `ai_engine_schema_path`.
- Single-responsibility. Parsers do parsing + light normalization only. Promotion of facts to persistent memory belongs to `game_memory`.
- No duplicate heuristics. Only one module is authoritative for a property. If `game_memory` needs the same parser, import the canonical parser from `game_engine_heuristics` rather than re-implementing.

Top-Level Object Schema
-----------------------

Scene Object Class:
Defines all of the heuristic and ai-inferred properties
- room_name: the canonical label of the current location (e.g. room name), captured from game output.
- ?

Game State Object:
Defines all of the heuristic and ai-inferred properties of the current Move of the game
This object is maintained by the individual modules as game progresses, and before switching to the new scene it is stored in the Moves table of the game database
- move number: 
- command: the exact player input text.
- room_name: 
- result: the raw text output from the game engine in response.
- timestamp: ISO 8601 string marking when the move was executed.
- associated objects: type and id of the associated objects (for example, room name, item name, npc name, )
- ?: ?

Game Item object:
- Object Name: 
- Location: either Player Inventory, room name, etc. 

NPC Object:
- npc name:
- room last seen:

xxx ?:
- id ?
- ?

TODO (moderated by new guidelines)
---------------------------------
Note: these TODOs are scoped according to the new rules (schema-driven, config-driven, single-responsibility).

**Audit findings (code review)**

- Duplicate room-name heuristic
  - Found: `GameController._extract_room()` and `GameMemoryStore._extract_room_name()` both extract the first capitalized line.
  - Impact: Same heuristic maintained in two places; risk of inconsistency if one is updated.
  - Action: Remove both; implement once in `game_engine_heuristics.parse()` as canonical.

- Score/moves parsing orphaned from memory
  - Found: `GameController._parse_game_metrics()` extracts Score/Moves via regex; `GameMemoryStore` ignores these entirely.
  - Impact: Metrics never stored in `GameState`; only UI displays them. Lost prompting context for AI.
  - Action: `game_engine_heuristics` should extract score/moves in schema. Memory should store them in `GameState`. Controller consumes results.

- Orphaned `TurnOutcome.raw_response`
  - Found: `GameAPI.send()` returns `raw_response` (dfrotz REST JSON), but no code reads it. Only `transcript` text is consumed.
  - Impact: Dead field.
  - Action: Once `game_engine_heuristics` is implemented, decide: richer parsing from raw JSON, or remove the field?

**Consolidation steps**

- Consolidate duplicate room heuristics
  - Find: `GameController._extract_room` and `GameMemoryStore._extract_room_name` both implement a capitalized-line heuristic.
  - Action: remove the controller helper; add `parse_room` to `game_engine_heuristics` and have `game_memory` call it from `extract_and_promote_state`. Update `GameController` to consume the structured result instead.

- Move score/moves parsing to `game_engine_heuristics`
  - Find: `GameController._parse_game_metrics` regex is the authoritative parser for score/moves but lives in controller.
  - Action: implement `parse_metrics(transcript, schema)` in `game_engine_heuristics`. `game_memory` and `GameController` should use that single implementation.

- Define and add config keys for schema paths
  - Find: schema files are read ad-hoc (some code loads `response_schema_path`).
  - Action: add `game_engine_schema_path` and `ai_engine_schema_path` to `config.json` and load them via `my_config` and `my_logging` initialization.

- Create `game_engine_heuristics` module
  - Implement small, well-tested, schema-driven parsing functions that accept `transcript`/`raw_response` and return validated objects.

- Create `ai_engine_parsing` module / align with `CompletionsHelper`
  - Ensure LLM outputs are validated against `ai_engine_schema` and normalized before being saved to `game_memory`.

- Update `game_memory` (formerly `game_buddy_memory`)
  - Ensure `extract_and_promote_state` delegates parsing to `game_engine_heuristics` and only handles promotion/storage.

- Tests & examples
  - Add unit tests for the canonical parsers (metrics, room, inventory, changes) with representative transcripts.
  - Add a sample `schemas/game_engine_schema.json` and `schemas/ai_engine_schema.json` to the repo and reference them from `config.json`.

Notes
-----
- Naming: the repo uses `game_memory` as the new name — adopt that everywhere.
- Keep prompts compact: schema fields should be short and avoid redundancy so that LLM prompts remain efficient.

