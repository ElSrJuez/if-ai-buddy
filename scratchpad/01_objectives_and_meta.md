# IF AI Buddy — Objectives and Meta-Objectives

A concise, generalized blueprint for the project’s direction. Emphasis on durable features and meta-features that enable meaningful episodic/stateful memory and a non-duplicative, playful, and useful AI narrator layered over base game output.

---

## 1. Core Objectives (Features)

- **Narration Layer:** Provide an AI narrator that transforms raw game output into coherent, engaging commentary that feels timely and context-aware.
- **Episodic Memory (within-run):** Maintain short-term memory of the last N interactions in the current game run (turns, events, discoveries) to inform immediate narration and guidance.
- **In-Game State Memory:** Extract and maintain the current world state from game output (rooms, room items and their state, scene/area changes, taken items, NPCs, player inventory, tasks/objectives), reflecting what has happened so far and how we arrived at the present state.
- **Beyond-immediate (within-run history):** Track the player across the entire current run’s history with non-spoilery, playful hints of what may be coming; identify and track intentions, changes, movements, transitions, actions and interactions (achievements, unresolved threads). This does not persist across separate sessions; it is scoped to the ongoing run.
- **Non-duplicit Output:** Reduce repetition and contradictions; prefer additive, clarifying narration over restating game output and previous/duplicit inference.
- **Actionable Hints:** Offer context-sensitive nudges (e.g., next logical actions, overlooked objects) without railroading the player.
- **Schema-Guided Responses:** Use a response schema to consistently structure model output (e.g., narration, salient objects, suggested actions), enabling reliable parsing and downstream features.
- **Streamed Delivery:** Stream narration in readable chunks to keep the UI responsive and support incremental rendering and optional TTS.
- **Auditability:** Log requests/responses and key decisions to support debugging, evaluation, and iterative improvement.

---

## 2. Meta-Objectives (Meta-Features)

- **Model Coercion Discipline:** Apply robust prompt strategies and response-format constraints so LLMs produce structured, useful outputs under varied inputs.
- **Memory Hygiene (within-run):** Curate what goes into episodic vs in-game state memory; avoid noise, duplication, and volatile facts incorrectly entering the run’s state representation.
- **Conflict Resolution:** Detect and reconcile inconsistencies between base game output, episodic memory, and in-game state memory before surfacing narration.
- **Narrative Tone Control:** Maintain a consistent voice and persona while adapting tone to context (discovery, failure, puzzle-solving) for engagement.
- **Context Windows Efficiency:** Slice history intelligently; prioritize salient events; compress or summarize to fit within model limits without losing meaning.
- **Safety Rails:** Guard against unsafe or misleading suggestions; prefer factual alignment with the base game output.
- **Observability-first Design:** Instrumentation and diagnostics are first-class to enable quick iteration on prompt, schema, and memory policies.

---

## 3. Functionality Map (Generalized)

- **Input Pipeline:**
  - Collect base game output and player commands into an interaction log.
  - Normalize and deduplicate lines; tag sources and timestamps for better downstream filtering.

- **Context Builder:**
  - Construct a prompt from recent history (episodic, within-run) plus the current in-game state (rooms, inventory, NPCs, objectives, recent changes).
  - Inject a response schema and guardrails to enforce structure and reduce hallucination.

- **Model Orchestration:**
  - Call a chat-completions API with schema-enforced output.
  - Parse with resilience (strip code fences, tolerate small deviations, fallback extraction for narration).

- **Narration Synthesis:**
  - Convert model payload into readable narration; trim redundancy; align with current world state.
  - Optionally include “what changed” highlights (new objects, unlocked areas, active quests).

- **Hinting & Guidance:**
  - Generate small, non-spoilery nudges based on incomplete objectives, overlooked affordances, and recent failures.

- **Streaming & UI:**
  - Stream narration chunks to the UI; keep gameplay loop responsive.
  - Optional TTS for narration-only payloads.

- **Persistence & Audit:**
  - Log structured request/response pairs and derived memory updates for the current run.
  - Maintain per-run state representations with clear policies for promotion/demotion within the run; separate sessions start fresh unless explicitly restored by the game.

---

## 4. Memory Design Principles

