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
        width: auto;
        height: auto;
        min-width: 60;
        min-height: 20;
        max-width: 80%;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    
    #image_display {
        width: 1fr;
        height: 15;
        background: $surface-darken-1;
        border: solid $accent;
        text-align: center;
        content-align: center middle;
        margin-bottom: 1;
    }
    
    #prompt_display {
        width: 1fr;
        height: auto;
        max-height: 4;
        background: $surface-darken-2;
        border: solid $secondary;
        padding: 1;
        margin-bottom: 1;
        text-wrap: true;
    }
    
    #action_buttons {
        width: 1fr;
        height: auto;
        layout: horizontal;
        align: center middle;
    }
    
    .action_button {
        margin: 0 1;
        min-width: 12;
    }
    
    #room_title {
        width: 1fr;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
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
        \"\"\"Initialize scene image popup.\n        \n        Args:\n            room_name: Name of the current room/scene\n            image_data: Optional image bytes (PNG format)\n            prompt_text: The prompt used to generate the image\n            quality: Quality level of the image\n            on_thumbs_down: Callback for thumbs down action\n            on_regenerate: Callback for regenerate action\n            on_hide: Callback for hide action\n        \"\"\"\n        super().__init__()\n        self.room_name = room_name\n        self.image_data = image_data\n        self.prompt_text = prompt_text\n        self.quality = quality\n        self._on_thumbs_down = on_thumbs_down\n        self._on_regenerate = on_regenerate\n        self._on_hide = on_hide\n        \n        my_logging.system_debug(f\"SceneImagePopup created: {room_name} ({quality})\")\n    \n    def compose(self) -> ComposeResult:\n        \"\"\"Compose the popup layout.\"\"\"\n        with Container(id=\"popup_container\"):\n            yield Label(self.room_name, id=\"room_title\")\n            yield self._create_image_display()\n            yield self._create_prompt_display()\n            yield self._create_action_buttons()\n    \n    def _create_image_display(self) -> Static:\n        \"\"\"Create the image display widget.\"\"\"\n        if self.image_data:\n            # For terminal UI, we'll show image info instead of actual image\n            image_size = len(self.image_data)\n            size_kb = image_size / 1024\n            display_text = f\"🖼️  Scene Image ({size_kb:.1f}KB)\\n[Image would be displayed here]\\n{self.quality.title()} Quality\"\n        else:\n            display_text = \"📄  No Image Available\\n[Placeholder or Logo]\\nGenerate image to view\"\n        \n        return Static(display_text, id=\"image_display\")\n    \n    def _create_prompt_display(self) -> Static:\n        \"\"\"Create the prompt text display.\"\"\"\n        if self.prompt_text:\n            display_text = f\"Prompt: {self.prompt_text}\"\n        else:\n            display_text = \"No prompt information available\"\n        \n        return Static(display_text, id=\"prompt_display\")\n    \n    def _create_action_buttons(self) -> Horizontal:\n        \"\"\"Create the action button container.\"\"\"\n        return Horizontal(\n            Button(\"👎 Feedback\", id=\"thumbs_down_btn\", classes=\"action_button\"),\n            Button(\"🔄 Regen\", id=\"regen_btn\", classes=\"action_button\"), \n            Button(\"❌ Hide\", id=\"hide_btn\", classes=\"action_button\"),\n            id=\"action_buttons\"\n        )\n    \n    @on(Button.Pressed, \"#thumbs_down_btn\")\n    def on_thumbs_down_pressed(self) -> None:\n        \"\"\"Handle thumbs down button press.\"\"\"\n        my_logging.system_info(f\"Scene image thumbs down: {self.room_name}\")\n        if self._on_thumbs_down:\n            self._on_thumbs_down()\n        # Note: Don't auto-dismiss popup, let callback decide\n    \n    @on(Button.Pressed, \"#regen_btn\")\n    def on_regenerate_pressed(self) -> None:\n        \"\"\"Handle regenerate button press.\"\"\"\n        my_logging.system_info(f\"Scene image regenerate: {self.room_name}\")\n        if self._on_regenerate:\n            self._on_regenerate()\n        # Note: Don't auto-dismiss popup, let callback decide\n    \n    @on(Button.Pressed, \"#hide_btn\")\n    def on_hide_pressed(self) -> None:\n        \"\"\"Handle hide button press.\"\"\"\n        my_logging.system_info(f\"Scene image popup hidden: {self.room_name}\")\n        if self._on_hide:\n            self._on_hide()\n        self.dismiss()\n    \n    def key_escape(self) -> None:\n        \"\"\"Handle escape key - same as hide.\"\"\"\n        self.on_hide_pressed()\n    \n    def update_image(self, image_data: bytes, prompt_text: str, quality: str) -> None:\n        \"\"\"Update popup with new image data.\"\"\"\n        self.image_data = image_data\n        self.prompt_text = prompt_text\n        self.quality = quality\n        \n        # Update image display\n        image_display = self.query_one(\"#image_display\", Static)\n        image_size = len(image_data)\n        size_kb = image_size / 1024\n        display_text = f\"🖼️  Scene Image ({size_kb:.1f}KB)\\n[Image would be displayed here]\\n{quality.title()} Quality\"\n        image_display.update(display_text)\n        \n        # Update prompt display\n        prompt_display = self.query_one(\"#prompt_display\", Static)\n        prompt_display.update(f\"Prompt: {prompt_text}\")\n        \n        my_logging.system_debug(f\"SceneImagePopup updated: {self.room_name} ({quality})\")\n    \n    def show_generation_progress(self) -> None:\n        \"\"\"Show generation in progress state.\"\"\"\n        image_display = self.query_one(\"#image_display\", Static)\n        image_display.update(\"🔄  Generating Image...\\n[Please wait]\\nThis may take a moment\")\n        \n        # Disable regenerate button during generation\n        regen_btn = self.query_one(\"#regen_btn\", Button)\n        regen_btn.disabled = True\n    \n    def hide_generation_progress(self) -> None:\n        \"\"\"Hide generation progress and re-enable buttons.\"\"\"\n        # Re-enable regenerate button\n        regen_btn = self.query_one(\"#regen_btn\", Button)\n        regen_btn.disabled = False