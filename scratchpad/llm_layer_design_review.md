# LLM Layer Design Review & Alignment Issues

## Executive Summary

Current docs and code assume **synchronous, single-purpose LLM calls** for narration only. The new direction requires:
1. **Two distinct LLM services** (Memory Enrichment + Async Narration)
2. **Non-blocking async orchestration** so the game doesn't stall on LLM latency
3. **Event-driven triggers** (engine turn, player command, idle schedule) instead of one-per-turn
4. **Decoupled concerns:** schema-driven game state vs. LLM inference layer

This creates significant architectural gaps between current docs and desired behavior.

---

## Current State Assessment

### What's Working
- ✅ **Game memory layer** is solid: GameMemoryStore captures EngineTurn facts into Scene objects with ActionRecords, description aggregation, inventory tracking.
- ✅ **Schema-driven heuristics** respect `game_engine_schema.json` and avoid re-parsing in multiple places.
- ✅ **JSONL audit trail** logs every state transition deterministically.
- ✅ **CompletionsHelper skeleton** exists and hooks into OpenAI/Foundry clients.

### What's Missing / Misaligned

#### 1. **Dual LLM Service Architecture Not Documented**
- Current docs (01_objectives_and_meta.md) treat "LLM" as a monolithic narrator.
- No mention of **memory enrichment** as a separate, **asynchronous** worker triggered on each completed engine turn.
- No mention of **async narration** running in parallel/background.
- Controller doesn't distinguish these two responsibilities.

**Impact:** Without explicit separation, the codebase will keep drifting toward a single “do everything” LLM call, which increases latency pressure and blurs which outputs are authoritative vs. advisory.

#### 2. **Async/Concurrency Model Undefined**
- README and 01_objectives mention "non-duplicit output" and "duplication filter" but don't explain how LLM calls happen asynchronously.
- GameController uses `asyncio` stubs but doesn't define the event loop structure or how narration runs in parallel.
- No scheduler for "idle" LLM triggers (e.g., "generate ambient commentary when the player is idle").

**Impact:** The project risks reintroducing “LLM blocks gameplay” behavior (or race-y UI updates) because there is no documented contract for queues, backpressure, cancellation, or how/when results are surfaced.

#### 3. **Memory Enrichment vs. Narration Conflated**
  - 01_objectives says "Episodic Memory" and "In-Game State Memory" but treats them as synchronous outputs of the same LLM call.
  - Memory enrichment must be async (like narration) but triggered immediately after heuristics complete; it must never block transcript display or prompt delivery.
  - `CompletionsHelper.run()` currently assumes a single schema; we must split into separate enrichment and narration pipelines, even though both run asynchronously with different triggers.

**Impact:** A single schema/call encourages bloated prompts and ambiguous outputs. We want two pipelines whose outputs have different lifecycles: enrichment is advisory state augmentation; narration is optional UI output.

#### 4. **Response Schema Confusion**
- `config/response_schema.json` is used for narration output (game_intent, narration, hints).
- But memory enrichment needs a different schema (recognized entities, state changes, confidence scores).
- No separation in code or docs.

**Impact:** One schema trying to serve two masters; both will be poorly constrained.

#### 5. **Event-Driven Trigger Model Missing**
- No clear definition of "when does an LLM call happen?"
- 01_objectives vaguely says "Collect base game output and player commands" but doesn't specify:
  - Does each EngineTurn immediately trigger narration?
  - Or is narration queued/batched?
  - What are the idle trigger rules?

**Impact:** Without explicit triggers and scheduling rules, the system cannot guarantee a responsive UI while also producing timely narration/enrichment. It also becomes impossible to reason about cost/throughput.

#### 6. **No Mention of Non-Blocking Constraints**
- GameController is designed as a sync TUI app with async helpers, but the LLM loop design doesn't account for "slow inference doesn't block gameplay."
- 01_objectives emphasizes "Streamed Delivery" and "keep the UI responsive" but doesn't explain how narration streams while the engine is ready for the next turn.

