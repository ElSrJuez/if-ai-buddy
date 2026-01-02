"""Standalone Scene Image Viewer process running Tk mainloop.

This module is launched as a subprocess to display a scene image and prompt
without interfering with the main application's event loop.

Usage:
    python -m module.scene_image_viewer --room "West of House" \
        --image-path "res/scene-img/west_of_house_medium.png" \
        --prompt "..."
"""
from __future__ import annotations

import argparse
import io
import sys
from typing import Optional

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


def _build_ui(root: tk.Tk, *, room_name: str, image_path: Optional[str], prompt_text: str) -> None:
    root.title(f"Scene Image - {room_name}")
    root.geometry("600x500")
    root.resizable(True, True)

    main_frame = ttk.Frame(root, padding="10")
    main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=1)

    title_label = ttk.Label(main_frame, text=room_name or "Unknown", font=("Arial", 14, "bold"))
    title_label.grid(row=0, column=0, pady=(0, 10))

    image_frame = ttk.LabelFrame(main_frame, text="Scene Image", padding="10")
    image_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
    image_frame.columnconfigure(0, weight=1)
    image_frame.rowconfigure(0, weight=1)

    image_label = ttk.Label(image_frame, text="Loading image...", anchor=tk.CENTER)
    image_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    prompt_frame = ttk.LabelFrame(main_frame, text="Generation Prompt", padding="5")
    prompt_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
    prompt_frame.columnconfigure(0, weight=1)

    prompt_widget = tk.Text(prompt_frame, height=3, wrap=tk.WORD, state=tk.NORMAL)
    prompt_widget.grid(row=0, column=0, sticky=(tk.W, tk.E))
    prompt_widget.insert(tk.END, prompt_text or "No prompt available")
    prompt_widget.config(state=tk.DISABLED)

    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=3, column=0, pady=(10, 0))

    hide_btn = ttk.Button(button_frame, text="❌ Hide", command=root.destroy)
    hide_btn.grid(row=0, column=2, padx=(5, 0))

    # Load image if available
    try:
        img_data: Optional[Image.Image] = None
        if image_path:
            img = Image.open(image_path)
            img_data = img
        if img_data:
            display_size = (500, 350)
            img_data.thumbnail(display_size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_data)
            image_label.configure(image=photo, text="")
            image_label.image = photo  # keep reference
        else:
            image_label.configure(text="No image available\n\nGenerate image to view", image="")
    except Exception as exc:
        image_label.configure(text=f"Error loading image: {exc}", image="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scene Image Viewer")
    parser.add_argument("--room", dest="room", default="Unknown")
    parser.add_argument("--image-path", dest="image_path", default=None)
    parser.add_argument("--prompt", dest="prompt", default="")
    args = parser.parse_args(argv)

    root = tk.Tk()
    _build_ui(root, room_name=args.room, image_path=args.image_path, prompt_text=args.prompt)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
