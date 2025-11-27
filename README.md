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
| **Structured-Output Pipeline** | `completions.py` injects `response_schema.json` into the prompt, requests strict JSON, logs every turn, and streams narration (or full JSON for debugging). |
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
├─ response_schema.json    # Strict schema enforced on every AI reply
├─ config.json             # System prompt template & runtime flags
└─ log/ai.jsonl            # Every request/response for analysis
```

---

## Bugs and Bugfixes


---

## TODO

---

## Credits & License

zmachine-api Rest-API Docker Wrapper: `https://github.com/opendns/zmachine-api/blob/master/README.md`

Code in this repository is MIT-licensed; see `LICENSE`.