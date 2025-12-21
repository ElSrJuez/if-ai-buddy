# Completions Helper — Current LLM Completion Stack

This note captures everything implemented around LLM completion handling. The helper itself stays focused on prompt orchestration, parsing, diagnostics, and handoff, while normalization, heuristics, metadata capture, and engine wiring live in dedicated modules so the stack remains composable and testable.

## Responsibilities
1. Accept the latest transcript chunk (plus any supplemental context forthcoming from the memory stack) and render the two-message bundle composed of `system_prompt` (with embedded schema JSON) and `user_prompt_template` (config-driven; context is prepended when available).
2. Instantiate the LLM client internally via `module.llm_factory_FoundryLocal.create_llm_client(config)` so this helper remains the single point that touches engine imports while the rest of the stack stays agnostic.
3. Parse the returned SDK object (OpenAI chat completion, Foundry dict, or fallback text), normalize the structured payload with `module.ai_engine_parsing.normalize_ai_payload`, and return a `{ payload, raw_response, diagnostics }` dict with latency/tokens/model.
4. Emit completion diagnostics through `my_logging.log_completion_event`, covering both success and error cases so observability remains consistent.
5. Provide identical normalization for fallback payloads, keeping downstream consumers agnostic to whether the completion succeeded, failed, or returned syntactically odd text.

## Completion Flow Highlights
- **Prompt building**: `_build_system_prompt` replaces `{response_schema}` with the JSON schema string so the LLM always receives a complete, schema-driven directive; `_build_user_prompt` injects the transcript and optional context JSON before sending the request.
- **Engine dispatch**: `_call_openai` and `_call_foundry` remain as the only engine-specific helpers, but neither module is imported at the top level except through the injected client, preserving separation of concerns.
- **Parsing & normalization**: `_parse_response` understands OpenAI message objects, Foundry dicts, and raw JSON in code fences; once it yields a dict, `normalize_ai_payload` enforces defaults, casts types, warns about missing required fields, and retains additional keys for future evolution.
- **Diagnostics**: tokens are extracted from `raw_response.usage` or dict usage fields, latency is measured via `time.time()`, and model alias is read from config before logging the completion event.
- **Fallback strategy**: exceptions capture the same diagnostics path, normalize a small default payload (narration, intents, hidden command), and continue returning a schema-compliant result.

## Supporting Modules & Integration
1. **`module.ai_engine_parsing.normalize_ai_payload`**: enforces schema defaults, casts string/integer/number/boolean types, warns when required fields are missing, and preserves unknown keys so the controller can extend the payload without touching the helper.
2. **`module.llm_factory_FoundryLocal`**: the only place in the repo that imports `foundry_local` or `openai`; it returns an OpenAI client when `llm_provider` is `openai` or `FoundryLocalManager` otherwise.
3. **`module.game_engine_heuristics`**: canonical parser for transcripts producing `EngineFacts` and metadata; this ensures prompts and context fed into `CompletionsHelper` come from one authoritative source rather than duplicated regex helpers.
4. **`module.game_api`**: builds `EngineTurn` objects from the heuristics output, logs parsed metadata with `my_logging.log_gameapi_event`, and exposes structured metadata (timestamp/status_code/pid) that makes it into the completions context without needing `raw_response`.
5. **`module.game_controller`**: consumes the parsed heuristics when initializing sessions or running turns, updates status fields (room/score/moves) from `EngineFacts`, and relies on `CompletionsHelper` solely for LLM completions.

## Future Work / Notes
- Any additional AI heuristics or schema weighting should live in `module.ai_engine_parsing` so this helper remains focused on completions.
- Streaming, multi-step prompts, or command palette integrations can wrap this helper but should continue receiving the normalized `{ payload, raw_response, diagnostics }` shape for consistency.
