"""Scene image prompt builder for generating concise AI diffusion prompts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module import my_config, my_logging


@dataclass(slots=True)
class SceneImagePromptSpec:
    """Meta-prompt specification for LLM to generate diffusion prompt."""

    meta_prompt: str  # What gets sent to LLM
    metadata: dict[str, Any]


class SceneImagePromptBuilder:
    """Transforms game memory context into concise AI diffusion prompts."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with scene image configuration."""
        self.config = config
        self._prompt_template = my_config.load_scene_image_prompt_template()
        self.system_prompt = self._prompt_template.get("system_prompt", "")
        self.max_prompt_length = self._prompt_template.get("max_prompt_length", 120)
        self.style_prefix = self._prompt_template.get("style_prefix", "detailed pencil art illustration of")
        
        my_logging.system_info(f"SceneImagePromptBuilder initialized (max_length={self.max_prompt_length})")

    def build_meta_prompt(
        self,
        *,
        memory_context: dict[str, Any]
    ) -> SceneImagePromptSpec:
        """Build meta-prompt that will be sent to LLM to generate diffusion prompt."""
        
        # Extract scene context using template value sources
        scene_context = self._extract_scene_context(memory_context)
        
        # Build meta-prompt for LLM instruction
        meta_prompt = self._format_meta_prompt_template(scene_context)
        
        metadata = {
            "room_name": scene_context.get("room_name", "Unknown"),
            "extracted_context": scene_context,
            "template_used": "scene_template"
        }
        
        my_logging.system_debug(f"Meta-prompt built for {metadata['room_name']}: {len(meta_prompt)} chars")
        
        return SceneImagePromptSpec(
            meta_prompt=meta_prompt,
            metadata=metadata
        )
    
    def _extract_scene_context(self, memory_context: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant scene information from game memory context."""
        value_sources = self._prompt_template.get("value_sources", {})
        scene_context = {}
        
        for key, source_config in value_sources.items():
            try:
                # Navigate path in memory context (e.g., "current_scene.room_name")
                path = source_config["path"]
                value = self._navigate_context_path(memory_context, path)
                
                # Apply transformations if specified
                if value is not None and "transform" in source_config:
                    value = self._apply_transform(value, source_config)
                
                # Use value or fallback
                scene_context[key] = value if value is not None else source_config.get("fallback", "")
                
            except (KeyError, TypeError, AttributeError) as exc:
                fallback = source_config.get("fallback", "")
                scene_context[key] = fallback
                my_logging.system_debug(f"Scene context extraction failed for '{key}': {exc}, using fallback: '{fallback}'")
        
        return scene_context
    
    def _navigate_context_path(self, context: dict[str, Any], path: str) -> Any:
        """Navigate nested dictionary path like 'current_scene.room_name'."""
        parts = path.split(".")
        current = context
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def _apply_transform(self, value: Any, config: dict[str, Any]) -> str:
        """Apply configured transformations to extracted values."""
        transform = config["transform"]
        
        if transform == "join_truncate" and isinstance(value, list):
            # Join list items and truncate to max_length
            joined = " ".join(str(item) for item in value)
            max_length = config.get("max_length", 200)
            return joined[:max_length] if len(joined) > max_length else joined
            
        elif transform == "join_list" and isinstance(value, list):
            # Join list with comma separation, respecting max_items
            max_items = config.get("max_items", 3)
            limited_items = value[:max_items] if len(value) > max_items else value
            return ", ".join(str(item) for item in limited_items)
        
        elif isinstance(value, list):
            # Default list handling - join with spaces
            return " ".join(str(item) for item in value)
        
        return str(value)
    
    def _format_meta_prompt_template(self, scene_context: dict[str, Any]) -> str:
        """Format the meta-prompt template with scene context."""
        template = self._prompt_template.get("scene_template", "")
        
        if not template:
            raise ValueError("No scene_template configured in prompt template")
        
        # Add template variables like style_prefix to context
        expanded_context = scene_context.copy()
        expanded_context["style_prefix"] = self.style_prefix
        expanded_context["max_prompt_length"] = self.max_prompt_length
        
        try:
            # Format template with scene context
            return template.format(**expanded_context)
        except KeyError as exc:
            # If template formatting fails, let it fail - no fallbacks
            raise ValueError(f"Template formatting failed - missing variable: {exc}") from exc