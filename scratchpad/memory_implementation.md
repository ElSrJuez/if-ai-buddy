# Memory Implementation TODO

## ✅ COMPLETED

1. **Scene Intro Collection (previous scene only)** [DONE]
   - Changed `GameMemoryStore.update_from_engine_facts()` to replace (not append) `scene_intro_collection` with single entry
   - Uses `facts.moves` for move_number with fallback to `self._turn_count`
   - Emits `scene_intro_updated` JSONL event with complete metadata
   - Ensures downstream prompt builders have clear "how we got here" context

2. **Current Items (clarify source and aggregation rules)** [DONE]
   - Updated to populate from `EngineTurn.visible_items` (room objects) instead of inventory
   - Semantics defined: `current_items` now tracks objects remaining in the current room
   - Emits `state_change` event when current_items differ from previous turn
   - Schema-respecting: uses only EngineTurn fields without custom extraction

3. **NPC detection (parked)**
   - Record that NPC tracking is unexercised; leave a placeholder field in `Scene` and a comment in heuristics to revisit once NPC encounters appear.
   - Maintain a TODO to implement detection heuristics later when NPC output becomes available (log to `scratchpad/memory_implementation.md` once evidence surfaces).

4. **Scene Actions + Action Records** [DONE]
   - Added structured `ActionRecord` objects alongside the legacy string list
   - Each record carries `turn`, `command`, `result`, `category`, `verb`, and `target_item`
   - Categories now distinguish `movement`, `item_interaction`, `world_object_interaction`, and `generic_interaction`
   - Scene/world state updates (current items, scene items, player inventory) are driven by these canonical records so we never re-parse transcripts in downstream layers

5. **Engine description + multi-line handling** [DONE]
   - `_extract_description()` now skips initial blank lines and continues until the body ends, so the “West of House…” prose is retained
   - Memory storage splits transcript prose into canonical paragraphs (not single wrapped lines) while preserving indented lists, preventing duplicates such as `"This is a"` / `"forest"`
   - Action summaries fall back to the full transcript body when descriptions are missing so commands like `read leaflet` capture the entire output

## 📋 PENDING / PARKED

6. **Narrations (parked)**
   - Not implemented yet; revisit once LLM layer is online.

7. **Multi-verb commands (parked)**
   - ActionRecords currently capture one record per player input; if the player chains verbs ("take nest and climb tree"), the record category is dominated by the room change and embedded item verbs do not execute yet.
   - Future LLM parsing should emit sub-actions so inventory/world state can reflect every clause deterministically.

## Design Principles Applied
- **Respect the schema:** Only use fields from `EngineTurn` (game_engine_schema.json); don't invent derived data.
- **Aggregate, don't distribute:** `Scene` collects and deduplicates; don't scatter logic across modules.
- **DRY:** Use facts as parsed by heuristics, don't re-parse in memory layer.
- **Audit:** Log every state change via `my_logging` so transitions are traceable.

## Async Enrichment Reminder

- Memory enrichment is an advisory background job that runs after heuristics record a turn. It receives the parsed scene facts, may emit confidence-scored suggestions or inferred entities, and never blocks the prompt preparation for the next turn.
- Enrichments are keyed to a specific turn, so if a new turn arrives before enrichment completes, the late job can safely log its outcome without mutating canonical memory or delaying gameplay.