- **Separation of Concerns:** Episodic (short-term, volatile, within-run) vs in-game state (current world, stable within the run) are distinct stores with explicit promotion rules.
- **Promotion Criteria:** Within the run, promote facts that are stable, recurring, or identity-defining for the current world; avoid transient states.
- **Duplication Avoidance:** Prefer references to canonical facts over copying; detect overlaps before adding.
- **Freshness & Decay:** Episodic items age out; in-game state facts are revalidated on new evidence or decayed/overwritten if contradicted by subsequent game output.
- **Alignment with Ground Truth:** Memory must be anchored to base game output; conflicting facts trigger reconciliation or suppression within the current run.

---

## 10. LLM Service Roles & Async Guarantees

- **Memory Enrichment Service (async, turn-triggered):** Runs immediately after heuristics record an engine turn, enriches the authoritative scene/state with inference cues (entities, inferred relationships, confidence signals) marked as advisory. It never blocks transcript rendering, prompt building for the next turn, or any UI response.
- **Narration Service (async, event/idle-triggered):** Enqueues creative commentary jobs keyed to engine turns, player commands, or idle timers. Each job streams or appends narration when ready; the game loop continues regardless of whether the job completes.
- **LLM Call Latency Management:** Treat every LLM job as a background worker subject to bounded queues, drop/skip policies, and explicit cancellation when newer turns supersede pending work. Document that UI responsiveness is maintained by never waiting synchronously for enrichment or narration.
- **Consistency Policy:** Heuristic memory remains authoritative. LLM enrichments are advisory, tagged with their originating turn, and may arrive after subsequent turns. If an enrichment is late, it should either be ignored or displayed with a clear “late advisory” flag instead of overwriting canonical facts.

---

## 5. Narrative Quality Heuristics

- **Additive, not Redundant:** Narration should build on the game output—clarify, contextualize, and motivate—never echo verbatim unless for emphasis.
- **Player-centric:** Use the player’s perspective and goals; reference past actions and preferences for continuity.
- **Varied Cadence:** Balance short quips with occasional deeper commentary; avoid monotony.
- **Error Tolerance:** If model output is incomplete, prefer a graceful, minimal narration rather than fabricating details.
- **Consistency:** Maintain persona and style across turns and sessions.

---

## 6. What We Intentionally Generalize (and Why)

- **Implementation Names:** Replace concrete class/module names with role-based terms (UI, InteractionLog, CompletionService) to avoid binding to old architectures.
- **Vendor Details:** Refer to “LLM client” rather than specific providers; keep the contract (schema, streaming) front and center.
- **File-level Specifics:** Treat schemas and configs as concepts, not fixed filenames; focus on the guarantees they provide.
- **Exact Prompt Wording:** Capture prompt patterns (system + user, alternation emphasis, constraints) without freezing exact text.

Rationale: This avoids old vices like brittle dependencies on prior code, while retaining the essential design invariants (schema enforcement, memory separation, narrative heuristics, observability).

---

## 7. Minimal Policies (Starter Set)

- **Schema Compliance:** Reject or repair outputs that fail structural checks; log and downgrade narration quality when repairs are applied.
- **Duplication Filter:** Suppress narration lines that restate the last k lines of game output unless they add new context.
- **Safety & Alignment:** Block suggestions that contradict ground truth or encourage unsafe actions.
- **Memory Update Rules:** Promote only stable facts; demote or annotate contested facts; never store raw hallucinations.

---

## 8. Evaluation & Iteration Hooks

- **Trace & Review:** Keep a small corpus of interaction logs and model outputs for periodic review.
- **Heuristic Metrics:** Track duplication rate, contradiction flags, hint usefulness ratings, and memory promotion events.
- **A/B Prompt Trials:** Rotate prompt variants (tone, constraints, memory selection) and compare outcome metrics.

---

## 9. Roadmap Themes (Non-binding)

- **Better Salience Detection:** Lightweight scoring to decide which events and facts enter context.
- **Narration Personas:** Configurable voice packs with style constraints and guardrails.
- **Adaptive Memory Windows:** Dynamic sizing of episodic memory based on scene complexity.
- **User Controls:** Toggle transparency mode (show full structured payload) vs narrator-only mode.
- **Richer Hints:** Quest-thread tracking and non-spoilery guidance generation.
