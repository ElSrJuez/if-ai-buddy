# Useful Prompting — Issues Observed in `log/Adventurer_common_llm_layer.jsonl`

This note is a **brainstorming** document: it describes what appears “wrong” in the prompt/response log and outlines **apparent root causes** in the current architecture. It is intentionally **not** a fix plan.

---

## 0) What this log actually is

`log/Adventurer_common_llm_layer.jsonl` is a JSONL trace of **LLM calls** made through the “common LLM layer.” Each entry contains:

- `timestamp`, `model`
- `request`: provider/model and the **full chat messages** (system + user prompt)
- `streamed_text`: the concatenated streamed output text
- `raw_text_deltas`: the raw textual delta fragments captured during streaming
- `raw_parts_preview`: first/last chunk preview (best-effort) for debugging
- `response`: currently logged as `null` in the sampled entries

This log is therefore both:

1) an **observability artifact** (you can see what was sent/received), and
2) a **data structure** you might want to query later.

---

## 1) High-signal issues *in the log itself*

### 1.1 Missing correlation / identity fields
**Symptom**: JSONL entries are hard to tie back to one “turn,” “session,” or “trigger.”

**What’s missing** (examples):
- `session_id` / `player_id` / `run_id`
- `turn` / `move` / `command`
- a durable `request_id` linking the LLM call to a memory transaction or engine turn

**Why it matters**:
- You can’t tell whether repeated prompts are retries, resets, multiple triggers, or bugs.
- You can’t aggregate “how often did narration fire per move?” or “which trigger caused this output?”

**Likely root cause**:
- The log record is written from the streaming layer (`module/common_llm_layer.py`) which is intentionally generic and does not know about game context unless the caller passes it.

---

### 1.2 `response: null` is misleading
**Symptom**: Entries show `response: null` even though we clearly received content (`streamed_text`) and chunk previews.

**Why it matters**:
- When scanning logs, `response: null` looks like the request failed.
- Downstream tooling/queries can’t distinguish “no response object” from “no response returned.”

**Likely root cause**:
- The log writer is called with `response=None` (or a provider wrapper doesn’t expose a final response object in streaming mode).
- The code emphasizes streaming deltas (good) but does not standardize “final response metadata.”

---

### 1.3 Redundant / high-noise payload (hard to read, expensive to store)
**Symptom**: Debug entries contain:
- full prompt text
- every `raw_text_deltas` fragment
- chunk previews

This can create **very large** JSONL lines and makes it difficult to locate anomalies.

**Why it matters**:
- Manual inspection is slow.
- Any sharing of logs becomes riskier.
- Storage grows quickly.

**Likely root cause**:
- Debug mode is optimized for “everything preserved” rather than “query-friendly structured summary.”

---

### 1.4 Logs contain full third-party transcript content
**Symptom**: The prompt embeds raw game transcript text, including copyrighted text.

**Why it matters**:
- Local development: usually fine.
- Sharing / attaching logs to tickets / posting snippets: high risk.
- Makes redaction difficult because the raw transcript is embedded deep inside `request.messages`.

**Likely root cause**:
- The narration prompt template includes the raw transcript delta and scene lines.

---

### 1.5 Repeated near-identical prompts/outputs without explanation
**Symptom**: You see the same “initial scene” prompt patterns and identical outputs appearing at multiple timestamps.

**Why it matters**:
- It looks like duplication or a loop.
- Without correlation fields, you cannot prove whether these are separate sessions or accidental repeats.

**Likely root cause** (several possibilities):
- Narration triggered on multiple events close together.
- A reset/restart path replays the opening transcript.
- The controller retries on network/model hiccups but the retry is not labeled.

---

## 2) Prompt-content issues visible inside the log (quality + correctness)

These are not “logging schema” issues; they are **prompt construction and pipeline semantics** issues. They are visible because the full prompt is included in each log entry.

### 2.1 Misleading label: `Visible:` is not “currently visible”
**Symptom**: The prompt includes a section like `Visible: ...`, but it appears to behave like “ever seen in this room” rather than “visible right now.”

**Root cause in code**:
- `module/narration_job_builder.py` builds `Visible:` from `scene.get("scene_items")`.
- `scene_items` in `module/game_memory.py` is **accumulative** (append if new, never remove).
- `current_items` exists and is updated from the latest `facts.visible_items`, but the prompt label uses `scene_items`.

