# if-ai-buddy
Your Interactive Fiction AI Buddy - Enhance the Gaming Experience of Text Adventures

A modern Python playground that fuses  beloved Text Adventures with a live AI companion, while an LLM provides concise, structured insights and narration – all inside a snappy Rich TUI.

---

## 📚 Table of Contents
1. [Features](#features)
2. [Getting Started](#getting-started)
3. [Playing the Game](#playing-the-game)
4. [Architecture & Configuration](#architecture--configuration)
5. [Credits & License](#credits--license)

---

## Features
| Category | Highlights |
|---|---|
| **Authentic Gameplay** | Relies on a Rest-API dfrotz wrapper. (see `https://github.com/opendns/zmachine-api/blob/master/README.md`). |
| **AI Gaming Pal** | OpenAI-compatible model (local or cloud) produces structured JSON with: `game-intent`, `game-meta-intent`, and `narration`. |
| **Textual Collapsible-Panel UI** | Left = original game transcript. Right = AI narrator streaming in real time with colour-alternating blocks. |
| **Structured-Output Pipeline** | `completions.py` injects `config/response_schema.json` (AI schema) into prompts, while heuristics modules target `config/game_engine_schema.json` for engine parsing, keeping LLM + engine responsibilities separate. |
| **Config Toggles** | `config.json` controls model prompt, token limits, and `stream_only_narration` switch. |

---

## Getting Started

```bash

```


---

## Playing the Game

### Basic Parser Commands
CLASSIC TEXT ADVENTURE HOW_TO_PLAY

---

## Architecture & Configuration
```
├─    # Builds prompts, injects schema, parses LLM JSON
├─    # Orchestrates UI ↔︎ completion service
├─    # Rich TUI (game left, AI right)
├─    # Canonical entry/exit points for printing & input; hooks for AI calls
├─ config/response_schema.json    # Strict schema enforced on every AI reply (AI engine)
├─ config/game_engine_schema.json # Canonical schema for deterministic parser heuristics
├─ config/config.json             # System prompt template & runtime flags
└─ log/ai.jsonl            # Every request/response for analysis
```

### LLM Layer (event-driven, non-blocking)

- Engine turns feed the heuristics layer first, ensuring `GameMemoryStore` records the authoritative scene and action records before any LLM work begins.
- Once a turn is committed, two background jobs are enqueued: (1) Memory Enrichment jobs keyed to that turn and (2) Narration jobs keyed to the turn, player commands, or idle timing events. Both workers operate asynchronously and independently of the main loop so the UI never waits for them.
- Bounded queues, drop/skip policies, and cancellation rules keep backpressure manageable; if newer turns arrive before a job completes, late results are either ignored or tagged as advisory, never blocking gameplay.
- Narration might stream chunks as they are produced, but the game loop continues to accept commands while narration remains in-flight. Memory enrichment updates are advisory annotations and do not overwrite canonical facts without explicit reconciliation.

### Triggering & Queueing

- **Turn trigger:** Every completed engine turn enqueues enrichment and narration jobs with the turn identifier so UI/outcomes can correlate results later.
- **Player trigger:** Player commands can explicitly prompt narration generation (e.g., when requesting a recap) without waiting for enrichment jobs to finish.
- **Idle trigger:** When the player is idle beyond a configured threshold, the narration scheduler may enqueue ambient commentary or reminders. All idle jobs also share the same non-blocking guarantees.

The architecture emphasizes that the UI renders engine output immediately and only logs/enriches later; the system’s observability (JSONL logs, heuristics) ensures auditors can replay the flow even when LLM work arrives out of order.

---

## Bugs and Bugfixes


---

## TODO

---

## Credits & License

zmachine-api Rest-API Docker Wrapper: `https://github.com/opendns/zmachine-api/blob/master/README.md`

Code in this repository is MIT-licensed; see `LICENSE`.