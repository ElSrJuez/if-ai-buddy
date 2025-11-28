# Minimal TUI — Notes Only

A thin Rich-based interface that keeps parser output, narrator output, and command entry separate while we prove the loop works.

## Goals
1. Two-column layout: left for raw game transcript, right for narrator payload.
2. Single input line anchored at the bottom with command history recall.
3. Non-blocking updates so the UI can repaint when either column changes.
4. Minimal instrumentation: capture timestamps per turn, surface a status line with latency + active PID.

## Structure
- **TranscriptPanel**: scrollable panel that appends parser text verbatim, highlights room headers, and keeps ~200 lines.
- **NarratorPanel**: scrollable panel that receives narration paragraphs and badges (e.g., "Hint", "Intent").
- **CommandInput**: text input widget with submit handler; dispatches commands to the main loop dispatcher.
- **StatusBar**: one-line footer showing model name, RU/token costs, and last error indicator.

## Event Flow
1. Player types command → `CommandInput` raises an event with the raw string.
2. Main loop sends command via REST helper, then pushes transcript string back into the UI queue.
3. Completions helper returns structured narration → converted to formatted blocks and appended to NarratorPanel.
4. StatusBar updates with turn counter, PID, latency breakdown.

## Minimal Interactions
- UI never calls HTTP or LLM helpers directly; it only sends/receives messages from the orchestrator.
- Panels simply append strings; no diffing or complex rendering yet.
- Uses Rich’s default theme; no custom CSS/colour work at this stage.

## Exit Handling
- `/quit` or Ctrl+C triggers the main loop to stop and emits a final message in both panels.
- UI tears down after the helper confirms the session is deleted.