**Effect**:
- The prompt can contain contradictions:
  - The latest transcript can say “you can’t see X,” while `Visible:` still lists X because it was seen in the past.
- This is a *prompt correctness* issue even if the memory model is behaving as designed.

---

### 2.2 “Transcript delta” formatting can blur signal
**Symptom**: `Transcript delta:` is built by joining the last ~4 non-empty lines into one string.

**Root cause in code**:
- `NarrationJobBuilder._extract_transcript_delta()` joins lines and truncates.

**Effect**:
- Multi-line engine output becomes one long line, which can:
  - reduce readability
  - hide structure like room header vs. response text
  - accidentally merge unrelated lines into one “delta”

---

### 2.3 Prompt includes narrator history that can anchor or amplify errors
**Symptom**: The prompt includes `=== Narrator already said ===` with prior LLM outputs.

**Why it can be problematic**:
- If the narrator once invented something, that invention becomes part of the *prompt history*.
- Even if the system prompt forbids invention, the next completion can treat the narrator history as “canon.”

**Likely root cause**:
- The system is trying to maintain continuity by feeding prior narrations, but it does not distinguish between:
  - engine-grounded facts
  - narrator prose that may contain hallucinations

---

### 2.4 Weak enforcement of system constraints
**Symptom** (as observed in the log output):
- Narrations often exceed the requested “exactly 1–2 sentences.”
- Narrations invent details beyond the engine transcript.

**Likely root cause**:
- Constraint enforcement is “prompt-only.” There is no post-generation validator/trimmer.
- Small instruction-following models can drift, especially with long context and narrative momentum.

---

## 3) Pipeline-level semantic gaps revealed by the log

### 3.1 The log does not capture which *prompt builder/version* produced the prompt
**Symptom**: You can see the prompt text but not:
- which prompt template/config version was used
- what limits were applied (max transcript chars, history count, etc.)

**Root cause**:
- Config and template parameters are applied in `NarrationJobBuilder`, but not exported into LLM log metadata.

**Effect**:
- When prompt behavior changes due to config edits, the logs are not self-describing.

---

### 3.2 No capture of “reason for narration trigger” in the LLM log
**Symptom**: The prompt contains some hints (“Recent actions”), but the log entry doesn’t clearly capture:
- trigger name (e.g., move completed vs. look vs. inventory)
- the command that caused it
- whether it was a retry

**Root cause**:
- Narration trigger metadata exists (`NarrationJobSpec.metadata` includes `trigger`, `turn_count`, `room`), but it appears not to be included in the common LLM layer JSONL record.

---

### 3.3 Missing runtime/operational fields
**Symptom**: There’s no latency, token usage, finish reason, retry count.

**Effect**:
- Hard to compare provider/model performance.
- Hard to tell “slow response” vs. “stalled stream” vs. “partial output.”

---

## 4) Apparent “root causes” mapped to modules

This is the most plausible mapping from observed log behavior to code responsibilities.

### 4.1 Prompt wording/labels and context selection
- **Module**: `module/narration_job_builder.py`
- **Root causes**:
  - uses `scene_items` but labels it `Visible`
  - transcript delta concatenation may reduce clarity
  - includes narrator history without a “grounded facts” boundary

### 4.2 Memory semantics: accumulative vs. current
- **Module**: `module/game_memory.py`
- **Root causes**:
  - `scene.scene_items` is “ever seen” (append-only)
  - `scene.current_items` is “currently visible” but may not be used in prompts

### 4.3 Engine transcript parsing heuristics
- **Module**: `module/game_engine_heuristics.py`
- **Root causes**:
  - Regex-based extraction can miss nuance (negations, lists, implicit objects)
  - Visible extraction is generic and may over/under-collect in edge cases

### 4.4 LLM streaming and logging schema
- **Module**: `module/common_llm_layer.py`
- **Root causes**:
  - log record optimized for streaming text capture, not for correlation/querying
  - `response` not populated; request context not enriched with game metadata

---

## 5) Quick “diagnostic questions” to validate the hypotheses (no fixing)

If you want to sanity-check these root causes, here are high-yield questions:

1) **Is the narration prompt intended to reflect “current visible objects” or “known objects in the room”?**
   - If it’s current visibility, `Visible:` should likely come from `current_items`, not `scene_items`.

2) **Do we intend narrator history to be treated as canon?**
   - If not, you may want a split between “facts from engine” and “flavor text.”

