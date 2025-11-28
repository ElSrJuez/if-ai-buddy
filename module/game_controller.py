"""Main loop orchestration for IF AI Buddy."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from module import my_logging
from module.completions_helper import CompletionsHelper, CompletionResult, CompletionError
from module.rest_helper import DfrotzClient, RestError, SessionHandle


@dataclass
class TurnResult:
    command: str
    transcript: str | None
    narration: str | None
    payload: dict[str, Any] | None
    diagnostics: dict[str, Any]
    error: str | None = None
    should_exit: bool = False


class GameController:
    def __init__(
        self,
        *,
        rest_client: DfrotzClient,
        completions: CompletionsHelper,
        game_name: str,
        session_label: str,
    ) -> None:
        self._rest = rest_client
        self._completions = completions
        self._game_name = game_name
        self._session_label = session_label
        self._session: SessionHandle | None = None
        self._transcript_buffer: list[str] = []
        self._lock = asyncio.Lock()

    async def bootstrap(self) -> str:
        async with self._lock:
            if self._session is None:
                handle, transcript = await self._rest.start_session(
                    self._game_name, self._session_label
                )
                self._session = handle
                transcript_text = str(transcript or "")
                if transcript_text:
                    self._transcript_buffer.append(transcript_text)
                    my_logging.game_log_json(
                        {
                            "event": "session_start",
                            "pid": handle.pid,
                            "transcript": transcript_text,
                        }
                    )
                    my_logging.log_player_output(transcript_text, pid=handle.pid)
            return self._transcript_buffer[-1] if self._transcript_buffer else ""

    async def play_turn(self, command: str) -> TurnResult:
        command = command.strip()
        if not command:
            return TurnResult(
                command=command,
                transcript=None,
                narration=None,
                payload=None,
                diagnostics={},
                error="Empty command",
            )

        if command.lower() in {"/quit", "quit"}:
            await self.shutdown()
            return TurnResult(
                command=command,
                transcript=None,
                narration="Session ended.",
                payload=None,
                diagnostics={},
                should_exit=True,
            )

        async with self._lock:
            session = await self._ensure_session()
            turn_diag: dict[str, Any] = {"pid": session.pid, "command": command}
            my_logging.log_player_input(command, pid=session.pid)
            transcript: str | None = None
            try:
                action_resp = await self._rest.submit_action(session.pid, command)
                transcript = str(action_resp.get("data", "") or "").strip()
                self._transcript_buffer.append(transcript)
                turn_diag["transcript_length"] = len(transcript)
                my_logging.log_player_output(transcript, pid=session.pid)
            except RestError as exc:
                my_logging.system_log(f"REST error: {exc}")
                return TurnResult(
                    command=command,
                    transcript=None,
                    narration=None,
                    payload=None,
                    diagnostics=turn_diag,
                    error=str(exc),
                )

            try:
                completion = await self._completions.run(transcript or "")
                narration = completion.payload.get("narration") if completion.payload else None
                result = TurnResult(
                    command=command,
                    transcript=transcript,
                    narration=narration,
                    payload=completion.payload,
                    diagnostics={
                        **turn_diag,
                        "latency_ms": completion.latency_ms,
                        "model": completion.model,
                        "provider": completion.provider,
                        "usage": completion.usage,
                    },
                )
                my_logging.game_log_json(
                    {
                        "pid": session.pid,
                        "command": command,
                        "transcript": transcript,
                        "narration": narration,
                        "payload": completion.payload,
                        "diagnostics": result.diagnostics,
                    }
                )
                return result
            except CompletionError as exc:
                my_logging.system_log(f"Completion error: {exc}")
                return TurnResult(
                    command=command,
                    transcript=transcript,
                    narration=None,
                    payload=None,
                    diagnostics=turn_diag,
                    error=str(exc),
                )

    async def shutdown(self) -> None:
        async with self._lock:
            if self._session is not None:
                try:
                    await self._rest.stop_session(self._session.pid)
                except RestError as exc:
                    my_logging.system_log(f"Failed to stop session: {exc}")
                self._session = None
            await self._rest.close()

    async def _ensure_session(self) -> SessionHandle:
        if self._session is None:
            handle, transcript = await self._rest.start_session(
                self._game_name, self._session_label
            )
            self._session = handle
            transcript_text = str(transcript or "")
            if transcript_text:
                self._transcript_buffer.append(transcript_text)
                my_logging.log_player_output(transcript_text, pid=handle.pid)
        return self._session


__all__ = ["GameController", "TurnResult"]
