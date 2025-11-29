"""Textual TUI for IF AI Buddy — two-column layout with game transcript and narration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import (
    Header,
    Footer,
    Input,
    RichLog,
    Static,
)
from textual.reactive import reactive


class AIStatus(Enum):
    """AI companion status."""

    IDLE = "Idle"
    WORKING = "Working"
    READY = "Ready"
    ERROR = "Error"


class EngineStatus(Enum):
    """Game engine status."""

    IDLE = "Idle"
    BUSY = "Busy"
    READY = "Ready"
    ERROR = "Error"


@dataclass(frozen=True)
class StatusSnapshot:
    """Immutable snapshot of game and AI status."""

    player: str
    game: str
    room: str = "Unknown"
    moves: int = 0
    score: int = 0
    engine_status: EngineStatus = EngineStatus.IDLE
    ai_status: AIStatus = AIStatus.IDLE

    @classmethod
    def default(cls, player: str, game: str) -> StatusSnapshot:
        return cls(player=player, game=game)

    def with_updates(
        self,
        player: str | None = None,
        game: str | None = None,
        room: str | None = None,
        moves: int | None = None,
        score: int | None = None,
        engine_status: EngineStatus | None = None,
        ai_status: AIStatus | None = None,
    ) -> StatusSnapshot:
        """Return a new snapshot with updated fields."""
        return StatusSnapshot(
            player=player if player is not None else self.player,
            game=game if game is not None else self.game,
            room=room if room is not None else self.room,
            moves=moves if moves is not None else self.moves,
            score=score if score is not None else self.score,
            engine_status=engine_status if engine_status is not None else self.engine_status,
            ai_status=ai_status if ai_status is not None else self.ai_status,
        )


class TranscriptLog(Static):
    """Left column: scrollable game transcript."""

    DEFAULT_CSS = """
    TranscriptLog {
        height: 1fr;
        border: solid $primary;
        overflow-y: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._log = RichLog(markup=True, highlight=False)

    def compose(self) -> ComposeResult:
        yield self._log

    def add_output(self, text: str) -> None:
        """Add text to the transcript log."""
        self._log.write(text)

    def reset(self) -> None:
        """Clear all transcript content."""
        self._log.clear()


class NarrationPanel(Static):
    """Right column: AI narration and future tabs."""

    DEFAULT_CSS = """
    NarrationPanel {
        height: 1fr;
        border: solid $secondary;
        overflow-y: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._narration_log = RichLog(markup=True, highlight=False)

    def compose(self) -> ComposeResult:
        yield self._narration_log

    def add_narration(self, text: str) -> None:
        """Add narration to the panel."""
        self._narration_log.write(text)

    def add_hint(self, text: str) -> None:
        """Add a hint or guidance line."""
        self._narration_log.write(f"[dim]{text}[/dim]")

    def reset(self) -> None:
        """Clear all narration content."""
        self._narration_log.clear()


class StatusBar(Static):
    """Footer status bar showing player, game, room, moves, score, and status."""

    DEFAULT_CSS = """
    StatusBar {
        height: auto;
        border-top: solid $primary;
        background: $surface;
        padding: 0 1;
    }
    """

    status: reactive[StatusSnapshot] = reactive(
        StatusSnapshot.default("Adventurer", "Unknown")
    )

    def __init__(self) -> None:
        super().__init__()
        self.on_player_click: Callable[[], None] | None = None

    def render(self) -> RenderableType:
        """Render the status bar with current values."""
        s = self.status
        engine_color = self._status_color(s.engine_status)
        ai_color = self._status_color(s.ai_status)
        return (
            f"[bold]{s.player}[/bold] | "
            f"Game: {s.game} | "
            f"Room: {s.room} | "
            f"Moves: {s.moves} Score: {s.score} | "
            f"[{engine_color}]Engine: {s.engine_status.value}[/{engine_color}] | "
            f"[{ai_color}]AI: {s.ai_status.value}[/{ai_color}]"
        )

    def _status_color(self, status: EngineStatus | AIStatus) -> str:
        """Return color code for a status enum."""
        if isinstance(status, EngineStatus):
            if status == EngineStatus.ERROR:
                return "red"
            elif status == EngineStatus.BUSY:
                return "blue"
            elif status == EngineStatus.READY:
                return "green"
            else:
                return "dim"
        else:  # AIStatus
            if status == AIStatus.ERROR:
                return "red"
            elif status == AIStatus.WORKING:
                return "blue"
            elif status == AIStatus.READY:
                return "green"
            else:
                return "dim"

    def update_status(self, snapshot: StatusSnapshot) -> None:
        """Update the status snapshot and trigger re-render."""
        self.status = snapshot


class CommandInput(Static):
    """Footer input field for player commands."""

    DEFAULT_CSS = """
    CommandInput {
        height: auto;
        border-top: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self, on_submit: Callable[[str], None]) -> None:
        super().__init__()
        self.on_submit = on_submit
        self._input: Input | None = None

    def compose(self) -> ComposeResult:
        self._input = Input(id="command_input", placeholder="Enter command...")
        yield self._input

    def on_mount(self) -> None:
        """Focus the input field on mount."""
        if self._input:
            self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission."""
        command = event.value.strip()
        if command and self._input:
            self.on_submit(command)
            self._input.value = ""
            self._input.focus()


class IFBuddyTUI:
    """Wraps a Textual app instance with game-specific methods."""

    def __init__(
        self,
        app,
        initial_status: StatusSnapshot,
        on_command: Callable[[str], None],
        on_player_rename: Callable[[], None],
        on_restart: Callable[[], None],
    ) -> None:
        self._app = app
        self._status = initial_status
        self._on_command = on_command
        self._on_player_rename = on_player_rename
        self._on_restart = on_restart

        # Widgets will be set up by the app
        self.transcript_log: TranscriptLog | None = None
        self.narration_panel: NarrationPanel | None = None
        self.status_bar: StatusBar | None = None
        self.command_input: CommandInput | None = None

    def add_transcript_output(self, text: str) -> None:
        """Add text to the game transcript (left column)."""
        if self.transcript_log:
            self.transcript_log.add_output(text)

    def add_narration(self, text: str) -> None:
        """Add narration to the right panel."""
        if self.narration_panel:
            self.narration_panel.add_narration(text)

    def add_hint(self, text: str) -> None:
        """Add a hint/guidance to the narration panel."""
        if self.narration_panel:
            self.narration_panel.add_hint(text)

    def reset_transcript(self) -> None:
        """Clear the game transcript."""
        if self.transcript_log:
            self.transcript_log.reset()

    def reset_narration(self) -> None:
        """Clear the narration panel."""
        if self.narration_panel:
            self.narration_panel.reset()

    def update_status(
        self,
        player: str | None = None,
        game: str | None = None,
        room: str | None = None,
        moves: int | None = None,
        score: int | None = None,
    ) -> None:
        """Update status fields and re-render."""
        self._status = self._status.with_updates(
            player=player, game=game, room=room, moves=moves, score=score
        )
        if self.status_bar:
            self.status_bar.update_status(self._status)

    def set_engine_status(self, status: EngineStatus) -> None:
        """Update engine status."""
        self._status = self._status.with_updates(engine_status=status)
        if self.status_bar:
            self.status_bar.update_status(self._status)

    def set_ai_status(self, status: AIStatus) -> None:
        """Update AI status."""
        self._status = self._status.with_updates(ai_status=status)
        if self.status_bar:
            self.status_bar.update_status(self._status)

    def run(self) -> None:
        """Run the Textual app."""
        self._app.run()

    def call_later(self, callback: Callable[[], None]) -> None:
        """Schedule a callback to run on the next event loop iteration."""
        self._app.call_later(callback)

    def run_worker_async(self, coro):
        """Schedule an async coroutine to run on the Textual event loop."""
        return self._app.call_later(lambda: asyncio.create_task(coro))


class IFBuddyApp(App):
    """Textual App for IF AI Buddy."""

    TITLE = "IF AI Buddy"
    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #main_container {
        height: 1fr;
    }

    #columns {
        height: 1fr;
        layout: horizontal;
    }

    #left_column {
        width: 1fr;
    }

    #right_column {
        width: 1fr;
    }

    Footer {
        height: auto;
    }
    """

    def __init__(self, tui: IFBuddyTUI) -> None:
        super().__init__()
        self._tui = tui

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()

        with Container(id="main_container"):
            with Horizontal(id="columns"):
                left = TranscriptLog()
                left.id = "left_column"
                self._tui.transcript_log = left
                yield left

                right = NarrationPanel()
                right.id = "right_column"
                self._tui.narration_panel = right
                yield right

        # Status bar
        status = StatusBar()
        status.update_status(self._tui._status)
        self._tui.status_bar = status
        yield status

        # Command input
        cmd_input = CommandInput(on_submit=self._tui._on_command)
        self._tui.command_input = cmd_input
        yield cmd_input

        yield Footer()

    async def action_quit(self) -> None:
        """Quit the app."""
        self.exit()


def create_app(
    initial_status: StatusSnapshot,
    on_command: Callable[[str], None],
    on_player_rename: Callable[[], None],
    on_restart: Callable[[], None],
) -> IFBuddyTUI:
    """Factory function to create and wire up the TUI."""
    # Create the TUI wrapper
    tui = IFBuddyTUI(
        app=None,  # Will be set below
        initial_status=initial_status,
        on_command=on_command,
        on_player_rename=on_player_rename,
        on_restart=on_restart,
    )

    # Create the app and wire it to the TUI
    app = IFBuddyApp(tui)
    tui._app = app

    return tui


__all__ = [
    "AIStatus",
    "EngineStatus",
    "StatusSnapshot",
    "IFBuddyTUI",
    "create_app",
]
