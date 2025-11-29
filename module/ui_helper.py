"""
IF AI Buddy TUI Helper Module

A self-initializing, non-blocking Textual-based TUI for AI-enhanced interactive fiction.
Provides a two-column layout with game transcript and AI companion commentary,
integrated status bar, and extensible tab system.

Key Features:
- Two-column layout: left (game transcript), right (AI narration + future tabs)
- Persistent footer with command input and multi-widget status bar
- Non-blocking design with clear separation of concerns
- Modular widget system for easy extension
- Status tracking for engine and AI states
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header, Footer, Input, Label, RichLog, Static, 
    TabbedContent, TabPane, Tree, DataTable, Button
)
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.panel import Panel
from enum import Enum
from typing import Optional, Callable, Dict, Any
from datetime import datetime


# =============================================================================
# Status Enums
# =============================================================================

class EngineStatus(Enum):
    """Game engine operational states"""
    READY = ("Ready", "status-ok")
    BUSY = ("Busy", "status-busy")
    ERROR = ("Error", "status-error")
    DISCONNECTED = ("Disconnected", "status-error")


class AIStatus(Enum):
    """AI companion operational states"""
    IDLE = ("Idle", "status-idle")
    WORKING = ("Working", "status-busy")
    READY = ("Ready", "status-ok")
    ERROR = ("Error", "status-error")


# =============================================================================
# Custom Messages
# =============================================================================

class CommandSubmitted(Message):
    """Emitted when user submits a command"""
    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__()


class PlayerNameClicked(Message):
    """Emitted when player name button is clicked"""
    pass


class StatusUpdate(Message):
    """Generic status update message"""
    def __init__(self, component: str, **kwargs) -> None:
        self.component = component
        self.data = kwargs
        super().__init__()


# =============================================================================
# Status Bar Widgets
# =============================================================================

class StatusCell(Static):
    """Individual status bar cell with semantic coloring"""
    
    def __init__(self, label: str, value: str = "", classes: str = "") -> None:
        super().__init__(classes=f"status-cell {classes}")
        self.label_text = label
        self.value_text = value
    
    def on_mount(self) -> None:
        self.update_display()
    
    def update_display(self) -> None:
        """Refresh the displayed content"""
        self.update(f"[bold]{self.label_text}:[/bold] {self.value_text}")
    
    def set_value(self, value: str, status_class: str = "") -> None:
        """Update value and optionally change status class"""
        self.value_text = value
        if status_class:
            self.remove_class("status-ok", "status-busy", "status-error", "status-idle")
            self.add_class(status_class)
        self.update_display()


class PlayerButton(Button):
    """Clickable player name button"""
    
    def __init__(self, name: str = "Player") -> None:
        super().__init__(f"👤 {name}", id="player-button", classes="status-button")
        self.player_name = name
    
    def set_name(self, name: str) -> None:
        """Update player name"""
        self.player_name = name
        self.label = f"👤 {name}"
    
    def on_button_pressed(self) -> None:
        self.post_message(PlayerNameClicked())


class StatusBar(Horizontal):
    """Composite status bar with multiple info cells"""
    
    def __init__(self) -> None:
        super().__init__(id="status-bar", classes="status-bar")
        self.player_btn: Optional[PlayerButton] = None
        self.cells: Dict[str, StatusCell] = {}
    
    def compose(self) -> ComposeResult:
        """Build status bar components"""
        self.player_btn = PlayerButton()
        yield self.player_btn
        
        # Create status cells
        self.cells["room"] = StatusCell("Room", "Unknown")
        self.cells["moves"] = StatusCell("Moves", "0")
        self.cells["score"] = StatusCell("Score", "0")
        self.cells["engine"] = StatusCell("Engine", "Ready", "status-ok")
        self.cells["ai"] = StatusCell("AI", "Idle", "status-idle")
        
        for cell in self.cells.values():
            yield cell
    
    def update_status(self, component: str, value: str, status_class: str = "") -> None:
        """Update a specific status cell"""
        if component == "player" and self.player_btn:
            self.player_btn.set_name(value)
        elif component in self.cells:
            self.cells[component].set_value(value, status_class)
    
    def set_engine_status(self, status: EngineStatus) -> None:
        """Update engine status with enum"""
        text, css_class = status.value
        self.update_status("engine", text, css_class)
    
    def set_ai_status(self, status: AIStatus) -> None:
        """Update AI status with enum"""
        text, css_class = status.value
        self.update_status("ai", text, css_class)


# =============================================================================
# Main Content Widgets
# =============================================================================

class TranscriptLog(RichLog):
    """Left column: scrolling game transcript"""
    
    def __init__(self) -> None:
        super().__init__(
            id="transcript-log",
            classes="transcript-log",
            highlight=False,
            markup=True,
            wrap=True,
            auto_scroll=True
        )
    
    def add_command(self, command: str, timestamp: Optional[datetime] = None) -> None:
        """Add a player command to the transcript"""
        ts = timestamp or datetime.now()
        time_str = ts.strftime("%H:%M:%S")
        self.write(f"[dim]{time_str}[/dim] [bold cyan]>[/bold cyan] {command}")
    
    def add_output(self, text: str, timestamp: Optional[datetime] = None) -> None:
        """Add game engine output to the transcript"""
        ts = timestamp or datetime.now()
        time_str = ts.strftime("%H:%M:%S")
        self.write(f"[dim]{time_str}[/dim] {text}")
    
    def add_error(self, error: str, timestamp: Optional[datetime] = None) -> None:
        """Add error message to the transcript"""
        ts = timestamp or datetime.now()
        time_str = ts.strftime("%H:%M:%S")
        self.write(f"[dim]{time_str}[/dim] [bold red]ERROR:[/bold red] {error}")
    
    def clear_transcript(self) -> None:
        """Clear the transcript log"""
        self.clear()


class NarrationLog(RichLog):
    """AI companion narration display"""
    
    def __init__(self) -> None:
        super().__init__(
            id="narration-log",
            classes="narration-log",
            highlight=False,
            markup=True,
            wrap=True,
            auto_scroll=True
        )
    
    def add_narration(self, text: str, timestamp: Optional[datetime] = None) -> None:
        """Add AI narration chunk"""
        ts = timestamp or datetime.now()
        time_str = ts.strftime("%H:%M:%S")
        self.write(f"[dim]{time_str}[/dim] [italic]{text}[/italic]")
    
    def add_hint(self, text: str) -> None:
        """Add a gameplay hint"""
        self.write(f"[bold yellow]💡 Hint:[/bold yellow] {text}")
    
    def add_separator(self) -> None:
        """Add visual separator between narration blocks"""
        self.write("[dim]" + "─" * 40 + "[/dim]")
    
    def clear_narration(self) -> None:
        """Clear the narration log"""
        self.clear()


class ItemsTreeWidget(VerticalScroll):
    """Placeholder: Items tree viewer (Player Inventory, World, Destroyed)"""
    
    def __init__(self) -> None:
        super().__init__(id="items-tree", classes="items-tree")
        self.items_tree: Optional[Tree] = None
    
    def compose(self) -> ComposeResult:
        self.items_tree = Tree("Items", id="items-tree-root")
        self.items_tree.root.expand()
        
        # Scaffold structure
        inventory = self.items_tree.root.add("📦 Player Inventory", expand=True)
        world = self.items_tree.root.add("🌍 World Items", expand=True)
        destroyed = self.items_tree.root.add("💥 Destroyed/Used", expand=True)
        
        # Placeholder items
        inventory.add_leaf("🔑 Rusty Key")
        world.add_leaf("🗡️ Sword (Hall)")
        destroyed.add_leaf("🧪 Health Potion")
        
        yield self.items_tree


class RoomsListWidget(VerticalScroll):
    """Placeholder: Visited rooms list"""
    
    def __init__(self) -> None:
        super().__init__(id="rooms-list", classes="rooms-list")
    
    def compose(self) -> ComposeResult:
        yield Label("📍 Visited Rooms (by recency)", classes="section-header")
        yield Label("1. Great Hall [entered via: north]", classes="room-entry")
        yield Label("2. Dark Corridor [entered via: east]", classes="room-entry")
        yield Label("3. Starting Room [entered via: --]", classes="room-entry")


class AchievementsWidget(VerticalScroll):
    """Placeholder: Achievements list"""
    
    def __init__(self) -> None:
        super().__init__(id="achievements", classes="achievements")
    
    def compose(self) -> ComposeResult:
        yield Label("🏆 Achievements", classes="section-header")
        yield Label("✓ First Steps - Explored 3 rooms", classes="achievement")
        yield Label("✓ Collector - Picked up 5 items", classes="achievement")


class TodoWidget(VerticalScroll):
    """Placeholder: Todo/suggestions list"""
    
    def __init__(self) -> None:
        super().__init__(id="todo-list", classes="todo-list")
    
    def compose(self) -> ComposeResult:
        yield Label("📝 Suggested Actions", classes="section-header")
        yield Label("• Examine the locked door", classes="todo-item")
        yield Label("• Try using the rusty key", classes="todo-item")
        yield Label("• Return to the Great Hall", classes="todo-item")


class LogViewerWidget(VerticalScroll):
    """Placeholder: Low-level log file viewer"""
    
    def __init__(self) -> None:
        super().__init__(id="log-viewer", classes="log-viewer")
        self.log_display = RichLog(highlight=True, markup=True, wrap=False)
    
    def compose(self) -> ComposeResult:
        yield Label("📄 Debug Logs", classes="section-header")
        yield self.log_display
    
    def on_mount(self) -> None:
        # Sample log entries
        self.log_display.write('[{"event": "command", "text": "north", "ts": "12:34:56"}]')
        self.log_display.write('[{"event": "response", "lines": 3, "ts": "12:34:57"}]')


# =============================================================================
# Main Application
# =============================================================================

class IFBuddyTUI(App):
    """
    Main Textual application for IF AI Buddy.
    
    Public API for game integration:
    - add_command(cmd: str) - Add player command to transcript
    - add_output(text: str) - Add game output to transcript
    - add_narration(text: str) - Add AI narration
    - add_hint(hint: str) - Add AI hint
    - set_engine_status(status: EngineStatus) - Update engine status
    - set_ai_status(status: AIStatus) - Update AI status
    - update_game_state(room, moves, score) - Update game statistics
    - clear_transcript() - Clear game transcript
    - clear_narration() - Clear AI narration
    """
    
    CSS = """
    /* Global Styles */
    Screen {
        background: $surface;
    }
    
    /* Two-column layout */
    #main-container {
        height: 1fr;
    }
    
    #left-column {
        width: 50%;
        border-right: solid $primary;
    }
    
    #right-column {
        width: 50%;
    }
    
    /* Transcript styling */
    .transcript-log {
        border: solid $primary;
        height: 100%;
        padding: 1;
    }
    
    /* Narration styling */
    .narration-log {
        border: solid $accent;
        height: 100%;
        padding: 1;
    }
    
    /* Footer input + status */
    #footer-container {
        height: auto;
        background: $surface-darken-1;
        padding: 1;
    }
    
    #command-input {
        width: 2fr;
        margin-right: 1;
    }
    
    #status-bar {
        width: 3fr;
        align: right middle;
    }
    
    .status-cell {
        margin-left: 2;
        padding: 0 1;
    }
    
    .status-ok {
        color: $success;
    }
    
    .status-busy {
        color: $warning;
    }
    
    .status-error {
        color: $error;
    }
    
    .status-idle {
        color: $text-muted;
    }
    
    .status-button {
        margin-right: 2;
    }
    
    /* Tab content */
    TabbedContent {
        height: 100%;
    }
    
    TabPane {
        padding: 1;
    }
    
    .section-header {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    .room-entry, .achievement, .todo-item {
        margin-left: 2;
        margin-bottom: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "clear_transcript", "Clear Transcript"),
        Binding("ctrl+n", "clear_narration", "Clear Narration"),
        Binding("ctrl+r", "restart", "Restart Game"),
    ]
    
    TITLE = "IF AI Buddy"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Widget references
        self.transcript: Optional[TranscriptLog] = None
        self.narration: Optional[NarrationLog] = None
        self.status_bar: Optional[StatusBar] = None
        self.command_input: Optional[Input] = None
        
        # Callback registry
        self.on_command_callback: Optional[Callable[[str], None]] = None
        self.on_player_rename_callback: Optional[Callable[[], None]] = None
        self.on_restart_callback: Optional[Callable[[], None]] = None
    
    def compose(self) -> ComposeResult:
        """Build the TUI layout"""
        yield Header(show_clock=True)
        
        # Main two-column layout
        with Container(id="main-container"):
            with Horizontal():
                # Left: Game transcript
                with Vertical(id="left-column"):
                    self.transcript = TranscriptLog()
                    yield self.transcript
                
                # Right: Tabbed content (Narration + future tabs)
                with Vertical(id="right-column"):
                    with TabbedContent(id="right-tabs"):
                        with TabPane("Narration", id="tab-narration"):
                            self.narration = NarrationLog()
                            yield self.narration
                        
                        with TabPane("Items", id="tab-items"):
                            yield ItemsTreeWidget()
                        
                        with TabPane("Rooms", id="tab-rooms"):
                            yield RoomsListWidget()
                        
                        with TabPane("Achievements", id="tab-achievements"):
                            yield AchievementsWidget()
                        
                        with TabPane("Todo", id="tab-todo"):
                            yield TodoWidget()
                        
                        with TabPane("Logs", id="tab-logs"):
                            yield LogViewerWidget()
        
        # Footer: Command input + Status bar
        with Horizontal(id="footer-container"):
            self.command_input = Input(
                placeholder="Enter command...",
                id="command-input"
            )
            yield self.command_input
            
            self.status_bar = StatusBar()
            yield self.status_bar
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize after widgets are mounted"""
        if self.command_input:
            self.command_input.focus()
        
        # Add welcome message
        if self.narration:
            self.narration.add_narration(
                "Welcome to IF AI Buddy! I'll be your companion on this adventure. "
                "Type commands in the input below, and I'll provide context and guidance."
            )
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission"""
        command = event.value.strip()
        if not command:
            return
        
        # Clear input
        if self.command_input:
            self.command_input.value = ""
        
        # Add to transcript
        if self.transcript:
            self.transcript.add_command(command)
        
        # Post message for game logic
        self.post_message(CommandSubmitted(command))
        
        # Invoke callback if registered
        if self.on_command_callback:
            self.on_command_callback(command)
    
    def on_player_name_clicked(self, message: PlayerNameClicked) -> None:
        """Handle player name button click"""
        if self.on_player_rename_callback:
            self.on_player_rename_callback()
    
    # =========================================================================
    # Public API for Game Integration
    # =========================================================================
    
    def add_command(self, command: str, timestamp: Optional[datetime] = None) -> None:
        """Add a player command to the transcript"""
        if self.transcript:
            self.transcript.add_command(command, timestamp)
    
    def add_output(self, text: str, timestamp: Optional[datetime] = None) -> None:
        """Add game engine output to the transcript"""
        if self.transcript:
            self.transcript.add_output(text, timestamp)
    
    def add_error(self, error: str, timestamp: Optional[datetime] = None) -> None:
        """Add error message to the transcript"""
        if self.transcript:
            self.transcript.add_error(error, timestamp)
    
    def add_narration(self, text: str, timestamp: Optional[datetime] = None) -> None:
        """Add AI narration to the companion panel"""
        if self.narration:
            self.narration.add_narration(text, timestamp)
    
    def add_hint(self, hint: str) -> None:
        """Add a gameplay hint to the companion panel"""
        if self.narration:
            self.narration.add_hint(hint)
    
    def add_narration_separator(self) -> None:
        """Add visual separator in narration"""
        if self.narration:
            self.narration.add_separator()
    
    def clear_transcript(self) -> None:
        """Clear the game transcript"""
        if self.transcript:
            self.transcript.clear_transcript()
    
    def clear_narration(self) -> None:
        """Clear the AI narration"""
        if self.narration:
            self.narration.clear_narration()
    
    def set_engine_status(self, status: EngineStatus) -> None:
        """Update engine status indicator"""
        if self.status_bar:
            self.status_bar.set_engine_status(status)
    
    def set_ai_status(self, status: AIStatus) -> None:
        """Update AI status indicator"""
        if self.status_bar:
            self.status_bar.set_ai_status(status)
    
    def update_game_state(
        self,
        room: Optional[str] = None,
        moves: Optional[int] = None,
        score: Optional[int] = None
    ) -> None:
        """Update game state indicators"""
        if not self.status_bar:
            return
        
        if room is not None:
            self.status_bar.update_status("room", room)
        if moves is not None:
            self.status_bar.update_status("moves", str(moves))
        if score is not None:
            self.status_bar.update_status("score", str(score))
    
    def set_player_name(self, name: str) -> None:
        """Update player name display"""
        if self.status_bar:
            self.status_bar.update_status("player", name)
    
    def register_command_callback(self, callback: Callable[[str], None]) -> None:
        """Register callback for command submission"""
        self.on_command_callback = callback
    
    def register_player_rename_callback(self, callback: Callable[[], None]) -> None:
        """Register callback for player rename request"""
        self.on_player_rename_callback = callback
    
    def register_restart_callback(self, callback: Callable[[], None]) -> None:
        """Register callback for game restart request"""
        self.on_restart_callback = callback
    
    # =========================================================================
    # Action Handlers
    # =========================================================================
    
    def action_clear_transcript(self) -> None:
        """Clear transcript action"""
        self.clear_transcript()
    
    def action_clear_narration(self) -> None:
        """Clear narration action"""
        self.clear_narration()
    
    def action_restart(self) -> None:
        """Restart game action"""
        if self.on_restart_callback:
            self.on_restart_callback()


