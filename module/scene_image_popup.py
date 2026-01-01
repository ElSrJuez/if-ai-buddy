"""Scene image popup widget for displaying generated scene images."""
from __future__ import annotations

from typing import Optional, Callable
import base64
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Label
from textual.reactive import reactive

from module import my_logging


class SceneImagePopup(ModalScreen):
    """Modal popup for displaying scene images with action buttons."""
    
    DEFAULT_CSS = """
    SceneImagePopup {
        align: center middle;
    }
    
    #popup_container {
        width: 60;
        height: 25;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    #room_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    #image_display {
        height: 10;
        text-align: center;
        border: solid $secondary;
        margin: 1 0;
        padding: 1;
    }
    
    #prompt_display {
        height: auto;
        margin: 1 0;
        padding: 1;
        border: solid $accent;
    }
    
    #action_buttons {
        height: auto;
        margin-top: 1;
    }
    
    .action_button {
        margin: 0 1;
    }
    """
    
    def __init__(
        self, 
        *,
        room_name: str,
        image_data: Optional[bytes] = None,
        prompt_text: str = "",
        quality: str = "medium",
        on_thumbs_down: Optional[Callable[[], None]] = None,
        on_regenerate: Optional[Callable[[], None]] = None,
        on_hide: Optional[Callable[[], None]] = None
    ) -> None:
        """Initialize scene image popup.
        
        Args:
            room_name: Name of the current room/scene
            image_data: Optional image bytes (PNG format)
            prompt_text: The prompt used to generate the image
            quality: Quality level of the image
            on_thumbs_down: Callback for thumbs down action
            on_regenerate: Callback for regenerate action
            on_hide: Callback for hide action
        """
        super().__init__()
        self.room_name = room_name
        self.image_data = image_data
        self.prompt_text = prompt_text
        self.quality = quality
        self._on_thumbs_down = on_thumbs_down
        self._on_regenerate = on_regenerate
        self._on_hide = on_hide
        
        my_logging.system_debug(f"SceneImagePopup created: {room_name} ({quality})")
    
    def compose(self) -> ComposeResult:
        """Compose the popup layout."""
        with Container(id="popup_container"):
            yield Label(self.room_name, id="room_title")
            yield self._create_image_display()
            yield self._create_prompt_display()
            yield self._create_action_buttons()
    
    def _create_image_display(self) -> Static:
        """Create the image display widget."""
        if self.image_data:
            # For terminal UI, we'll show image info instead of actual image
            image_size = len(self.image_data)
            size_kb = image_size / 1024
            display_text = f"🖼️  Scene Image ({size_kb:.1f}KB)\n[Image would be displayed here]\n{self.quality.title()} Quality"
        else:
            display_text = "📄  No Image Available\n[Placeholder or Logo]\nGenerate image to view"
        
        return Static(display_text, id="image_display")
    
    def _create_prompt_display(self) -> Static:
        """Create the prompt text display."""
        if self.prompt_text:
            display_text = f"Prompt: {self.prompt_text}"
        else:
            display_text = "No prompt information available"
        
        return Static(display_text, id="prompt_display")
    
    def _create_action_buttons(self) -> Horizontal:
        """Create the action button container."""
        return Horizontal(
            Button("👎 Feedback", id="thumbs_down_btn", classes="action_button"),
            Button("🔄 Regen", id="regen_btn", classes="action_button"), 
            Button("❌ Hide", id="hide_btn", classes="action_button"),
            id="action_buttons"
        )
    
    @on(Button.Pressed, "#thumbs_down_btn")
    def on_thumbs_down_pressed(self) -> None:
        """Handle thumbs down button press."""
        my_logging.system_info(f"Scene image thumbs down: {self.room_name}")
        if self._on_thumbs_down:
            self._on_thumbs_down()
        # Note: Don't auto-dismiss popup, let callback decide
    
    @on(Button.Pressed, "#regen_btn")
    def on_regenerate_pressed(self) -> None:
        """Handle regenerate button press."""
        my_logging.system_info(f"Scene image regenerate: {self.room_name}")
        if self._on_regenerate:
            self._on_regenerate()
        # Note: Don't auto-dismiss popup, let callback decide
    
    @on(Button.Pressed, "#hide_btn")
    def on_hide_pressed(self) -> None:
        """Handle hide button press."""
        my_logging.system_info(f"Scene image popup hidden: {self.room_name}")
        if self._on_hide:
            self._on_hide()
        self.dismiss()
    
    def key_escape(self) -> None:
        """Handle escape key - same as hide."""
        self.on_hide_pressed()
    
    def update_image(self, image_data: bytes, prompt_text: str, quality: str) -> None:
        """Update popup with new image data."""
        self.image_data = image_data
        self.prompt_text = prompt_text
        self.quality = quality
        
        # Update image display
        image_display = self.query_one("#image_display", Static)
        image_size = len(image_data)
        size_kb = image_size / 1024
        display_text = f"🖼️  Scene Image ({size_kb:.1f}KB)\n[Image would be displayed here]\n{quality.title()} Quality"
        image_display.update(display_text)
        
        # Update prompt display
        prompt_display = self.query_one("#prompt_display", Static)
        prompt_display.update(f"Prompt: {prompt_text}")
        
        my_logging.system_debug(f"SceneImagePopup updated: {self.room_name} ({quality})")
    
    def show_generation_progress(self) -> None:
        """Show generation in progress state."""
        image_display = self.query_one("#image_display", Static)
        image_display.update("🔄  Generating Image...\n[Please wait]\nThis may take a moment")
        
        # Disable regenerate button during generation
        regen_btn = self.query_one("#regen_btn", Button)
        regen_btn.disabled = True
    
    def hide_generation_progress(self) -> None:
        """Hide generation progress and re-enable buttons."""
        # Re-enable regenerate button
        regen_btn = self.query_one("#regen_btn", Button)
        regen_btn.disabled = False