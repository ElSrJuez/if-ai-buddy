"""Scene image cache system for file-based storage in res/scene-img/."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from module import my_config, my_logging
from module.sd_server_client import ImageGenerationResponse


@dataclass
class SceneImageMetadata:
    """Metadata stored alongside cached scene images."""
    
    prompt: str
    size: str
    steps: int
    quality: str
    created: str
    room_name: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SceneImageMetadata:
        """Create from dictionary loaded from JSON."""
        return cls(**data)


class SceneImageCache:
    """File-based cache for scene images in res/scene-img/."""
    
    def __init__(self) -> None:
        """Initialize cache with configuration from scene image config."""
        self._config = my_config.load_scene_image_config()
        cache_dir = self._config["cache_directory"]
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        my_logging.system_info(f"SceneImageCache initialized: {self._cache_dir}")
    
    def generate_cache_key(self, room_name: str, quality: str) -> str:
        """Generate cache key from room name and quality level."""
        # Create filesystem-safe key from room name + quality
        safe_room = room_name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
        return f"{safe_room}_{quality}"
    
    def get_image_path(self, room_name: str, quality: str) -> Path:
        """Get the file path for cached image."""
        safe_room = room_name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
        return self._cache_dir / f"{safe_room}_{quality}.png"
    
    def get_metadata_path(self, room_name: str) -> Path:
        """Get the file path for cached metadata."""
        safe_room = room_name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
        return self._cache_dir / f"{safe_room}.json"
    
    def is_cached(self, room_name: str, quality: str) -> bool:
        """Check if image is cached."""
        image_path = self.get_image_path(room_name, quality)
        return image_path.exists()
    
    def get_available_qualities(self, room_name: str) -> list[str]:
        """Get list of available quality levels for a room."""
        metadata_path = self.get_metadata_path(room_name)
        if not metadata_path.exists():
            return []
        
        try:
            metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
            if "qualities" in metadata_data:
                return list(metadata_data["qualities"].keys())
            elif "quality" in metadata_data:
                # Old format - single quality
                return [metadata_data["quality"]]
            else:
                return []
        except (json.JSONDecodeError, KeyError):
            return []
    
    def store_image(
        self, 
        room_name: str,
        response: ImageGenerationResponse,
        quality: str
    ) -> None:
        """Store image and metadata to cache."""
        image_path = self.get_image_path(room_name, quality)
        metadata_path = self.get_metadata_path(room_name)
        
        # Store image data
        image_path.write_bytes(response.image_data)
        
        # Load existing metadata or create new structure
        if metadata_path.exists():
            existing_data = json.loads(metadata_path.read_text(encoding="utf-8"))
            # Handle migration from old single-metadata format
            if "qualities" not in existing_data:
                # Convert old format to new format
                old_quality = existing_data.get("quality")
                qualities_data = {}
                if old_quality:
                    qualities_data[old_quality] = {
                        "prompt": existing_data["prompt"],
                        "size": existing_data["size"],
                        "steps": existing_data["steps"],
                        "created": existing_data["created"]
                    }
                existing_data = {
                    "room_name": existing_data["room_name"],
                    "qualities": qualities_data
                }
        else:
            existing_data = {
                "room_name": room_name,
                "qualities": {}
            }
        
        # Update metadata for this specific quality
        existing_data["qualities"][quality] = {
            "prompt": response.prompt_used,
            "size": response.size,
            "steps": response.steps,
            "created": response.created
        }
        
        metadata_path.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
        
        my_logging.system_info(f"Scene image cached: {room_name} (quality={quality}, {len(response.image_data)} bytes)")
    
    def load_image(self, room_name: str, quality: str) -> tuple[bytes, SceneImageMetadata]:
        """Load image and metadata from cache."""
        if not self.is_cached(room_name, quality):
            raise FileNotFoundError(f"Scene image not cached: {room_name} ({quality})")
        
        image_path = self.get_image_path(room_name, quality)
        metadata_path = self.get_metadata_path(room_name)
        
        image_data = image_path.read_bytes()
        metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
        
        # Handle both old single-metadata format and new multi-quality format
        if "qualities" in metadata_data:
            # New format: extract specific quality
            if quality not in metadata_data["qualities"]:
                raise FileNotFoundError(f"Quality {quality} not found in metadata for {room_name}")
            quality_data = metadata_data["qualities"][quality]
            metadata = SceneImageMetadata(
                prompt=quality_data["prompt"],
                size=quality_data["size"],
                steps=quality_data["steps"],
                quality=quality,
                created=quality_data["created"],
                room_name=metadata_data["room_name"]
            )
        else:
            # Old format: direct metadata
            metadata = SceneImageMetadata.from_dict(metadata_data)
        
        my_logging.system_debug(f"Scene image loaded from cache: {room_name} ({quality})")
        return image_data, metadata
    
    def invalidate(self, cache_key: str) -> None:
        """Remove image and metadata from cache."""
        image_path = self.get_image_path(cache_key)
        metadata_path = self.get_metadata_path(cache_key)
        
        if image_path.exists():
            image_path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()
        
        my_logging.system_info(f"Scene image cache invalidated: {cache_key}")
    
    def list_cached_keys(self) -> list[str]:
        """List all cached image keys."""
        keys = []
        for png_file in self._cache_dir.glob("*.png"):
            key = png_file.stem
            if self.is_cached(key):  # Ensure both PNG and JSON exist
                keys.append(key)
        return sorted(keys)
    
    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        png_files = list(self._cache_dir.glob("*.png"))
        total_size = sum(png_file.stat().st_size for png_file in png_files)
        
        # Count unique rooms
        rooms = set()
        for png_file in png_files:
            # Extract room name from filename (remove _quality.png)
            parts = png_file.stem.split("_")
            if len(parts) >= 2:
                room_parts = parts[:-1]  # All but last part (quality)
                room_name = "_".join(room_parts)
                rooms.add(room_name)
        
        return {
            "cached_images": len(png_files),
            "unique_rooms": len(rooms),
            "total_size_bytes": total_size,
            "cache_directory": str(self._cache_dir)
        }