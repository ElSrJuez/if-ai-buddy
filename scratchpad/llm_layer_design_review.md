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
- No mention of **memory enrichment** as a separate, synchronous task per turn.
- No mention of **async narration** running in parallel/background.
- Controller doesn't distinguish these two responsibilities.

**Impact:** Code will conflate schema enforcement (memory layer) with creative inference (narration), causing bottlenecks and confusion about blocking vs. non-blocking.

#### 2. **Async/Concurrency Model Undefined**
- README and 01_objectives mention "non-duplicit output" and "duplication filter" but don't explain how LLM calls happen asynchronously.
- GameController uses `asyncio` stubs but doesn't define the event loop structure or how narration runs in parallel.
- No scheduler for "idle" LLM triggers (e.g., "generate ambient commentary when the player is idle").

**Impact:** TUI will block waiting for narration, defeating the "non-blocking" goal. Idle scheduling logic won't exist.

#### 3. **Memory Enrichment vs. Narration Conflated**
- 01_objectives says "Episodic Memory" and "In-Game State Memory" but doesn't say which LLM service populates them.
- Current `CompletionsHelper.run()` is called once per turn with a generic `context` dict.
- No schema for "what memory enrichment should produce" vs. "what narration should produce."

**Impact:** Will attempt to produce both in one LLM call, forcing a bloated schema and slow iterations. Better to split: fast memory enrichment (schema-strict) + slower narration (creative, optional).

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

**Impact:** TUI will poll for narration unpredictably. No framework for background scheduler.

#### 6. **No Mention of Non-Blocking Constraints**
- GameController is designed as a sync TUI app with async helpers, but the LLM loop design doesn't account for "slow inference doesn't block gameplay."
- 01_objectives emphasizes "Streamed Delivery" and "keep the UI responsive" but doesn't explain how narration streams while the engine is ready for the next turn.

**Impact:** TUI and LLM orchestration will have race conditions or artificial waits.

---

## Design Issues in Current Docs

### 01_objectives_and_meta.md
**Issues:**
- No distinction between **memory enrichment LLM calls** (fast, schema-strict, per-turn) and **narration LLM calls** (slower, creative, async-optional).
- "Narration Layer" is described as a single feature, not as an independent async service.
- "Episodic Memory" and "In-Game State Memory" described but no mention of which is LLM-derived vs. heuristic-derived.
- "Streamed Delivery" assumes narration is always requested; no mention of optional narration or idle scheduling.

**Recommendations:**
- Explicitly separate "Memory Enrichment Service" and "Narration Service" with distinct objectives.
- Document that memory enrichment is **synchronous, per-turn, must complete before the next prompt**.
- Document that narration is **asynchronous, optional, triggered by engine/player events or idle schedule**.
- Add "LLM Call Latency Management" as a meta-objective (recognizing LLM is slow, design for non-blocking).

### README.md
**Issues:**
- Architecture section lists files but doesn't mention an LLM orchestration layer or scheduler.
- Says "AI narrator streaming in real time" but doesn't explain how streaming coexists with game turns.
- No mention of memory enrichment as distinct from narration.

**Recommendations:**
- Add diagram or flowchart showing: Engine → Memory Store → (Memory Enrichment LLM) → (Prompt Builder) → (Narration LLM, async) → UI.
- Clarify that narration is optional/non-blocking; the game loop does not wait for it.
- Document the scheduler/event-driven architecture briefly.

### 05_game_memory.md & memory_implementation.md
**Issues:**
- Describe what memory stores (good) but don't address "what does the Memory Enrichment LLM enrich?"
- No mention of LLM-derived fields or confidence scores.
- Assume all memory is heuristic-parsed; no framework for LLM to suggest corrections or add context.

**Recommendations:**
- Add section "Memory Enrichment by LLM" explaining what fields/facts are submitted to the memory-enrichment model and how responses are integrated.
- Document fallback: if memory enrichment fails/times out, proceed with heuristic memory only (non-blocking guarantee).

### game_controller.py
**Issues:**
- `CompletionsHelper` is called in an unclear place (no clear turn/narration workflow).
- No async scheduler for idle narration or background enrichment.
- No isolation between memory enrichment and narration calls.

**Recommendations:**
- Define a clear **TurnOrchestrator** or **LLMScheduler** that manages:
  - Synchronous memory-enrichment call (blocks, completes before next context).
  - Asynchronous narration call (fire-and-forget, UI streams it).
  - Idle scheduler (background commentary when player is idle).

---

## Proposed New Architecture (High-Level)

```
┌─────────────────────────────────────────────────────────────────┐
│ Game Loop (TUI / Textual Event Loop)                            │
└────────────────┬──────────────────────────────────────────────┘
                 │
         ┌───────▼────────┐
         │ Engine Turn    │
         └───────┬────────┘
                 │
         ┌───────▼─────────────────────────┐
         │ GameMemoryStore.record_turn()   │  (Heuristic-based)
         │ - Parse EngineTurn → Scene      │
         │ - Update inventory/items        │
         │ - Log JSONL audit trail         │
         └───────┬─────────────────────────┘
                 │
         ┌───────▼──────────────────────────────┐
         │ MemoryEnrichmentService.enrich()     │  (Sync, LLM #1)
         │ - Takes: Scene facts + recent history│
         │ - Returns: suggested NPC states,    │
         │   item purposes, theme tags         │
         │ - Blocks until done (timeout safety) │
         │ - Updates Scene with enrichments    │
         └───────┬──────────────────────────────┘
                 │
         ┌───────▼───────────────────────────┐
         │ NarrationScheduler.schedule()      │  (Async, LLM #2)
         │ - Enqueue narration task if:       │
         │   - New turn just completed        │
         │   - Player idle > N seconds        │
         │   - Narration queue not full       │
         └───────┬───────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
[Narration    [Idle        [Prompt
 Task]        Timer]       Builder]
    │            │            │
    └────┬───────┘────────────┘
         │
    ┌────▼──────────────────────────┐
    │ NarrationService.narrate()     │  (Async, LLM #2 call)
    │ - Takes: context              │
    │ - Returns: narration chunk     │
    │ - Streams to UI (non-blocking) │
    └────┬──────────────────────────┘
         │
    ┌────▼──────────────────────────┐
    │ TUI: Display narration         │
    └───────────────────────────────┘
```

