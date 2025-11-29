# Minimal Completions Helper — Notes Only

Single helper that hides the Python `openai` SDK vs `foundry_local_sdk` differences and feeds the loop a "structured narration" object per turn.

## Responsibilities
1. Accept the *latest transcript chunk* plus any caller-provided crumbs (e.g., player command, simple config flags).
2. Inject the static system prompt + schema (loaded from `response_schema.json`).
3. Call the configured backend (`openai` chat completion or Foundry local runner) with streaming turned **off** for now.
4. Return a dict with the parsed JSON payload (`narration`, `suggested_actions`, etc.) and diagnostics (latency, token counts, model name).

## Minimal Interface Sketch
- Constructor locks in the config, schema, and injected client instance.
- `run(transcript_chunk)` builds the two-message prompt (system + latest transcript) and immediately routes to the proper backend path:
  - When `config.provider` is `openai`, call `chat.completions.create` with `response_format=self.schema` and the configured temperature.
  - When `config.provider` is `foundry`, call the Foundry local `chat` entrypoint with the same messages and schema reference.
- The helper always parses the JSON payload, returning a dict containing the structured narration and the raw SDK response.

## Notes
- Inject `llm_client` (`openai.OpenAI()` or Foundry local client) so tests can stub it out.
- Use OpenAI's `response_format` and Foundry's `schema` argument for strict JSON.
- Keep inputs minimal for now: latest transcript chunk only, no streaming or extra memory.
- Main loop logs both `payload` and `raw` with the parser transcript for traceability.
