# previous, failed implementation of game TUI
"""Rich/Textual TUI for IF AI Buddy."""
from __future__ import annotations

import re
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Footer, Header, Input, Static, Log

from module.game_controller import GameController, TurnResult


class TurnCompleted(Message):
    def __init__(self, result: TurnResult) -> None:
        self.result = result
        super().__init__()


class StatusBar(Static):
    def compose(self) -> ComposeResult:  # type: ignore[override]
        with Horizontal(id="status-strip"):
            yield Button(
                "Player: --",
                id="status-player",
                classes="status-box status-clickable",
            )
            yield Static("Room: --", id="status-room", classes="status-box")
            yield Static("Moves: 0", id="status-moves", classes="status-box")
            yield Static("Score: 0", id="status-score", classes="status-box")
            yield Static("Engine: Idle", id="status-engine", classes="status-box")
            yield Static("AI: Offline", id="status-ai", classes="status-box")
            yield Static("Palette: --", id="status-palette", classes="status-box")

    def update_values(self, data: dict[str, str]) -> None:
        for key, value in data.items():
            try:
                widget = self.query_one(f"#status-{key}")
            except Exception:  # pragma: no cover - defensive
                continue
            target: Button | Static | None = None
            if isinstance(widget, Button):
                widget.label = value
                target = widget
            elif isinstance(widget, Static):
                widget.update(value)
                target = widget
            if target is not None:
                self._apply_status_style(target, value)

    @staticmethod
    def _status_class(value: str) -> str | None:
        lowered = value.lower()
        if any(keyword in lowered for keyword in ("error", "offline", "failed")):
            return "status-error"
        if any(keyword in lowered for keyword in ("busy", "working", "starting")):
            return "status-busy"
        if any(keyword in lowered for keyword in ("ready", "idle", "online")):
            return "status-ok"
        return None

    def _apply_status_style(self, widget: Static | Button, value: str) -> None:
        for css_class in ("status-ok", "status-busy", "status-error"):
            widget.remove_class(css_class)
        css = self._status_class(value)
        if css:
            widget.add_class(css)


