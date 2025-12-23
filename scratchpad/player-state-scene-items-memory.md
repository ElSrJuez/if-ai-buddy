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
   - `scene_items` remains the union of every visible object mentioned in `EngineTurn.visible_items` for that room.
   - `current_items` reflects the latest `visible_items` list so downstream consumers know what is currently present.
   - Because `visible_items` reports only what the engine explicitly announces, we additionally monitor action results for any textual cues that would warrant a follow-up rewrite (e.g., an action result that produces a new "there is a..." paragraph) and treat that as an implicit refresh trigger.
2. **Player inventory state:**
   - `facts.inventory` is the only source of truth for what the player is carrying; it is tracked separately from `current_items` so the UI can show both the world state and the player’s items without conflating the two caches.
   - When `facts.inventory` changes, emit a `state_change` event and persist the new list in the relevant `Scene` (or a higher-level store if needed) so the prompt builder can refer to `scene.current_items` for the room and the latest inventory snapshot for the player.
   - Because inventory is global (not per-scene), consider a lightweight registry or field on `GameMemoryStore` that mirrors the last-known inventory list and is stored explicitly in TinyDB for audits.
3. **Action updateness signal:**
   - Each `scene_action_added` event must include the command/result pair and, when available, any recognized visible-item effects so that consumers can decide whether to refresh `current_items` without retrying heuristics outside the schema.
   - Movement actions continue to use the target room as the result; interaction actions surface the first description line as before.

## Implementation Tasks
1. **Augment `GameMemoryStore` with inventory tracking:**
   - Introduce a `last_inventory` field stored on the scene or the store itself.
   - When `facts.inventory` changes (non-null, different set), log a `state_change` event and persist the new list; also expose it in `get_context_for_prompt()` under `player_inventory`.
2. **Scene items refresh logic:**
   - Keep populating `scene.scene_items` and `scene.current_items` from `facts.visible_items` as before.
   - Add a lightweight helper that watches recent `scene_action_added` results for keywords such as "there is" or explicit visible-item lists, and if such a description is present, trigger an immediate pass to update `current_items` (without re-parsing the entire transcript, simply re-use the already available `visible_items` list or cue the heuristics layer to re-run on the same transcript).
3. **Documented behavior and tests:**
   - Extend the TinyDB persistence schema to include the new inventory snapshot (if stored at the scene level) or a separate `player_state.json` record, matching what the UI docs expect.
   - Update or add tests to cover the dual reporting of player inventory and scene item lists, ensuring the JSONL audit log reflects the new `state_change` and `scene_action_added` semantics.

## Audit & Traceability
- Every change to `current_items`, `scene_items`, and `player inventory` must emit a `my_logging.log_state_change` entry so we can replay the timeline.
- Scene-level updates remain purely additive/deduplicative; the only mutation path for these lists is through the schema-derived heuristics or the explicit action-triggered refresh described above.

## Next Steps
1. Implement the inventory snapshot storage and logging in `GameMemoryStore`.
2. Enhance `scene_actions` to note when a command impacts visible items, and tap that signal to refresh `current_items` if necessary.
3. Verify the JSON schema (config/game_engine_schema.json) is extended if we start persisting the inventory snapshot as part of the `EngineTurn`-like record or a new memory event.
4. Update docs or tests that display the Items tree so they rely on the new player inventory plumbing rather than derived heuristics.
