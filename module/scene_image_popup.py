"""Scene image popup as OS desktop window for displaying generated images.

This module provides a real desktop popup window since Textual cannot display images.
Uses tkinter to create an OS-native window with actual image display and action buttons.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import io
from typing import Callable, Optional
from pathlib import Path

from module import my_logging


class SceneImagePopup:
    """OS desktop popup window for displaying scene images with action controls."""
    
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
        """Initialize scene image desktop popup.
        
        Args:
            room_name: Name of the current room/scene
            image_data: Optional image bytes (PNG format)
            prompt_text: The prompt used to generate the image
            quality: Quality level of the image
            on_thumbs_down: Callback for thumbs down action
            on_regenerate: Callback for regenerate action
            on_hide: Callback for hide action
        """
        self.room_name = room_name
        self.image_data = image_data
        self.prompt_text = prompt_text
        self.quality = quality
        self._on_thumbs_down = on_thumbs_down
        self._on_regenerate = on_regenerate
        self._on_hide = on_hide
        
        self._window: Optional[tk.Toplevel] = None
        self._image_label: Optional[tk.Label] = None
        
        my_logging.system_debug(f"SceneImagePopup created: {room_name} ({quality})")
    
    def show(self) -> None:
        """Show the desktop popup window."""
        if self._window is not None:
            self._window.lift()
            try:
                self._window.update_idletasks()
                self._window.update()
            except Exception:
                pass
            return
            
        # Create root window if it doesn't exist
        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()  # Hide the root window
        
        # Create popup window
        self._window = tk.Toplevel(root)
        self._window.title(f"Scene Image - {self.room_name}")
        # Size and position (centered)
        width, height = 600, 500
        try:
            screen_w = self._window.winfo_screenwidth()
            screen_h = self._window.winfo_screenheight()
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            self._window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self._window.geometry("600x500")
        self._window.resizable(True, True)
        
        # Raise window and ensure initial visibility
        try:
            self._window.attributes('-topmost', True)
        except Exception:
            pass
        self._window.lift()
        self._window.focus_force()
        
        # Handle window close
        self._window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self._create_widgets()
        self._update_content()
        # Force a draw without entering mainloop
        try:
            self._window.update_idletasks()
            self._window.update()
        except Exception:
            pass
        # Drop topmost after showing so gameplay isn't blocked
        try:
            self._window.attributes('-topmost', False)
        except Exception:
            pass
        
        my_logging.system_info(f"Scene image popup shown: {self.room_name}")
    
    def _create_widgets(self) -> None:
        """Create the popup window widgets."""
        if not self._window:
            return
            
        # Main frame
        main_frame = ttk.Frame(self._window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self._window.columnconfigure(0, weight=1)
        self._window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Room title
        title_label = ttk.Label(main_frame, text=self.room_name, font=('Arial', 14, 'bold'))
        title_label.grid(row=0, column=0, pady=(0, 10))
        
        # Image display area
        image_frame = ttk.LabelFrame(main_frame, text="Scene Image", padding="10")
        image_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        image_frame.columnconfigure(0, weight=1)
        image_frame.rowconfigure(0, weight=1)
        
        self._image_label = ttk.Label(image_frame, text="Loading image...", anchor=tk.CENTER)
        self._image_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Prompt display
        prompt_frame = ttk.LabelFrame(main_frame, text="Generation Prompt", padding="5")
        prompt_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        prompt_frame.columnconfigure(0, weight=1)
        
        prompt_text = tk.Text(prompt_frame, height=3, wrap=tk.WORD, state=tk.DISABLED)
        prompt_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Insert prompt text
        prompt_text.config(state=tk.NORMAL)
        prompt_text.insert(tk.END, self.prompt_text or "No prompt available")
        prompt_text.config(state=tk.DISABLED)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, pady=(10, 0))
        
        thumbs_down_btn = ttk.Button(button_frame, text="👎 Feedback", command=self._handle_thumbs_down)
        thumbs_down_btn.grid(row=0, column=0, padx=(0, 5))
        
        regen_btn = ttk.Button(button_frame, text="🔄 Regenerate", command=self._handle_regenerate)
        regen_btn.grid(row=0, column=1, padx=5)
        
        hide_btn = ttk.Button(button_frame, text="❌ Hide", command=self._handle_hide)
        hide_btn.grid(row=0, column=2, padx=(5, 0))
    
    def _update_content(self) -> None:
        """Update the popup content with current image and text."""
        if not self._image_label:
            return
            
        if self.image_data:
            try:
                # Load image from bytes
                image = Image.open(io.BytesIO(self.image_data))
                
                # Resize to fit display area while maintaining aspect ratio
                display_size = (500, 350)
                image.thumbnail(display_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage for tkinter
                photo = ImageTk.PhotoImage(image)
                self._image_label.configure(image=photo, text="")
                
                # Keep a reference to prevent garbage collection
                self._image_label.image = photo  # type: ignore
                
                my_logging.system_debug(f"Scene image displayed: {image.size}")
                
            except Exception as exc:
                self._image_label.configure(text=f"Error loading image: {exc}", image="")
                my_logging.system_warn(f"Failed to display scene image: {exc}")
        else:
            self._image_label.configure(text="No image available\n\nGenerate image to view", image="")
    
    def _handle_thumbs_down(self) -> None:
        """Handle thumbs down button click."""
        my_logging.system_info(f"Scene image thumbs down: {self.room_name}")
        if self._on_thumbs_down:
            self._on_thumbs_down()
    
    def _handle_regenerate(self) -> None:
        """Handle regenerate button click."""
        my_logging.system_info(f"Scene image regenerate: {self.room_name}")
        if self._on_regenerate:
            self._on_regenerate()
    
    def _handle_hide(self) -> None:
        """Handle hide button click."""
        my_logging.system_info(f"Scene image popup hidden: {self.room_name}")
        if self._on_hide:
            self._on_hide()
        self.close()
    
    def _on_window_close(self) -> None:
        """Handle window close event."""
        self._handle_hide()
    
    def close(self) -> None:
        """Close the popup window."""
        if self._window:
            self._window.destroy()
            self._window = None
            self._image_label = None
    
    def update_image(self, image_data: bytes, prompt_text: str, quality: str) -> None:
        """Update popup with new image data."""
        self.image_data = image_data
        self.prompt_text = prompt_text
        self.quality = quality
        
        if self._window and self._window.winfo_exists():
            self._update_content()
        
        my_logging.system_debug(f"SceneImagePopup updated: {self.room_name} ({quality})")
    
    def show_generation_progress(self) -> None:
        """Show generation in progress state."""
        if self._image_label:
            self._image_label.configure(text="🔄 Generating Image...\n\nPlease wait\nThis may take a moment", image="")
    
    def hide_generation_progress(self) -> None:
        """Hide generation progress and restore normal state."""
        self._update_content()