class GameApp(App):
    CSS = """
    Screen {
        align: center middle;
    }
    #content {
        height: 1fr;
        width: 100%;
    }
    #main-columns {
        height: 1fr;
    }
    TextLog {
        border: round $primary;
    }
    #transcript, #narration {
        width: 1fr;
        height: 1fr;
    }
    #status-message {
        min-height: 2;
        padding: 0 1;
        border: tall $surface;
    }
    #input-row {
        height: 3;
        border-top: round $surface;
        padding-top: 1;
    }
    Input#command-input {
        width: 2fr;
    }
    StatusBar {
        width: 1fr;
    }
    #status-strip {
        width: 100%;
        padding: 0 1;
        height: auto;
        border: round $surface;
        background: $panel;
    }
    .status-box {
        padding: 0 1;
        border: round $accent-darken-1;
        margin: 0 1;
    }
    .status-clickable {
        background: $accent;
    }
    .status-ok {
        background: $success-darken-1;
    }
    .status-busy {
        background: $warning-darken-1;
    }
    .status-error {
        background: $error;
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
        self.status_bar: StatusBar | None = None
        self._command_placeholder = "Enter command…"
        self.status_data = {
            "ai": "AI: Idle",
            "engine": "Engine: Idle",
            "room": "Room: --",
            "player": "Player: --",
            "moves": "Moves: 0",
            "score": "Score: 0",
            "palette": "Palette: ^P palette",
        }
        self.busy = False
        self.awaiting_player_name = False

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Header()
        with Vertical(id="content"):
            with Horizontal(id="main-columns"):
                self.transcript_log = Log(highlight=True, id="transcript")
                self.narration_log = Log(highlight=True, id="narration")
                yield self.transcript_log
                yield self.narration_log
            self.status_widget = Static("Ready", id="status-message")
            yield self.status_widget
            with Horizontal(id="input-row"):
                self.command_input = Input(placeholder=self._command_placeholder, id="command-input")
                yield self.command_input
                self.status_bar = StatusBar()
                yield self.status_bar
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
        self._initialize_status_bar()

    async def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        command = event.value.strip()
        event.input.value = ""
        if self.awaiting_player_name:
            self.awaiting_player_name = False
            self._restore_command_placeholder()
            if not command:
                self._set_status("Player rename cancelled")
                return
            self._set_status("Restarting session…")
            self.run_worker(self._handle_player_rename(command), exclusive=True)
            return
        if not command:
            return
        self._set_status("Working…")
        self.run_worker(self._handle_command(command), exclusive=True)

    async def _handle_command(self, command: str) -> None:
        self._update_engine_status("Engine: Busy")
        self._update_ai_status("AI: Working")
        result = await self.controller.play_turn(command)
        await self._deliver_result(result)

    async def _deliver_result(self, result: TurnResult) -> None:
        if result.transcript and self.transcript_log:
            self.transcript_log.write(f"\n> {result.command}\n{result.transcript}")
            self._update_room_name(result.transcript)
            self._update_score_moves(result.transcript)
        if result.narration and self.narration_log:
            self.narration_log.write(f"\n{result.narration}")
            self._update_ai_status("AI: Ready")
        elif not result.narration:
            self._update_ai_status("AI: Idle")
        if result.error:
            self._set_status(f"Error: {result.error}")
            self._update_engine_status("Engine: Error")
            self._update_ai_status("AI: Error")
        else:
            latency = result.diagnostics.get("latency_ms") if result.diagnostics else None
            if latency is not None:
                self._set_status(f"Done in {latency:.0f} ms")
            else:
                self._set_status("Done")
            self._update_engine_status("Engine: Ready")
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

    def _initialize_status_bar(self) -> None:
        room_name = getattr(self.controller, "game_name", "--")
        player_name = getattr(self.controller, "player_name", "--")
        self.status_data.update(
            {
                "room": f"Room: {room_name}",
                "player": f"Player: {player_name}",
                "engine": "Engine: Ready",
                "ai": "AI: Idle",
                "moves": "Moves: 0",
                "score": "Score: 0",
            }
        )
        self._refresh_status_bar()

    def _update_engine_status(self, status: str) -> None:
        self.status_data["engine"] = status
        self._refresh_status_bar()

    def _update_ai_status(self, status: str) -> None:
        self.status_data["ai"] = status
        self._refresh_status_bar()

    def _update_score_moves(self, transcript: str) -> None:
        match = re.search(r"Score:\s*(\d+)\s+Moves:\s*(\d+)", transcript)
        if not match:
            return
        score, moves = match.groups()
        self.status_data["score"] = f"Score: {score}"
        self.status_data["moves"] = f"Moves: {moves}"
        self._refresh_status_bar()

    def _update_room_name(self, transcript: str) -> None:
        for line in transcript.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("Score:"):
                continue
            self.status_data["room"] = f"Room: {text}"
            self._refresh_status_bar()
            break

    def _refresh_status_bar(self) -> None:
        if self.status_bar:
            self.status_bar.update_values(self.status_data)

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        if event.button.id == "status-player":
            self._prompt_player_rename()

    def _prompt_player_rename(self) -> None:
        self.awaiting_player_name = True
        self._set_status("Enter a new player name and press Enter to restart the game.")
        if self.command_input:
            self.command_input.placeholder = "Enter player name…"
            self.command_input.value = ""
            self.set_focus(self.command_input)

    def _restore_command_placeholder(self) -> None:
        if self.command_input:
            self.command_input.placeholder = self._command_placeholder

    async def _handle_player_rename(self, new_name: str) -> None:
        try:
            intro = await self.controller.restart(new_name)
        except Exception as exc:  # pragma: no cover - UI surface
            self._set_status(f"Restart failed: {exc}")
            return
        if self.transcript_log:
            if hasattr(self.transcript_log, "clear"):
                self.transcript_log.clear()
            self.transcript_log.write(intro)
        if self.narration_log and hasattr(self.narration_log, "clear"):
            self.narration_log.clear()
        self._initialize_status_bar()
        self._update_room_name(intro)
        self.status_data["player"] = f"Player: {self.controller.player_name}"
        self.status_data["moves"] = "Moves: 0"
        self.status_data["score"] = "Score: 0"
        self._refresh_status_bar()
        self._set_status("Session restarted with new player")
        self.set_focus(self.command_input)


__all__ = ["GameApp"]