3) **Are repeated prompts due to retries or multiple triggers?**
   - If yes, the log needs a `trigger` and `request_id` and perhaps `retry_of`.

4) **Do we need shareable logs?**
   - If yes, consider whether transcript should be hashed/redacted or stored separately.

---

## 6) Takeaway

The log is doing its core job—recording prompts and streamed completions—but it is **not yet an audit-friendly, query-friendly trace**.

The biggest *practical* correctness issue visible in the log is a **semantic mismatch**:

- `Visible:` in prompts is derived from **accumulated scene items** (`scene_items`), not necessarily **currently visible items** (`current_items`).

That alone can make prompts appear contradictory even when the engine transcript is correct.

---

## Gamer Pal Narration Goals and Meta-Goals

Strategic objectives and agreements extracted from the markdown collective:

### Core narration objectives (player-facing)
- Provide a **timely, context-aware narrator** that transforms raw transcript into coherent, engaging commentary.
- Maintain **non-duplicit output**: reduce repetition/contradictions; be additive rather than echoing engine text.
- Provide **actionable, non-railroading hints** (context-sensitive nudges; avoid spoilers).
- Preserve **consistent tone/persona** while adapting to context (discovery, failure, puzzle-solving).
- Support **streamed delivery** so narration arrives incrementally and the UI stays responsive.

### Memory objectives (within-run)
- Maintain **episodic memory** of the last N interactions to support immediate continuity.
- Maintain **in-game state memory** anchored to engine output: rooms, items, NPCs, inventory, actions, progress.
- Track **beyond-immediate run history** (threads, intentions, transitions) without persisting across separate sessions.
- Enforce **memory hygiene**: curate/limit what is stored; avoid noise, duplication, and volatile facts.
- Provide **conflict resolution**: detect/reconcile inconsistencies between transcript, episodic memory, and state memory before surfacing narration.

### Ground-truth and safety agreements
- **Heuristic memory is authoritative**; LLM outputs must not overwrite canonical facts without explicit reconciliation policy.
- Prefer **factual alignment** with base game output; avoid fabricated objects/knowledge.
- If LLM output is incomplete or malformed, prefer **minimal, explicit error/skip behavior** over fabrication.

### Canonical turn lifecycle contract (ordering)
- Every turn (including intro/turn 0) follows: **Parse → Record → Context → Completion → Append Narration**.
- **Parse once** per turn via the canonical heuristics module; no re-parsing in downstream layers.
- **Record memory before prompt construction** so prompts always see the latest committed state.
- **Append narration only after completion** via a dedicated memory append pathway.

### LLM services + non-blocking guarantees
- Separate concerns into two LLM roles:
  - **Narration Service** (creative UI output; event/idle-triggered; may stream).
  - **Memory Enrichment Service** (future; advisory annotations; schema-structured; turn-triggered).
- LLM work is **non-blocking**: gameplay must never wait on narration/enrichment.
- Use **event-driven triggers** (engine-turn, player-command, idle) rather than “always exactly one call per turn.”
- Use **bounded queues/backpressure** with explicit skip/drop/cancel rules; late results are tagged, not silently merged.

### Prompting + schema discipline
- Use **schema-guided responses** where appropriate to keep outputs reliably parseable.
- Keep prompt context **compact and efficient**: sliding windows, salience-first selection, no duplicated fields.
- Maintain clear separation of pipelines:
  - deterministic `game_engine_heuristics` for engine facts
  - `ai_engine_parsing` for LLM output normalization/validation

### Scene/item semantics agreement (important for prompt correctness)
- Distinguish:
  - `scene_items` = objects **ever seen** in the room (accumulative)
  - `current_items` = objects **currently present** (latest known)
- Prefer structured **ActionRecords** for durable state transitions and audit/replay.

### Observability + logging agreements
- Treat logs as an **observability contract** (debuggable, replayable, queryable).
- Keep **structured telemetry (JSONL)** separate from the plain-text system log.
- Keep log paths **config-driven**; avoid hidden defaults.
- Preserve **player identity integrity**: renames/restarts must not mix player-scoped logs/memory.

### Engineering agreements (process/quality)
- **Config-driven behavior** and **fail-fast** on missing config; avoid silent fallbacks.
- DRY + separation of concerns: heuristics, memory, controller orchestration, prompt building, transport, UI are distinct.
- Testing should be **focused and observable** (scripts that clearly log objective, inputs, expected outputs).
