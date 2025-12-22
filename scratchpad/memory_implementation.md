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

4. **Scene Actions (clarify result semantics per schema)** [DONE]
   - Extended to distinguish action types:
     - Movement verbs: result = new room_name (e.g., "west -> Forest")
     - Interaction verbs: result = first line of description (e.g., "open mailbox -> Opening the small mailbox reveals a leaflet")
   - Eliminates conflation of movement and interaction commands
   - Emits `scene_action_added` event with command, result, and implicit type
   - Uses only schema data (EngineTurn fields) without inventing heuristics

## 📋 PENDING / PARKED

5. **Narrations (parked)**
   - Not implemented yet; revisit once LLM layer is online.

## Design Principles Applied
- **Respect the schema:** Only use fields from `EngineTurn` (game_engine_schema.json); don't invent derived data.
- **Aggregate, don't distribute:** `Scene` collects and deduplicates; don't scatter logic across modules.
- **DRY:** Use facts as parsed by heuristics, don't re-parse in memory layer.
- **Audit:** Log every state change via `my_logging` so transitions are traceable.
