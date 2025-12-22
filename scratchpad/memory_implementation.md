# Memory Implementation TODO

1. **Scene Intro Collection (previous scene only)**
   - Confirm `Scene` stores just the immediate predecessor room, move number, and command/action that brought the player into the current room (no longer an unbounded history).
   - Update `GameMemoryStore` logic to capture this shim on every `EngineTurn` that crosses scenes, persisting it to TinyDB and emitting the associated JSONL event via `my_logging` so the metadata is auditable.
   - Ensure `scene_intro_collection` now reflects a single entry per `Scene` representing the last ingress, and that downstream prompt builders rely on this for “how we got here” context.

2. **Current Items heuristics layer for actions on items, llm layer for more advanced game engine room description interpreting**
   - implement a smart heuristics of action verbs on items and item game responses. 
   - Park: Implement a llm layer that inspects each `EngineTurn.description` for repeated reference to objects or explicit statements that items remain (e.g., "a small mailbox here" "still contains"), and classify those as `current` while otherwise demoting them to `sceneItems`.
   - Expose a dedicated `EngineFacts.current_items` collection (or reuse `visible_items`/`inventory` if they reliably reflect persistence) so `GameMemoryStore.update_from_engine_facts` can store the normalized list in `Scene.current_items`.
   - Document the exact text cues used for the classification so any future reviewer understands why a line is marked `current` instead of simply `seen`.

3. **NPC detection (parked)**
   - Record that NPC tracking is unexercised; leave a placeholder field in `Scene` and a comment in heuristics to revisit once NPC encounters appear.
   - Maintain a TODO to implement detection heuristics later when NPC output becomes available (log to `scratchpad/memory_implementation.md` once evidence surfaces).

4. **Scene Actions (follow schema-defined tuple)**
   - identify that actions are diverse, driven by the user's command verb
   - Per the schema, each `scene_actions` entry should capture `"command -> result"` plus an optional type tag. Ensure `game_engine_heuristics` consistently emits that tuple for both movement and interaction commands by parsing the transcript and capturing the engine’s outcome line (e.g., the new room name or a success/failure message).
   - Pass the parsed action object into `GameMemoryStore.update_from_engine_facts` so the Scene stores the normalized string/structure without assuming only movement verbs appear.
   - Log `scene_action_added` events via `my_logging.log_memory_event` with the same schema so we retain a traceable history of every command/result pair.

8. **Narrations (parked)**
   - Leave a placeholder note acknowledging narrations are not implemented yet; once the LLM layer is online, revisit this document to specify how narrations attach to scenes and which metadata needs capturing.

Each step should reference the owning module (`game_engine_heuristics`, `game_memory`, `my_logging`, etc.) and keep the hierarchy of `EngineTurn -> Scene -> Narration` intact. Once implemented, update `game_engine_schema.json` or other configs to reflect the new fields.
