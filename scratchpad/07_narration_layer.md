# Narration Layer & LLM Services Architecture

Update notes now describe how the current architecture will focus on the narration layer before the memory helper launches. The LLM layer splits into two async services: the Narration Service (the immediate focus) and the future Memory Enrichment Service. `CompletionsHelper` remains the shared gateway for invoking LLM calls, while `llm_factory_*` modules keep engine-specific imports isolated. Queueing and scheduling belong to the service orchestrators, and prompt construction now moves into a dedicated builder fed by the rich game memory snapshot.

## Narration Service (current priority)
1. Runs asynchronously after every completed turn (and optionally on player/idle triggers) via a `NarrationScheduler` that enqueues jobs without blocking the UI.
2. Uses a `NarrationJobBuilder` to assemble the submission object from the current `GameMemoryStore` snapshot (scene summaries, prior narrations, player state, heuristics) plus trigger metadata. The builder owns the narration prompts and returns `{messages, diagnostics}` ready for transport.
3. Does not expect schema-bound JSON output from the LLM. Instead, it can rely on natural-language narration with signed metadata (turn identifiers, optional confidence scores) produced by the completion itself or `ai_engine_parsing` heuristics.
4. Streams or appends narration to the UI once available; playback includes metadata so late results can be tagged appropriately, and the Narration Service always degrades to skipping when newer turns render older jobs stale.

## Memory Enrichment Service (future)
Documentation for the enrichment-focused flow now lives in `scratchpad/08_llm_memory_helper.md`. That note captures how structured output will enforce `llm_memory_helper_schema.json`, how enrichment jobs remain advisory, and how `ai_engine_parsing` adjusts to native JSON parsing.

## Prompt/Job Builder & CompletionsHelper
- `NarrationJobBuilder` (new) harvests everything needed from the memory engine. Inputs include the latest `GameMemoryStore.get_context_for_prompt()` result, trigger type (turn/idle/manual), player persona, and any queued hints. It applies configurable sliding windows (e.g., `narration_context_max_scenes`, `narration_recent_narrations`, `narration_recent_items`) so prompts remain short but information-rich. It produces:
	- `messages`: ordered chat messages constructed from narration-specific prompts stored in config (`llm_narration_*`).
	- `metadata`: references to the originating turn, scene, trigger, and optional dedupe tokens.
- The builder formats the context as natural prose sections (Current Scene, Previous Scenes, Last Narrations, Inventory Highlights, Pending Triggers) instead of JSON to improve readability for the local LLM while respecting the sliding-window limits.
- `CompletionsHelper` now acts purely as transport:
	- Accepts the prebuilt `messages` and sends them via the configured provider.
	- Parses SDK responses and delegates normalization to `module.ai_engine_parsing.normalize_ai_payload` (free-form narration) or future enrichment schemas.
	- Returns `{ payload, raw_response, diagnostics }` and logs the full prompt/response pair (when debug enabled) via `my_logging.log_completion_event`.

## llm_factory_* modules
- `llm_factory_FoundryLocal`: constructs the Foundry or OpenAI client based on `llm_provider`. The Narration Service consumes this client through `CompletionsHelper` so the rest of the stack doesn’t import Foundry/OpenAI directly.
- `llm_factory_otherai`: placeholder for future providers; keep it aligned so additional engines simply return compatible clients.

## Integration partners
1. **`module.game_engine_heuristics`**: still produces canonical `EngineFacts` used to update `GameMemoryStore`.
2. **`module.game_controller`**: writes transcripts, stores facts in memory, and enqueues narration jobs by handing the memory snapshot + trigger info to the job builder; it never crafts prompts directly.
3. **`module.game_memory`**: is now the authoritative source for narration context (scene summaries, player state, prior narrations). The builder pulls everything from here rather than stitching multiple sources, obeying the configurable window sizes when sampling scenes, actions, or narrations.
4. **`module.my_logging`**: receives `log_completion_event` inputs for every invocation, ensuring traceable telemetry even when Narration Service jobs are dropped or retried.

## Observability & policies
- Queues are bounded; older narration/enrichment jobs can be dropped when newer turns arrive (documented in the scheduler). Latency is captured for each job, and diagnostics include whether the payload came from structured output (future enrichment) or natural-language narration.
- The Narration Service may optionally request minimal metadata (intent, hidden command) using heuristics instead of JSON parsing, keeping the LLM’s creative output flexible while still providing structured hints when beneficial.

## Future Work / Notes
- Any additional AI heuristics or schema weighting should live in `module.ai_engine_parsing` so this helper remains focused on completions.
- Streaming, multi-step prompts, or command palette integrations can wrap this helper but should continue receiving the normalized `{ payload, raw_response, diagnostics }` shape for consistency.
