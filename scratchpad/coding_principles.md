# Coding Principles & Lessons Learned

Throughout this project’s UI redesign iterations, we encountered a series of missteps—overly large patches, mixing concerns, hidden defaults, and broken builds—that have crystallized a set of guiding principles for sustainable, maintainable code.

---

## 1. Configuration-Driven Behavior
- **Never hard-code defaults in logic.** All parameters (API endpoints, game names, UI layout options) must live in `config.json` or environment variables.  
- **Fail fast if config is missing.** Reject startup early and loudly instead of silently falling back to in-code values.

## 2. No In-Code Fallbacks
- **Don’t embed fallback heuristics in business logic.** If a dependency or value is missing, surface it to the user or admin to correct.  
- **Eliminate `try`/`except` silence.** Catch and rethrow with clear context rather than hiding errors.

## 3. DRY & Separation of Concerns
- **Single responsibility per module.** UI rendering belongs in `ui_helper.py` (or `tui_app.py`), game logic in `game_controller.py`, config in `my_config.py`, and API calls in `game_api.py` / `rest_helper.py`.  
- **Thin entry point.** `main.py` only orchestrates wiring: load config, initialize logging, create controller, hand off to UI runner.  
- **Extract glue code.** Rather than littering `main.py` with UI minutiae, use a small `ui_runner.py` to adapt controller ↔ UI interactions.

## 4. Code Simplicity & Sustainability
- **Prefer minimal diffs.** Start with the smallest possible change to validate a new feature; expand only when proven working.  
- **Iterate incrementally.** Avoid 100+ line patches that are hard to review; break tasks into bite-sized commits.  
- **Readable over clever.** Explicit is better than implicit; a few more lines of clear code beats inscrutable one-liners.

## 5. Logging Strategy
- **Structured and consistent.** Use `my_logging` to capture debug-level REST requests, errors, and state transitions.  
- **Contextual messages.** Prefix logs with module/function names and include critical variables (e.g., `game_id`, `player_name`).  
- **Unobtrusive by default.** Log only warnings/errors in normal use; enable verbose/tracing only when debugging.

---

By adhering to these principles, we ensure any future UI overhaul or feature addition remains a clear, low-risk operation—no surprises, no hidden defaults, and a clean separation between configuration, logic, and presentation.