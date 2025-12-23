# Player State & Scene Items Memory

## Purpose
Capture the documented agreement that the memory layer must reflect both scene-level objects and the player inventory as first-class state, then expose that data for prompts and UI without inventing new heuristics outside the established schema.

## Design Anchors
- **Documentation sources:**
  * `scratchpad/01_objectives_and_meta.md` clearly lists "player inventory" as part of the In-Game State Memory
  * `scratchpad/03_TUI_design.md` describes an "Items tree" whose top-level nodes are **Player Inventory** and **World**
  * `scratchpad/05_game_memory.md` and `memory_implementation.md` reinforce schema-driven aggregation (description lines, scene actions, current items)
- **Schema compliance:** Only fields derived from `EngineTurn` (plus the derived control fields such as `scene_intro_collection`, `scene_actions`, etc.) are acceptable inputs for the memory store. No additional parsing heuristics should be introduced at this layer.

## Requirements
1. **Scene items (`current_items` + `scene_items`):**
   - `scene_items` now records every object ever seen in the room via either `visible_items` *or* an `ActionRecord` categorized as `item_interaction` (e.g., `take nest`).
   - `current_items` reflects the live room contents. It updates directly from `EngineTurn.visible_items` when the engine reports them, and otherwise relies on the structured `ActionRecord` effects (`take`, `drop`, `put`, etc.) so the room stays authoritative even when the transcript omits follow-up lists.
   - Multi-line outputs (inventory dumps, leaflet text) are normalized before storage so we avoid accidental duplication caused by transcript wrapping.
2. **Player inventory state:**
   - The store maintains a persisted `_player_state` table containing the latest inventory, score, and move count mirrored from `engine_turn.player_state`.
   - Every change emits a `state_change` log entry and becomes part of the scene envelope so prompts/UI can render the exact item list without heuristics.
3. **Action updateness signal:**
   - `scene_action_added` now writes both the legacy string summary and the structured `ActionRecord`. Downstream consumers should prefer the structured form because it carries verb, category, and `target_item` data needed for inventory/world synchronization.
   - Movement actions still use the destination room as their result; all other actions hold the full normalized transcript block (not just the first line) so rich outputs are preserved for prompt building.

## Implementation Tasks
1. **Augment `GameMemoryStore` with inventory tracking** ✅
   - `_player_state` TinyDB table stores the latest inventory/score/moves snapshot per player.
   - `get_context_for_prompt()` exposes this under `player_state`, and `log_state_change` events capture every delta for audit.
2. **Scene items refresh logic** ✅
   - ActionRecords categorized as `item_interaction` now add/remove entries from both `scene_items` and `current_items` when the engine transcript omits `visible_items`.
   - Movement/world-object actions continue to rely on `visible_items`, but we normalize their multi-line descriptions so deduplication works.
3. **Documented behavior and tests** ✅
   - Schema updated with `ActionRecord` definition plus player-state envelope, TinyDB now persists `_player_state`, and `testing/test_turn_lifecycle_order.py` exercises the memory-before-completions contract.

## Audit & Traceability
- Every change to `current_items`, `scene_items`, and `player inventory` must emit a `my_logging.log_state_change` entry so we can replay the timeline.
- Scene-level updates remain purely additive/deduplicative; the only mutation path for these lists is through the schema-derived heuristics or the explicit action-triggered refresh described above.

## Advisory LLM Enrichment
- LLM enrichment jobs annotate scenes with additional inference fields (e.g., inferred motives, thematic tags, confidence scores) but do so asynchronously. Each enrichment result is tied to the turn it references and may arrive only after subsequent turns, so downstream consumers must treat those annotations as optional, late-arriving hints rather than overwriting the canonical memory state.
- If an enrichment job is skipped or fails, the player state and scene items remain authoritative—this is the expected behavior. Enrichments simply add more context when they complete, without introducing blocking waits.

## Next Steps
1. Implement the inventory snapshot storage and logging in `GameMemoryStore`.
2. Enhance `scene_actions` to note when a command impacts visible items, and tap that signal to refresh `current_items` if necessary. ✅ (ActionRecord-driven updates now perform this deterministically.)
3. Verify the JSON schema (config/game_engine_schema.json) is extended if we start persisting the inventory snapshot as part of the `EngineTurn`-like record or a new memory event. ✅
4. Update docs or tests that display the Items tree so they rely on the new player inventory plumbing rather than derived heuristics. 🔄 (Ongoing as the TUI items panel is refreshed.)

## TODO · Schema Alignment Gaps
- [x] **P0 – Emit `SceneEnvelope` payloads**: Every turn now writes `{ scene, engine_turn }` envelopes to JSONL so downstream analytics consume the schema verbatim.
- [x] **P0 – Provide `engine_turn.player_state`**: `EngineFacts` exposes a `PlayerStateSnapshot`, `GameAPI` threads it through `EngineTurn`, and the memory layer persists it without inventing new containers.
- [x] **P1 – Persist player inventory snapshot**: `GameMemoryStore` mirrors the latest inventory inside `_player_state`, logs every delta, and exposes it via `get_context_for_prompt()`.