**Impact:** The implementation will either (a) block the player while waiting on LLM calls or (b) produce inconsistent output ordering because there is no stated ordering/consistency policy.

---

## Design Issues in Current Docs

### 01_objectives_and_meta.md
**Issues:**
- No distinction between **memory enrichment LLM calls** (advisory, async-per-turn trigger) and **narration LLM calls** (creative, async, event/idle-triggered).
- "Narration Layer" is described as a single feature, not as an independent async service.
- "Episodic Memory" and "In-Game State Memory" described but no mention of which is LLM-derived vs. heuristic-derived.
- "Streamed Delivery" assumes narration is always requested; no mention of optional narration or idle scheduling.

**Recommendations:**
- Explicitly separate "Memory Enrichment Service" and "Narration Service" with distinct objectives.
- Document that memory enrichment is **asynchronous and non-blocking**: it starts after heuristics record the turn, but it must not delay transcript rendering or the next command prompt.
- Document that narration is **asynchronous and optional**, triggered by engine/player/idle events; gameplay must never wait for it.
- Add "LLM Call Latency Management" as a meta-objective (recognizing LLM is slow, design for non-blocking).
- Add a short “Consistency Policy” note: heuristic memory is authoritative; LLM enrichments are advisory and may arrive late, be skipped, or be superseded.

### README.md
**Issues:**
- Architecture section lists files but doesn't mention an LLM orchestration layer or scheduler.
- Says "AI narrator streaming in real time" but doesn't explain how streaming coexists with game turns.
- No mention of memory enrichment as distinct from narration.

**Recommendations:**
- Describe the event flow in text (avoid code): engine turn → heuristics memory update → enqueue enrichment job + enqueue narration job → UI streams outputs when ready.
- Clarify that narration is optional/non-blocking; the game loop does not wait for it.
- Document the scheduler/event-driven architecture briefly.
- Document the three triggers explicitly: engine-turn trigger, player-command trigger, idle trigger.

### 05_game_memory.md & memory_implementation.md
**Issues:**
- Describe what memory stores (good) but don't address "what does the Memory Enrichment LLM enrich?"
- No mention of LLM-derived fields or confidence scores.
- Assume all memory is heuristic-parsed; no framework for LLM to suggest corrections or add context.

**Recommendations:**
- Add section "Memory Enrichment by LLM" explaining (a) what is submitted, (b) what comes back, (c) that the result is advisory and may arrive late.
- Document that if enrichment fails or is skipped, gameplay proceeds with heuristic memory only (this is the normal, supported path).

### game_controller.py
**Issues:**
- `CompletionsHelper` is called in an unclear place (no clear turn/narration workflow).
- No async scheduler for idle narration or background enrichment.
- No isolation between memory enrichment and narration calls.

**Recommendations:**
- Define a clear **TurnOrchestrator** or **LLMScheduler** that manages:
  - Enqueue memory-enrichment work after heuristics complete (non-blocking).
  - Enqueue narration work after engine/player events and on idle (non-blocking).
  - Backpressure rules (max queue depth, drop/skip policy, cancellation on new turns).

---

## Proposed New Architecture (High-Level)

Event flow (conceptual, no code):

1. Engine responds → UI immediately renders transcript.
2. Heuristics parse + `GameMemoryStore` records the turn (authoritative state).
3. Two background jobs are *enqueued* (non-blocking):
   - **Memory enrichment** job (trigger: “turn recorded”).
   - **Narration** job (trigger: “turn recorded”, plus optional player/idle triggers).
4. When each job completes, it emits an event to the UI/log:
   - Memory enrichment updates advisory fields on the current scene (never overwriting authoritative facts without explicit policy).
   - Narration streams or appends output to the UI.

Key invariants:
- Gameplay never waits on any LLM job.
- All LLM outputs are tagged with the turn they refer to; late results may be ignored or appended with that context.
- Queue/backpressure is explicit (bounded queues, drop/skip rules).

