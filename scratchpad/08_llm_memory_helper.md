# LLM Memory Helper Architecture

This placeholder documents the future Memory Enrichment Service that runs separately from the Narration layer. Its goal is to add advisory metadata to scenes and player state without ever blocking the main game loop or overriding the canonical heuristics that come directly from `GameEngineHeuristics`.

## High-Level Responsibilities
1. **Trigger after each deduplicated engine turn**: once `GameMemoryStore.update_from_engine_facts` finishes, enqueue a bounded enrichment job tied to that turn number. Jobs should be cancelable/droppable when newer turns arrive before completion.
2. **Use OpenAI structured output**: send prompts that reference `llm_memory_helper_schema.json` and rely on the native structured output API rather than manual JSON parsing. The schema will describe inferred entities, relationships, confidence scores, and optional annotations that augment `Scene` objects.
3. **Normalize with `ai_engine_parsing`**: adapt `normalize_ai_payload` (and any new helpers) to understand structured output responses so that the enrichment payload can be mapped to scene enrichment fields reliably.
4. **Annotate scenes advisory**: enrichment outputs should not mutate canonical fields without explicit reconciliation. Instead, store them in dedicated enrichment slots (tags, inferred motives, probabilities) keyed by turn so consumers can decide whether to display or log them.
5. **Observability**: log completion diagnostics, track latency, and annotate whether the enrichment job was dropped, skipped, or completed late. Provide telemetry for queue depth/backpressure as part of the scheduler’s responsibilities.

## Integration Notes
- **CompletionsHelper**: acts as the shared normalization and logging gateway; it continues to build prompts (system prompt + user prompt) but now passes enriched schema context when called by the Memory Enrichment Service. Since structured output is used, the helper must ensure the schema string is current and the request includes the right response format directives.
- **llm_factory_FoundryLocal / llm_factory_otherai**: produce clients that support structured output. The Memory Enrichment Service requests the appropriate client via the factory so that the rest of the codebase remains agnostic to provider-specific APIs.
- **GameController**: enqueues the enrichment job after recording the turn. It writes the resulting job metadata to logs but never waits for the LLM call before accepting the next player command.
- **GameMemoryStore**: exposes optional `append_enrichment(scene_name, data)` or similar helpers so the service can persist enrichment annotations without touching the core heuristics.
- **MyLogging**: receives completion diagnostics (latency, tokens, outcome) for every enrichment invocation, even when the job is dropped due to backpressure.

## Future Tasks
- Define the full `llm_memory_helper_schema.json` with the planned enrichment fields (entities, relationships, confidence, hints).
- Implement the scheduler that enqueues enrichment jobs, enforces queue limits, handles cancellations, and emits events when enrichment results arrive.
- Wire the enrichment outputs into prompts (context builder) in a way that they remain advisory: heuristics remain the truth, enrichments provide complementary insight.
