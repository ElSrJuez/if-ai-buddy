# Minimal REST Helper — Notes Only

- Keep everything synchronous and blocking for now.
- Inputs: `base_url`, shared HTTP session (requests or httpx in sync mode).
- Exposed operations:
  1. `ping()` → GET `/` just to verify the emulator is alive.
  2. `start(game, label)` → POST `/games` returning `{ pid, data }`.
  3. `action(pid, text)` → POST `/games/{pid}/action` returning `{ pid, data }`.
  4. `stop(pid)` → DELETE `/games/{pid}`.
- Return raw JSON dictionaries; caller is responsible for parsing transcript text.
- Basic error handling: raise `RuntimeError` with status code + body when 4xx/5xx.
- Leave retries/timeouts to the shared HTTP session configuration.
