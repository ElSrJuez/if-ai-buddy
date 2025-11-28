# AI Narration Flow

Detailed walkthrough of how a single player interaction produces the AI narration that appears in the right-hand panel.

---

## 1. Player Command Lifecycle

1. **UI bootstrap (GameUI)**
   - Lazily constructs the game UI and calls `start()` so the dual-pane layout begins rendering and accepting keyboard input.

2. **Game text accumulation (append_game_output)**
   - Every game message funnels through a single output function, which:
     - pushes the text into the left pane via `GameUI.append_game_output`.
     - appends non-duplicate lines into the global `InteractionLog`, creating the rolling transcript that the AI later reads.
     - records `(message, caller)` tuples in a transient print cache for diagnostics/logging and writes them via the logging layer.

3. **Prompting for the next command (read_player_input)**
   - Before asking the player for a new action, the input routine:
     - grabs and clears the print cache so freshly printed text is included in `InteractionLog`.
     - calls `stream_to_ui(ui, InteractionLog[-MAX_LOG_LINES:])` which kicks off the AI narration update described in sections 2–4.
   - After the narration stream finishes, `GameUI.read_prompt` captures the player’s typed command, echoes it in the left pane (`append_game_output`), and stores an uppercase version (e.g., `"> LOOK"`) back into `InteractionLog` for future context.

Result: right before every user input, the AI gets a chance to comment on the most recent game state using the same history the player sees.

---

## 2. Turning History into an LLM Prompt (CompletionService.build_messages)

1. **History slicing**
   - `MAX_LOG_LINES` (from config) limits how many of the `InteractionLog` lines are fed to the model, avoiding unbounded prompts.

2. **Prompt templates**
   - A system prompt injects the response schema directly into the instructions so the model knows the exact JSON structure it must return.
   - A user prompt is filled with the recent log excerpt and emphasizes that entries alternate between game output and player commands.

3. **Message list**
   - `build_messages` returns a standard chat payload like `[{"role": "system", ...}, {"role": "user", ...}]` for the chosen LLM client.

---

## 3. Request/Response Orchestration (CompletionService)

1. **Logging and schema enforcement**
   - The request is logged to an audit trail before being sent.
   - `response_format` uses JSON schema mode so the model is contractually required to emit the structure defined by the configured schema (e.g., `game-last-objects`, `hidden-next-command`, `narration`).

2. **Model invocation**
   - The service calls the configured chat completions API of the LLM client.

3. **Parsing safeguards**
   - The parser removes code fences and attempts to parse the message into a dict, with fallback heuristics to extract narration when the output is malformed.

4. **Persistent audit trail**
   - The parsed JSON is appended to the audit log, keeping request/response pairs for debugging and future analysis.

5. **Choosing what to stream**
   - If `stream_only_narration` is true in config, only the `"narration"` field is streamed to the UI; otherwise, the entire JSON blob (pretty-printed) is shown for transparency/debugging.

6. **Chunked streaming**
   - Long texts are broken into ~140-character segments so the UI can display them smoothly as they arrive.

7. **Controller hand-off**
   - `stream_to_ui` hands the generator returned by `CompletionService.get_stream` to `ask_ai`, which is responsible for the actual UI coordination.

---

## 4. UI Rendering and Audio (Controllers & GameUI)

1. **ask_ai orchestration**
   - `ask_ai` signals `GameUI.start_ai_message`, optionally inserting a separator line and toggling text color for readability.
   - As each chunk arrives from the completion service, `ask_ai` calls `ui.append_ai_output(chunk)` and accumulates the text.
   - When streaming completes, `ask_ai` forces generator finalization and calls `ui.finalize_ai_message(full_text)` to close styling and pass the entire narration string.

2. **GameUI behaviors**
   - Maintains two panes: left for canonical game output, right for AI narration.
   - Ensures each AI message sits inside its own styled block; separators visualize distinct turns.
   - On `finalize_ai_message`, attempts optional TTS playback when the narration isn’t JSON (e.g., pure sentences), logging any audio failures to the system log.

3. **Player sees narration**
   - The live display refreshes with every chunk, so the narrator text appears incrementally in the right pane before the prompt is shown for the next command.

---

## 5. Summary Timeline

1. The output routine collects recent world text → stored in `InteractionLog`.
2. The input routine fires before user typing → triggers `stream_to_ui` using the latest history slice.
3. `CompletionService` builds messages, enforces schema, calls the LLM client, logs the transaction, and yields narration chunks.
4. `ask_ai` streams those chunks into `GameUI`, which renders them (and optionally voices them) in the AI pane.
5. UI prompt reappears; player types the next command; the cycle repeats with a richer shared context between player and AI narrator.

This document should serve as the reference point for inserting additional processing stages (e.g., augmenting the structured "attribute-rich" section before narration) without losing sight of where each responsibility lives today.

## 6. Future-ready context builder

`build_narration_context(interactions)` encapsulates the same pipeline that `CompletionService.get_stream` relies on, minus the streaming/UI work:

- Reuses the current prompt assets (config + response schema) to build the system/user messages from the latest `InteractionLog` slice.
- Calls the LLM client with the strict JSON schema and logs the request/response to the audit trail, preserving today’s auditing artifacts.
- Applies the same parsing fallbacks so the returned `payload` matches what the UI narrator already consumes (`game-last-objects`, `narration`, etc.).
- Provides a `NarrationContext` object containing the messages, raw model content, parsed payload, and the narration string so future callers can extend or remix the result without touching UI concerns.

This helper is the new first stage for any narration feature: call it with the transcript to obtain the structured response, then decide—outside the completion service—whether to stream, cache, or transform it further.