# =============================================================================
# Module-level Convenience Functions
# =============================================================================

def create_app(**kwargs) -> IFBuddyTUI:
    """Factory function to create a new TUI app instance"""
    return IFBuddyTUI(**kwargs)


def run_app_async(app: IFBuddyTUI):
    """Run the app asynchronously (non-blocking if used with proper event loop)"""
    return app.run_async()


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Demonstration of the TUI with simulated game interaction
    
    app = create_app()
    
    # Register callbacks
    def handle_command(cmd: str):
        print(f"[Game Logic] Received command: {cmd}")
        # Simulate game processing
        app.set_engine_status(EngineStatus.BUSY)
        
        # Simulate game response (would come from actual engine)
        app.call_later(
            lambda: app.add_output(f"You typed: {cmd}\nThe room echoes with your words.")
        )
        app.call_later(lambda: app.set_engine_status(EngineStatus.READY))
        
        # Simulate AI processing
        app.set_ai_status(AIStatus.WORKING)
        app.call_later(
            lambda: app.add_narration(
                f"Interesting choice! The command '{cmd}' reveals your curiosity."
            )
        )
        app.call_later(lambda: app.set_ai_status(AIStatus.READY))
    
    def handle_restart():
        print("[Game Logic] Restart requested")
        app.clear_transcript()
        app.clear_narration()
        app.add_narration("Game restarted. Ready for a new adventure!")
    
    app.register_command_callback(handle_command)
    app.register_restart_callback(handle_restart)
    
    # Run the application
    app.run()
