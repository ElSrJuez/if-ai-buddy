"""Rich/Textual TUI for IF AI Buddy."""
from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input, Static, Log

from module.game_controller import GameController, TurnResult


class TurnCompleted(Message):
    def __init__(self, result: TurnResult) -> None:
        self.result = result
        super().__init__()


class GameApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    #content {
        height: 1fr;
        width: 100%;
    }
    TextLog {
        border: round $primary;
    }
    #transcript {
        width: 1fr;
        height: 1fr;
    }
    #narration {
        width: 1fr;
        height: 1fr;
    }
    #input-row {
        width: 100%;
    }
    #status {
        height: 3;
    }
    """

    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, controller: GameController) -> None:
        super().__init__()
        self.controller = controller
        self.transcript_log: Log | None = None
        self.narration_log: Log | None = None
        self.command_input: Input | None = None
        self.status_widget: Static | None = None
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="content"):
            with Horizontal():
                self.transcript_log = Log(highlight=True, id="transcript")
                self.narration_log = Log(highlight=True, id="narration")
                yield self.transcript_log
                yield self.narration_log
            self.command_input = Input(placeholder="Enter command…", id="command-input")
            yield self.command_input
            self.status_widget = Static("Ready", id="status")
            yield self.status_widget
        yield Footer()

    async def on_mount(self) -> None:
        self.set_focus(self.command_input)
        await self._bootstrap()

    async def _bootstrap(self) -> None:
        self._set_status("Starting session…")
        try:
            transcript = await self.controller.bootstrap()
        except Exception as exc:  # pragma: no cover - UI surface
            self._set_status(f"Failed to start session: {exc}")
            return
        if transcript and self.transcript_log:
            self.transcript_log.write(transcript)
        self._set_status("Session ready")

    async def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        command = event.value.strip()
        event.input.value = ""
        if not command:
            return
        self._set_status("Working…")
        self.run_worker(self._handle_command(command), exclusive=True)

    async def _handle_command(self, command: str) -> None:
        result = await self.controller.play_turn(command)
        await self._deliver_result(result)

    async def _deliver_result(self, result: TurnResult) -> None:
        if result.transcript and self.transcript_log:
            self.transcript_log.write(f"\n> {result.command}\n{result.transcript}")
        if result.narration and self.narration_log:
            self.narration_log.write(f"\n{result.narration}")
        if result.error:
            self._set_status(f"Error: {result.error}")
        else:
            latency = result.diagnostics.get("latency_ms") if result.diagnostics else None
            if latency is not None:
                self._set_status(f"Done in {latency:.0f} ms")
            else:
                self._set_status("Done")
        if result.should_exit:
            await self._shutdown_controller()
            self.exit()

    async def on_shutdown_request(self) -> None:
        await self._shutdown_controller()

    async def on_shutdown(self) -> None:
        await self._shutdown_controller()

    async def _shutdown_controller(self) -> None:
        await self.controller.shutdown()

    def _set_status(self, message: str) -> None:
        if self.status_widget:
            self.status_widget.update(message)


__all__ = ["GameApp"]