---

## Specific Doc Updates Needed

### 1. **scratchpad/01_objectives_and_meta.md**
Add a short “LLM Service Roles” section:

- **Memory Enrichment Service (async, turn-triggered)**: starts immediately after heuristics record the turn; never blocks transcript rendering or next-command prompt; writes advisory enrichments keyed to a specific turn.
- **Narration Service (async, event/idle-triggered)**: runs independently and streams/adds narration; may be skipped or delayed; must not block gameplay.

### 2. **scratchpad/05_game_memory.md**
Add a short “LLM-Driven Enrichment (Future)” section explaining which *advisory* fields may be added to Scene, and that enrichment is opportunistic and may arrive late.

### 3. **README.md**
Expand “Architecture” with a brief “LLM Layer” subsection describing the two async workers and their triggers, emphasizing that neither blocks gameplay.

### 4. **scratchpad/player-state-scene-items-memory.md**
Add a note describing enrichment as advisory, keyed to a turn, and potentially stale if it arrives after additional turns.

---

## Code Architecture Implications

### New Files / Modules Needed
1. **module/memory_enrichment_service.py** — Async LLM calls to enrich Scene facts (turn-triggered).
2. **module/narration_scheduler.py** — Event-driven queue and idle timer for narration tasks.
3. **module/narration_service.py** — Async LLM calls for narration generation and streaming.
4. **module/llm_scheduler.py** (or extend game_controller) — Central orchestrator that manages both services.

### Modified Files
- **module/game_controller.py** — Add LLMScheduler, wire up turn events → enrichment → narration queue.
- **module/game_memory.py** — Add optional enrichment fields to Scene; expose enrichment method.
- **module/completions_helper.py** — Refactor into:
  - `MemoryEnrichmentCompletion` (schema: {npc_inferences, item_inferences, themes, threads})
  - `NarrationCompletion` (schema: {narration, hints, flavor})
- **config/response_schema.json** — Split into:
  - `config/response_schema_enrichment.json`
  - `config/response_schema_narration.json`

---

## Non-Blocking Guarantee Mechanism

Documented policy (no code):

- The UI renders engine output immediately.
- Memory recording (heuristics + persistence) happens before any LLM work and remains authoritative.
- Memory enrichment and narration are queued background jobs.
- Both jobs are bounded by explicit backpressure rules (skip, drop, or cancel) and are keyed to a specific turn so late results can be safely ignored or displayed with the correct context.

---

## Summary of Alignment Gaps

| Document | Gap | Severity |
|---|---|---|
| 01_objectives_and_meta.md | No mention of two async LLM workers (enrichment + narration) and their triggers | **High** |
| README.md | Architecture section incomplete re: event triggers, queues, and non-blocking guarantees | **High** |
| 05_game_memory.md | Missing definition of advisory enrichment outputs and integration policy | **Medium** |
| game_controller.py | No LLMScheduler (enqueueing, backpressure, idle trigger) | **High** |
| completions_helper.py | Monolithic; must split enrichment ↔ narration schemas and execution paths | **High** |

---

## Recommended Next Steps

1. **Finalize LLM Schema**: Define strict JSON schemas for enrichment and narration separately.
2. **Design Idle Scheduler**: Specify rules for "player idle > N seconds → generate ambient narration."
3. **Implement MemoryEnrichmentService (async)**: Enqueue enrichment on “turn recorded”; ensure bounded queue, cancellation/skip rules, and per-turn correlation.
4. **Implement NarrationScheduler + NarrationService (async)**: Enqueue on turn/player/idle triggers; ensure bounded queue, streaming-to-UI, and duplication controls.
5. **Update GameController**: Wire engine-turn events to immediate UI display + heuristic memory recording, then enqueue both LLM jobs without blocking input.
6. **Update all design docs** with the recommendations above.

