# AI Narration Flow

Detailed walkthrough of how a single player interaction produces the AI narration that appears in the right-hand panel.

---

## 1. Player Command Lifecycle

1. **UI bootstrap (`zork_io._ui_instance`)**
   - Lazily constructs `RichZorkUI` and calls `start()` so the dual-pane Rich layout begins rendering and accepting keyboard input.

2. **Game text accumulation (`zork_print`)**
   - Every game message funnels through `zork_print`, which:
     - pushes the text into the left pane via `RichZorkUI.append_zork`.
     - appends non-duplicate lines into the global `INTERACTIONS` list, creating the rolling transcript that the AI will later read.
     - records `(message, caller)` tuples in `_PRINT_CACHE` for diagnostics/logging and writes them via `zork_logging.game_log_json`.

3. **Prompting for the next command (`zork_input`)**
   - Before asking the player for a new action, `zork_input`:
     - grabs and clears `_PRINT_CACHE` (`collect_printed_messages`) so freshly printed text is included in `INTERACTIONS`.
     - calls `stream_to_ui(ui, INTERACTIONS[-MAX_LOG_LINES:])` which kicks off the AI narration update described in sections 2–4.
   - After the narration stream finishes, `RichZorkUI.read_prompt` captures the player’s typed command, echoes it in the left pane (`append_zork`), and stores an uppercase version (`"> LOOK"`) back into `INTERACTIONS` for future context.

Result: right before every user input, the AI gets a chance to comment on the most recent game state using the same history the player sees.

---

## 2. Turning History into an LLM Prompt (`completions.build_messages`)

1. **History slicing**
   - `MAX_LOG_LINES` (from `config.json`) limits how many of the `INTERACTIONS` lines are fed to the model, avoiding unbounded prompts.

2. **Prompt templates**
   - `SYSTEM_PROMPT` injects `response_schema.json` directly into the instructions so the model knows the exact JSON structure it must return.
   - `USER_TMPL` is filled with the recent log excerpt and emphasizes that entries alternate between game output and player commands.

3. **Message list**
   - `build_messages` returns `[{"role": "system", ...}, {"role": "user", ...}]`, the complete payload required by the OpenAI chat completion API (in this repo, the local Foundry-backed client described in `zork_ai.py`).

---

## 3. Request/Response Orchestration (`OpenAICompletionService`)

1. **Logging and schema enforcement**
   - The request is logged to `log/ai.jsonl` before being sent.
   - `response_format` uses `json_schema` mode so the model is contractually required to emit the structure defined in `response_schema.json` (e.g., `game-last-objects`, `hidden-next-command`, `narration`, etc.).

2. **Model invocation**
   - `client.chat.completions.create` goes through the Foundry Local service (`manager` and `alias` from `zork_ai.py`).

3. **Parsing safeguards**
   - `_find_json_payload` removes code fences and attempts to parse the message into a dict, with fallback heuristics `_extract_narration_from_text` if the output is malformed.

4. **Persistent audit trail**
   - The parsed JSON is appended to `ai.jsonl`, keeping request/response pairs for debugging and future analysis.

5. **Choosing what to stream**
   - If `stream_only_narration` is true in `config.json`, only the `"narration"` field is streamed to the UI; otherwise, the entire JSON blob (pretty-printed) is shown for full transparency/debugging.

6. **Chunked streaming**
   - `_chunk` breaks long texts into ~140-character segments so the Rich UI can display them smoothly as they arrive.

7. **Controller hand-off**
   - `stream_to_ui` hands the generator returned by `get_stream` to `ask_ai` (in `zork_ai_controllers.py`), which is responsible for the actual UI coordination.

---

## 4. UI Rendering and Audio (`zork_ai_controllers` & `zork_ui`)

1. **ask_ai orchestration**
   - `ask_ai` signals `RichZorkUI.start_ai_message`, optionally inserting a separator line and toggling text color for readability.
   - As each chunk arrives from the completion service, `ask_ai` calls `ui.write_ai(chunk)` and accumulates the text.
   - When streaming completes, `ask_ai` forces generator finalization and calls `ui.finalize_ai_message(full_text)` to close the color tag and pass the entire narration string.

2. **RichZorkUI behaviors**
   - Maintains two panes: left for canonical Zork output, right for AI narration.
   - Ensures each AI message sits inside its own styled block; separators visualize distinct turns.
   - On `finalize_ai_message`, attempts optional TTS playback via `zork_voice.speak` when the narration isn’t JSON (e.g., pure sentences), logging any audio failures to `system_log`.

3. **Player sees narration**
   - The Rich live display refreshes with every chunk, so the narrator text appears incrementally in the right pane before the prompt is shown for the next command.

---

## 5. Summary Timeline

1. `zork_print` collects recent world text → stored in `INTERACTIONS`.
2. `zork_input` fires before user typing → triggers `stream_to_ui` using the latest history slice.
3. `OpenAICompletionService` builds messages, enforces schema, calls the Foundry-backed OpenAI client, logs the transaction, and yields narration chunks.
4. `ask_ai` streams those chunks into `RichZorkUI`, which renders them (and optionally voices them) in the AI pane.
5. UI prompt reappears; player types the next command; the cycle repeats with a richer shared context between player and AI narrator.

This document should serve as the reference point for inserting additional processing stages (e.g., augmenting the structured "attribute-rich" section before narration) without losing sight of where each responsibility lives today.

## 6. Future-ready context builder

`zork_ai.create_narration_context(interactions)` now encapsulates *exactly* the same pipeline that `OpenAICompletionService.get_stream` relied on, minus the streaming/UI work:

- Reuses the current prompt assets (`config.json`, `response_schema.json`) to build the system/user messages from the latest `INTERACTIONS` slice.
- Calls the Foundry-backed client with the strict JSON schema and logs the request/response to `log/ai.jsonl`, preserving today’s auditing artifacts.
- Applies the same parsing fallbacks (`_find_json_payload`, `_extract_narration_from_text`) so the returned `payload` matches what the UI narrator already consumes (`game-last-objects`, `narration`, etc.).
- Provides a `NarrationContext` dataclass containing the messages, raw model content, parsed payload, and the narration string so future callers can extend or remix the result without touching UI concerns.

This helper is the new first stage for any narration feature: call it with the transcript to obtain the structured response, then decide—outside `zork_ai`—whether to stream, cache, or transform it further.
