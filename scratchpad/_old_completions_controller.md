# Completion Handling – Challenges & Separation of Concerns

## 1. What we need to achieve
| Need | Description |
|------|-------------|
| **A. Live UI streaming** | As tokens arrive from the LLM they must appear **immediately** in the “AI Output” pane.  |
| **B. Capture full response** | After the call finishes we require the *entire assistant reply* (a single string) to persist in logs / memory for: replay, evaluation, and future context. |
| **C. Transport-agnostic design** | Whether we use streaming or non-streaming completions must *not* ripple through UI or logging code; only the completion adapter changes. |

---

## 2. Current implementation (problems)

Component: `completions.stream_to_ui`

| Responsibility | Implementation | Observation |
|----------------|----------------|-------------|
| Build prompts  | ✅ `build_messages()` pure, simple |
| Send request   | ✅ Uses `client.chat.completions.create(stream=True)` |
| Live display   | ✅ Feeds each chunk to `ui.write_ai()` |
| **Start new block** | **Missing** – caller never tells UI a new answer has begun, so consecutive answers blend together |
| Log **request** | ✅ Writes `messages` to `ai.jsonl` |
| Log **response** | **Missing** – streamed deltas are not re-assembled or persisted |
| Error handling | **Missing** – exceptions abort stream, UI may hang |
| Coupling       | OpenAI call + UI logic are in one function → limited flexibility |

---

## 3. Proposed separation of concerns

```
            Controller
                │
 ┌──────────────┼──────────────┐
 │                              │
CompletionService         UI Renderer
(build + call + log)      (write / append)
```

### 3.1 CompletionService
Single responsibility: *given* recent game lines, return a **generator** that yields tokens **and** finally exposes the full answer.

Pseudo-API:

```python
class CompletionService:
    def get_stream(self, recent_lines) -> Generator[str, None, str]:
        """
        Yields streamed chunks; returns final full_text on StopIteration.
        Handles:
        • build_messages()
        • openai call (streaming / non-streaming)
        • request & response logging
        • error handling / retries
        """
```

Key points  
• Works in streaming *or* non-streaming modes; callers don’t care.  
• Accumulates `full_text` internally; writes to log once complete.  
• Emits events (`yield chunk`) that any UI can subscribe to.

### 3.2 UI Renderer (`RichZorkUI`)
Responsibilities:  
• `start_ai_message(separator:str|None)` – allocate new block + optional visual divider  
• `write_ai(chunk:str)` – append chunk to current block  
• `finalize_ai_message(full_text:str)` – called once to signal end (if UI needs a footer, progress stop etc.)

No knowledge of OpenAI, prompts, or logging.

### 3.3 Controller / Orchestrator
Glue code:

```python
def ask_ai(ui: RichZorkUI, recent_lines: list[str], svc: CompletionService):
    ui.start_ai_message("─"*40)
    full_text = ""
    for chunk in svc.get_stream(recent_lines) as part:
        ui.write_ai(part)
        full_text += part
    # generator finished, we already have full_text
    ui.finalize_ai_message(full_text)   # optional
```

Now:
• Bugs in UI (e.g., missing separators) stay local.  
• Bugs in logging / OpenAI params stay within `CompletionService`.  
• Switching to `stream=False` only affects `CompletionService`.

---

## 4. Migration steps

1. Create `services/completions.py`
   • Move `build_messages`, OpenAI call, logging there.  
   • Provide `get_stream()` generator that yields chunks and finally returns full text.

2. Extend `RichZorkUI`
   • Add `start_ai_message`, `finalize_ai_message`.  
   • Keep existing `write_ai` as-is.

3. Refactor callers
   • Replace calls to `stream_to_ui` with the Controller pattern above.

4. Unit-test
   • Mock CompletionService to yield known chunks; assert UI lines/separators.  
   • Verify `ai.jsonl` contains both request & response.

---

## 5. Benefits

• **Debuggability** – Each layer can be tested in isolation; missing separators or logging gaps surface quickly.  
• **Extensibility** – Swap OpenAI for another backend, or switch to batch (non-streaming) mode.  
• **Maintainability** – Clear contracts (`get_stream`, `start_ai_message`, etc.) reduce cross-cutting concerns.
