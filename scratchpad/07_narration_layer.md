# Narration Layer & LLM Services Architecture

Update notes now describe how the current architecture will focus on the narration layer before the memory helper launches. The LLM layer splits into two async services: the Narration Service (the immediate focus) and the future Memory Enrichment Service. `CompletionsHelper` remains the shared gateway for invoking LLM calls, while `llm_factory_*` modules keep engine-specific imports isolated. The helper is responsible for prompt orchestration, normalization, and diagnostics, but queueing and scheduling belong to the service orchestrators.

## Narration Service (current priority)
1. Runs asynchronously after every completed turn (and optionally on player/idle triggers) via a `NarrationScheduler` that enqueues jobs without blocking the UI.
2. Builds prompts by combining the system prompt (with schema, tone, and config-driven directives) and the user prompt (with the latest transcript and optional enrichment context) through `CompletionsHelper`.
3. Does not expect schema-bound JSON output from the LLM. Instead, it can rely on natural-language narration with signed metadata (turn identifiers, optional confidence scores) produced by the completion itself or `ai_engine_parsing` heuristics.
4. Streams or appends narration to the UI once available; playback includes metadata so late results can be tagged appropriately, and the Narration Service always degrades to skipping when newer turns render older jobs stale.

## Memory Enrichment Service (future)
Documentation for the enrichment-focused flow now lives in `scratchpad/08_llm_memory_helper.md`. That note captures how structured output will enforce `llm_memory_helper_schema.json`, how enrichment jobs remain advisory, and how `ai_engine_parsing` adjusts to native JSON parsing.

## CompletionsHelper (shared gateway)
- Accepts either the narration or enrichment schema (when the latter is implemented) and builds the prompt bundle accordingly: system prompt (schema placeholder, policy guards) + user prompt (transcript/scene context). It uses injected LLM clients from the factory helpers to send requests.
- Parses SDK responses (OpenAI chat, Foundry dict, or structured output) and delegates normalization to `module.ai_engine_parsing.normalize_ai_payload`, which now must know whether the caller expects schemaed JSON (enrichment) or free-form narration output.
- Returns `{ payload, raw_response, diagnostics }`: payload is normalized to the appropriate schema or natural-language format; diagnostics include latency, tokens, and model alias for `my_logging.log_completion_event`. Fallbacks still produce minimal narration/intents so downstream services can keep streaming even when LLM errors occur.

## llm_factory_* modules
- `llm_factory_FoundryLocal`: constructs the Foundry or OpenAI client based on `llm_provider`. The Narration Service consumes this client through `CompletionsHelper` so the rest of the stack doesn’t import Foundry/OpenAI directly.
- `llm_factory_otherai`: placeholder for future providers; keep it aligned so additional engines simply return compatible clients.

## Integration partners
1. **`module.game_engine_heuristics`**: still produces canonical `EngineFacts` used both for immediate state updates and for narration context (turn metadata, verbs, results).
2. **`module.game_controller`**: writes transcripts, stores facts in `GameMemoryStore`, updates UI status, and enqueues narration jobs; it never waits on the LLM call.
3. **`module.game_memory`**: records scenes and actions immediately; narrations appended by the Narration Service are purely supplemental and logged with their origin turn.
4. **`module.my_logging`**: receives `log_completion_event` inputs for every invocation, ensuring traceable telemetry even when Narration Service jobs are dropped or retried.

## Observability & policies
- Queues are bounded; older narration/enrichment jobs can be dropped when newer turns arrive (documented in the scheduler). Latency is captured for each job, and diagnostics include whether the payload came from structured output (future enrichment) or natural-language narration.
- The Narration Service may optionally request minimal metadata (intent, hidden command) using heuristics instead of JSON parsing, keeping the LLM’s creative output flexible while still providing structured hints when beneficial.

## Future Work / Notes
- Any additional AI heuristics or schema weighting should live in `module.ai_engine_parsing` so this helper remains focused on completions.
- Streaming, multi-step prompts, or command palette integrations can wrap this helper but should continue receiving the normalized `{ payload, raw_response, diagnostics }` shape for consistency.
