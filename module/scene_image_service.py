"""Scene image service for managing image generation workflow."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from module import my_config, my_logging
from module.scene_image_cache import SceneImageCache
from module.scene_image_prompt_builder import SceneImagePromptBuilder, SceneImagePromptSpec
from module.sd_server_client import SDServerClient, ImageGenerationRequest, ImageGenerationResponse


@dataclass(slots=True)
class SceneImageJob:
    """Scene image generation job specification."""
    
    room_name: str
    quality: str
    memory_context: dict[str, Any]
    force_regenerate: bool = False
    
    def __str__(self) -> str:
        regen_flag = " (regen)" if self.force_regenerate else ""
        return f"SceneImageJob({self.room_name}, {self.quality}{regen_flag})"


class SceneImageService:
    """Orchestrates scene image generation workflow with cache-first approach."""
    
    def __init__(self, main_config: dict[str, Any]) -> None:
        """Initialize service with configuration and dependencies."""
        self._config = my_config.load_scene_image_config()
        self._cache = SceneImageCache()
        # Pass main config to prompt builder for LLM settings
        self._prompt_builder = SceneImagePromptBuilder(main_config)
        self._sd_client = SDServerClient()
        self._enabled = self._config.get("enable_scene_images", True)
        
        # Current state tracking
        self._current_room: Optional[str] = None
        self._generation_in_progress: Optional[SceneImageJob] = None
        
        my_logging.system_info(f"SceneImageService initialized (enabled={self._enabled})")
    
    def is_enabled(self) -> bool:
        """Check if scene image generation is enabled."""
        return self._enabled
    
    def is_generation_in_progress(self) -> bool:
        """Check if image generation is currently in progress."""
        return self._generation_in_progress is not None
    
    def should_auto_generate(self, room_name: str) -> bool:
        """Determine if scene should auto-generate image on entry."""
        if not self._enabled:
            return False
        
        # Check if this is a new scene entry
        if self._current_room == room_name:
            return False  # Same room, no auto-generation
        
        # Check if auto-display is enabled
        auto_display = self._config.get("auto_display_on_new_scene", True)
        if not auto_display:
            return False
        
        # Check if we have cached image for default quality
        default_quality = self._config.get("default_quality", "medium")
        return not self._cache.is_cached(room_name, default_quality)
    
    def update_current_room(self, room_name: str) -> None:
        """Update current room tracking for scene change detection."""
        self._current_room = room_name
        my_logging.system_debug(f"Scene service tracking room: {room_name}")
    
    async def generate_scene_image(
        self,
        *,
        room_name: str,
        memory_context: dict[str, Any],
        quality: Optional[str] = None,
        force_regenerate: bool = False
    ) -> tuple[bytes, dict[str, Any]]:
        """Generate scene image with cache-first approach.
        
        Returns:
            Tuple of (image_data, metadata_dict)
        """
        if not self._enabled:
            raise RuntimeError("Scene image generation is disabled")
        
        target_quality = quality or self._config.get("default_quality", "medium")
        
        # Create job specification
        job = SceneImageJob(
            room_name=room_name,
            quality=target_quality,
            memory_context=memory_context,
            force_regenerate=force_regenerate
        )
        
        my_logging.system_info(f"Scene image generation requested: {job}")
        
        # Check cache first (unless forced regeneration)
        if not force_regenerate and self._cache.is_cached(room_name, target_quality):
            my_logging.system_info(f"Scene image cache hit: {room_name} ({target_quality})")
            image_data, metadata = self._cache.load_image(room_name, target_quality)
            return image_data, metadata.to_dict()
        
        # Generate new image
        return await self._generate_new_image(job)
    
    async def regenerate_scene_image(
        self,
        *,
        room_name: str,
        memory_context: dict[str, Any],
        quality: Optional[str] = None
    ) -> tuple[bytes, dict[str, Any]]:
        """Force regeneration of scene image (bypasses cache)."""
        regen_quality = quality or self._config.get("regen_quality", "high")
        return await self.generate_scene_image(
            room_name=room_name,
            memory_context=memory_context,
            quality=regen_quality,
            force_regenerate=True
        )

    async def regenerate_image_from_cached_prompt(
        self,
        *,
        room_name: str,
        quality: Optional[str] = None
    ) -> tuple[bytes, dict[str, Any]]:
        """Regenerate image using existing cached prompt without changing it.

        Uses regen quality from config unless explicitly provided.
        """
        target_quality = quality or self._config.get("regen_quality", "high")
        
        # Load cached prompt from any available quality (prefer default)
        default_quality = self._config.get("default_quality", "medium")
        prompt_source_quality = default_quality if self._cache.is_cached(room_name, default_quality) else None
        if prompt_source_quality is None:
            # Try any available quality
            qualities = self._cache.get_available_qualities(room_name)
            if not qualities:
                raise FileNotFoundError(f"No cached image available for room '{room_name}' to reuse prompt")
            prompt_source_quality = qualities[0]
        
        # Load metadata and reuse prompt
        _, metadata_obj = self._cache.load_image(room_name, prompt_source_quality)
        diffusion_prompt = metadata_obj.prompt
        
        # Build request using target regen quality
        quality_presets = self._config.get("quality_presets", {})
        if target_quality not in quality_presets:
            available_qualities = list(quality_presets.keys())
            raise ValueError(f"Quality '{target_quality}' not found. Available: {available_qualities}")
        quality_config = quality_presets[target_quality]
        
        request = ImageGenerationRequest(
            prompt=diffusion_prompt,
            size=quality_config["size"],
            steps=quality_config["steps"]
        )
        
        # Generate image and store
        my_logging.system_info(f"Regenerating image from cached prompt: {room_name} ({target_quality})")
        response = await self._sd_client.generate_image(request)
        self._cache.store_image(room_name, response, target_quality)
        
        metadata = {
            "prompt": diffusion_prompt,
            "size": response.size,
            "steps": response.steps,
            "quality": target_quality,
            "created": response.created,
            "room_name": room_name,
            "image_path": str(self._cache.get_image_path(room_name, target_quality))
        }
        return response.image_data, metadata
    
    def get_cached_image(
        self,
        room_name: str,
        quality: Optional[str] = None
    ) -> Optional[tuple[bytes, dict[str, Any]]]:
        """Get cached image if available, otherwise None."""
        target_quality = quality or self._config.get("default_quality", "medium")
        
        if self._cache.is_cached(room_name, target_quality):
            try:
                image_data, metadata = self._cache.load_image(room_name, target_quality)
                # Include image path so UI can load bytes from disk if needed
                metadata_dict = metadata.to_dict()
                metadata_dict["image_path"] = str(self._cache.get_image_path(room_name, target_quality))
                return image_data, metadata_dict
            except FileNotFoundError:
                return None
        
        return None
    
    def get_available_qualities(self, room_name: str) -> list[str]:
        """Get list of available cached quality levels for a room."""
        return self._cache.get_available_qualities(room_name)
    
    def get_placeholder_image(self) -> Optional[bytes]:
        """Get placeholder image data if configured."""
        placeholder_path = self._config.get("placeholder_image_path")
        if placeholder_path:
            try:
                from pathlib import Path
                path = Path(placeholder_path)
                if path.exists():
                    return path.read_bytes()
            except Exception as exc:
                my_logging.system_warn(f"Failed to load placeholder image: {exc}")
        
        return None
    
    async def _generate_new_image(self, job: SceneImageJob) -> tuple[bytes, dict[str, Any]]:
        """Generate new scene image (internal implementation)."""
        self._generation_in_progress = job
        
        try:
            # Generate diffusion prompt via LLM
            if hasattr(self, '_on_sd_prompt_start') and callable(self._on_sd_prompt_start):
                self._on_sd_prompt_start()
                
            diffusion_prompt = await self._prompt_builder.generate_sd_prompt(
                memory_context=job.memory_context
            )
            
            if hasattr(self, '_on_sd_prompt_end') and callable(self._on_sd_prompt_end):
                self._on_sd_prompt_end()
            
            my_logging.system_info(f"LLM generated diffusion prompt for {job.room_name}: '{diffusion_prompt}'")
            
            # Get quality configuration from presets
            quality_presets = self._config.get("quality_presets", {})
            if job.quality not in quality_presets:
                available_qualities = list(quality_presets.keys())
                raise ValueError(f"Quality '{job.quality}' not found. Available: {available_qualities}")
            
            quality_config = quality_presets[job.quality]
            
            # Create SD server request
            request = ImageGenerationRequest(
                prompt=diffusion_prompt,
                size=quality_config["size"],
                steps=quality_config["steps"]
            )
            
            # Generate image via SD server
            my_logging.system_info(f"Generating scene image: {job.room_name} ({job.quality})")
            response = await self._sd_client.generate_image(request)
            
            # Store in cache
            self._cache.store_image(job.room_name, response, job.quality)
            
            # Create metadata for return
            metadata = {
                "prompt": diffusion_prompt,
                "size": response.size,
                "steps": response.steps,
                "quality": job.quality,
                "created": response.created,
                "room_name": job.room_name,
                "image_path": str(self._cache.get_image_path(job.room_name, job.quality))
            }
            
            my_logging.system_info(f"Scene image generated: {job.room_name} ({len(response.image_data)} bytes)")
            return response.image_data, metadata
            
        finally:
            self._generation_in_progress = None
    
    def get_service_status(self) -> dict[str, Any]:
        """Get current service status and statistics."""
        cache_stats = self._cache.get_cache_stats()
        
        return {
            "enabled": self._enabled,
            "current_room": self._current_room,
            "generation_in_progress": str(self._generation_in_progress) if self._generation_in_progress else None,
            "cache_stats": cache_stats,
            "config": {
                "default_quality": self._config.get("default_quality"),
                "regen_quality": self._config.get("regen_quality"),
                "auto_display": self._config.get("auto_display_on_new_scene"),
                "available_qualities": list(self._config.get("quality_presets", {}).keys())
            }
        }