---

## Specific Doc Updates Needed

### 1. **scratchpad/01_objectives_and_meta.md**
Add new section after "Core Objectives":

```markdown
### 1a. LLM Service Roles

**Memory Enrichment Service (Synchronous, Per-Turn)**
- Triggered: After every engine turn, once heuristic memory is recorded.
- Input: Scene facts, recent action history, known entities.
- Output: Enriched facts (NPC states, item purposes, location themes, unresolved threads).
- Constraint: Must complete within timeout (e.g., 5s) or abort gracefully; game does not wait.
- Schema: Strict JSON with recognized field names, confidence scores.

**Narration Service (Asynchronous, Event-Driven)**
- Triggered: When new turn available, player idle > N seconds, or on a background schedule.
- Input: Scene context, enriched facts, recent narrations (dedup).
- Output: Narrative commentary, optional hints, flavor text.
- Constraint: Non-blocking; runs in background while game accepts next command.
- Schema: Looser format (may include streaming markdown, unstructured flavor).
```

### 2. **scratchpad/05_game_memory.md**
Add section "LLM Enrichment":

```markdown
## LLM-Driven Enrichment (Future)

The Memory Enrichment Service augments Scene objects with:
- **npc_states**: Inferred emotional state, intentions, last-seen context for each NPC.
- **item_purposes**: Detected use cases (key, weapon, tool, decoration) for items in scene_items.
- **location_themes**: Inferred atmosphere/danger/puzzle markers for the room.
- **unresolved_threads**: Tasks/questions the player left behind.

These fields are optional and do not block the main game loop. If the LLM call times out or fails, gameplay continues with heuristic memory only.
```

### 3. **README.md**
Expand "Architecture & Configuration":

```markdown
## LLM Layer

Two LLM services run in parallel:

1. **Memory Enrichment** (sync, per-turn)
   - Enriches Scene facts with NPC states, item purposes, themes.
   - Blocks briefly; times out safely.
   - Updated facts improve narration quality.

2. **Narration** (async, event-driven)
   - Consumes enriched Scene + history.
   - Runs in background; UI streams output.
   - Triggered by: engine turns, player idle, background schedule.
   - Never blocks the game loop.
```

### 4. **scratchpad/player-state-scene-items-memory.md**
Add note about enrichment:

```markdown
### LLM Enrichment Interaction

When Memory Enrichment succeeds, it adds optional fields to Scene:
- `npc_inferences`: Map of NPC name → {mood, last_action, suspected_goal}.
- `item_inferences`: Map of item name → {likely_purpose, rarity, puzzle_hint}.

These are **advisory only**; heuristic memory remains the source of truth.
```

---

## Code Architecture Implications

### New Files / Modules Needed
1. **module/memory_enrichment_service.py** — Synchronous LLM calls to enrich Scene facts.
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

```python
class MemoryEnrichmentService:
    async def enrich_async(self, scene: Scene) -> Scene:
        """Attempt enrichment; abort gracefully on timeout."""
        try:
            result = await asyncio.wait_for(
                self._call_llm(scene),
                timeout=5.0
            )
            scene.enrichment = result
        except asyncio.TimeoutError:
            my_logging.system_warn("Memory enrichment timed out, proceeding with heuristic memory")
            scene.enrichment = None
        return scene
```

Game always waits for memory enrichment (guarantees state is fresh). But narration is queued:

```python
class NarrationScheduler:
    async def schedule_narration(self, scene: Scene, reason: str) -> None:
        """Queue narration task; never blocks game loop."""
        if len(self._queue) < self._max_queue_size:
            self._queue.append((scene, reason))
            asyncio.create_task(self._process_next())
        else:
            my_logging.debug("Narration queue full, skipping background narration")
```

---

## Summary of Alignment Gaps

| Document | Gap | Severity |
|---|---|---|
| 01_objectives_and_meta.md | No mention of two LLM services or async narration | **High** |
| README.md | Architecture section incomplete re: LLM orchestration | **High** |
| 05_game_memory.md | No framework for LLM enrichment fields | **Medium** |
| game_controller.py | No LLMScheduler or narration queue | **High** |
| completions_helper.py | Monolithic; should split enrichment ↔ narration | **High** |

---

## Recommended Next Steps

1. **Finalize LLM Schema**: Define strict JSON schemas for enrichment and narration separately.
2. **Design Idle Scheduler**: Specify rules for "player idle > N seconds → generate ambient narration."
3. **Implement MemoryEnrichmentService**: Sync LLM calls with timeout safety.
4. **Implement NarrationScheduler + NarrationService**: Async queue and background streaming.
5. **Update GameController**: Wire turn events → enrichment → narration queue.
6. **Update all design docs** with the recommendations above.

