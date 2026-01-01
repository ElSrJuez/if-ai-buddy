#!/usr/bin/env python3
"""Test script for SD-Server client using actual project constructs."""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from module.sd_server_client import SDServerClient, ImageGenerationRequest
from module.scene_image_cache import SceneImageCache
from module import my_config


async def test_sd_server_client(quality_name: str = None):
    """Test SD server client using our actual configuration constructs."""
    print("Testing SD-Server client with project constructs...")
    
    try:
        # Test our configuration loading
        scene_config = my_config.load_scene_image_config()
        print(f"✅ Scene image config loaded")
        
        # Test our quality presets
        quality_presets = scene_config["quality_presets"]
        default_quality = scene_config["default_quality"]
        
        # Use specified quality or fall back to default
        target_quality = quality_name if quality_name else default_quality
        
        # Validate quality exists
        if target_quality not in quality_presets:
            available_qualities = list(quality_presets.keys())
            raise ValueError(f"Quality '{target_quality}' not found. Available: {available_qualities}")
        
        quality_config = quality_presets[target_quality]
        print(f"✅ Config values: quality={target_quality}, steps={quality_config['steps']}, size={quality_config['size']}")
        
        # Test client initialization with our config
        client = SDServerClient()
        print(f"✅ Client initialized from our config system")
        
        # Create request using our configuration constructs
        request = ImageGenerationRequest(
            prompt="pencil art: a mysterious cave entrance",  # TODO: Use prompt template system
            size=quality_config["size"],
            steps=quality_config["steps"]
        )
        print(f"✅ Request created using config: {request.size}, {request.steps} steps")
        
        # Generate image
        print("🔄 Generating image...")
        response = await client.generate_image(request)
        
        # Test our cache system construct
        cache = SceneImageCache()
        print(f"✅ Cache system initialized")
        
        # Test cache key generation  
        room_name = "West of House Test"  # Use actual project scene identifier
        print(f"✅ Using room name: {room_name} with quality: {target_quality}")
        
        # Test cache storage
        cache.store_image(room_name, response, target_quality)
        print(f"✅ Image stored in cache system with quality tracking")
        
        # Test cache retrieval
        cached_image, cached_metadata = cache.load_image(room_name, target_quality)
        print(f"✅ Image loaded from cache system:")
        print(f"  - Cached size: {len(cached_image)} bytes")
        print(f"  - Metadata prompt: {cached_metadata.prompt}")
        print(f"  - Metadata quality: {cached_metadata.quality}")
        print(f"  - Metadata steps: {cached_metadata.steps}")
        
        # Test cache statistics
        stats = cache.get_cache_stats()
        print(f"✅ Cache stats: {stats['cached_images']} images, {stats['total_size_bytes']} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Test SD-Server client with configurable quality")
    parser.add_argument("--quality", type=str, help="Quality preset to use (e.g., medium, high)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    success = asyncio.run(test_sd_server_client(args.quality))
    sys.exit(0 if success else 1)