# IF AI Buddy — Roadmap / TODO

This project is intentionally **schema-first**, **config-driven**, and **observable-by-default** (see `scratchpad/01_objectives_and_meta.md`).

## v0.1 scope (current)

Shipped baseline capabilities:

- [x] Textual two-pane UI + status bar + command input (`module/ui_helper.py`)
- [x] dfrotz REST integration (`module/rest_helper.py`, `module/game_api.py`)
- [x] Canonical engine parsing (`module/game_engine_heuristics.py`)
- [x] TinyDB run memory (`module/game_memory.py`)
- [x] Prompt builder (`module/narration_job_builder.py`)
- [x] Streaming narration helper (`module/llm_narration_helper.py`)
- [x] JSONL logging for engine, completions, memory transactions (`module/my_logging.py`)

## v0.2 (next) — UX + lifecycle hardening

### UI / UX
- [ ] Alternating narration *blocks* (full-width, atomic across streaming)
- [ ] Right-pane tabs scaffolding (Items / Visited / Achievements / Todo) per `scratchpad/03_TUI_design.md`
- [ ] Command palette / quick actions stub (palette cell in footer)

### Controller lifecycle
- [ ] Enforce the Canonical Turn Lifecycle Contract (`scratchpad/06_game_controller.md`)
  - [ ] Treat start transcript as turn 0 end-to-end (parse → record → context → narration)
  - [ ] Add explicit memory transaction envelope events (begin/end per turn)
  - [ ] Add regression tests for ordering (memory updated before LLM call)
- [ ] Player rename: force full engine restart so logs/memory never straddle identities

### Observability
- [ ] Add a single “session summary” log event at startup with resolved config + schema paths
- [ ] Emit structured “job dropped / job stale / job cancelled” narration events

## v0.3 (later) — tests, correctness, and polish

### Testing
- [ ] Unit tests for engine heuristics (room, score/moves, inventory, visible items)
- [ ] Golden tests for narration prompt rendering (prompt snapshots)

### Config + docs
- [ ] Add `schemas/` examples and document schema-first parsing contract
- [ ] Review config keys for dead fields and either implement or remove them

## Known pain points (tracked)

- LLM “looping” / repetition spirals can still happen depending on model + settings.
- Some UI polish is still WIP; focus remains on correctness and observability first.