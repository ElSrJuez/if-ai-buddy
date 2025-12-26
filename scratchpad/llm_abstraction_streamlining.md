# LLM Abstraction Streamlining (pre-`otheropenai`)

## Purpose
We want to add `otheropenai` without multiplying provider-specific branching and copy/paste logic.

Constraints / values we must respect:
- **Config-driven, fail-fast**: no in-code defaults that hide missing config.
- **One place to decide provider**: avoid scattered `if provider == ...` across the codebase.
- **Streaming is primary**: preserve the existing streaming flow + the existing logging/trace approach.
- **Minimize duplicity**: new providers should be “plug in an adapter”, not “copy the whole orchestration layer”.

---

## Current gaps (pain points)

### 1) Provider branching is duplicated across layers
Provider selection currently leaks into multiple modules:
- `module/llm_factory_FoundryLocal.py` (factory)
- `module/llm_narration_helper.py` (async streaming orchestration)
- `module/llm_narration_helper.py` (sync fallback orchestration)
- `testing/llm_smoke_test.py` (smoke test orchestration)

**Why it’s bad:** every new provider forces edits in several places, increasing drift risk.

**Target state:** provider selection happens **once** (in the factory), and the rest of the stack is provider-agnostic.

---

### 2) No explicit internal client interface
Foundry path uses `FoundryChatAdapter.stream_chat/chat`.
OpenAI path uses a different surface (`client.responses.stream`, plus chat completions in sync).

**Why it’s bad:** the orchestration code must know provider-specific SDK shapes.

**Target state:** the app uses one internal interface everywhere.

Proposed internal interface (minimal):
- `stream_chat(model, messages, temperature, max_tokens, *, extra=None) -> Iterable[Any]`
- `chat(model, messages, temperature, max_tokens, *, schema=None, extra=None) -> Any`

Notes:
- `Iterable[Any]` is intentional: the *event shape* can vary, but must be compatible with `common_llm_layer.extract_stream_text`.
- `schema` remains optional and should be applied only where supported.

---

### 3) Config resolution is partly centralized but still “pulled” in multiple places
We now have provider-scoped keys (e.g., `llm_model_alias_foundry`), but values are fetched in several modules.

**Why it’s bad:** duplicated key logic makes it easier to accidentally reintroduce defaults or partial configs.

**Target state:** one canonical config resolver that returns a strict, validated settings object.

---

### 4) Test code reimplements production streaming logic
`testing/llm_smoke_test.py` contains its own provider branching and streaming logic.

**Why it’s bad:** tests can pass while production breaks (and vice versa).

**Target state:** smoke tests reuse the production abstraction (adapter + stream extraction).

---

## Detailed improvement plan

### Phase 0 — Document invariants (before refactor)
**Deliverable:** a small set of explicit invariants to keep refactors honest.

Invariants:
1. Streaming is the primary path.
2. Prompt messages are logged verbatim in the simple interaction history.
3. Missing provider-scoped config should raise clear errors (no silent defaults).
4. `common_llm_layer.extract_stream_text` remains the canonical text extraction.

---

### Phase 1 — Centralize provider-scoped settings resolution (no new modules)
**Goal:** stop scattering config-key lookups.

Implementation detail:
- Add to `module/config_registry.py`:
  - `resolve_llm_settings(config) -> dict` (or a small dataclass if desired)

Example return shape:
```python
{
  "provider": "foundry",
  "alias": "Phi-4-mini-instruct-cuda-gpu",
  "temperature": 0.4,
  "max_tokens": 1000,
  # optional fields for otheropenai later:
  "endpoint": None,
  "api_key": None,
}
```

Rules:
- The resolver must be **strict** and must not assign defaults.
- It should validate types (e.g., `float(temperature)` should fail loudly if invalid).

Outcome:
- `llm_narration_helper` and factories consume only the resolver output.

---

## Addendum: Canonical prompt inputs (must land before `otheropenai`)

Provider abstraction is only half the problem. The narration failures (repetition, invention) are primarily driven by **prompt construction**.

### Required prompt/data work
1. Add `turn_hints` to the memory snapshot (TurnHints: command, deltas, bounded evidence excerpt).
2. Make the prompt builder consume only `NarrationArtifacts` from `GameMemoryStore.get_context_for_prompt()`.
3. Remove repetition amplifiers:
  - Do not label append-only `scene_items` as “Visible now”. Use `current_items`.
  - Stop feeding full room descriptions back as action results.
  - Replace ad-hoc transcript-delta parsing with memory-owned TurnHints.

### Why this is a prerequisite
Without this, adding `otheropenai` will only change latency/model quirks while the core problem (ambiguous, repetitive, weakly-grounded prompts) persists.

---

### Phase 2 — Introduce a single internal LLM adapter interface
**Goal:** `CompletionsHelper` should not branch by provider.

Approach:
- Define the internal interface by convention (duck typing) to avoid overengineering:
  - `stream_chat(...)`
  - `chat(...)`

Adapters:
1. `FoundryChatAdapter` already matches this.
2. Add `OpenAIChatAdapter` that wraps `openai.OpenAI` and exposes the same methods.
   - Streaming method should yield events compatible with `common_llm_layer.extract_stream_text`.

Where to place:
- Keep adapters in the existing factory module(s) to avoid proliferating modules.

---

### Phase 3 — Make the factory return only adapters
**Goal:** callers never see raw SDK clients.

Changes:
- `create_llm_client(config)` should return an object implementing the adapter interface.
- The provider decision happens exactly once here.

Result:
- `llm_narration_helper` can always call `self.llm_client.stream_chat(...)`.

---

### Phase 4 — Collapse orchestration logic in `llm_narration_helper`
**Goal:** remove provider-specific logic from orchestration.

Changes:
- Replace:
  - `_stream_openai` and `_stream_foundry` split
- With:
  - one `_stream_chat` that calls `self.llm_client.stream_chat(...)`
  - one `_call_chat` that calls `self.llm_client.chat(...)`

Logging stays:
- `common_llm_layer.stream_text_from_iterable` remains unchanged.
- `log_stream_finished` continues to record full-fidelity traces.

---

### Phase 5 — Update smoke tests to reuse the production interface
**Goal:** tests validate the production path.

Changes:
- `testing/llm_smoke_test.py` should:
  - load config
  - call `create_llm_client(config)`
  - call `adapter.stream_chat(...)`
  - use `common_llm_layer.stream_text_from_iterable` to print/validate

No provider branching in tests.

---

## How this enables `otheropenai` with minimal duplication
With the above in place, implementing `otheropenai` becomes:
1. Add provider-scoped config fields to `resolve_llm_settings` validation.
2. Add a new adapter (or reuse `OpenAIChatAdapter` with a configurable base_url/api_key).
3. Add a new branch in the factory that returns that adapter.

No changes required in `llm_narration_helper` or the test harness.

---

## Risk / mitigation notes
- **Risk:** some providers emit different stream event shapes.
  - **Mitigation:** adjust adapters to emit shapes `extract_stream_text` already supports.
- **Risk:** overfitting to OpenAI Responses API.
  - **Mitigation:** keep adapter surface generic (`stream_chat`) and isolate SDK choices in adapters.

---

## Definition of done
- Only the factory knows the provider string.
- Only `config_registry` knows provider-scoped config key names.
- `CompletionsHelper` has a single streaming path.
- Smoke tests call the same adapter path.
- No defaults for provider-scoped settings; missing config fails explicitly.
