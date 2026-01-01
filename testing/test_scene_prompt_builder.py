#!/usr/bin/env python3
"""Test script for Scene Image Prompt Builder."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from module.scene_image_prompt_builder import SceneImagePromptBuilder
from module import my_config


def test_scene_image_prompt_builder():
    """Test scene image prompt builder with mock game context."""
    print("Testing Scene Image Prompt Builder...")
    
    try:
        # Load configuration
        scene_config = my_config.load_scene_image_config()
        print(f"✅ Scene image config loaded")
        
        # Initialize prompt builder
        builder = SceneImagePromptBuilder(scene_config)
        print(f"✅ Prompt builder initialized")
        
        # Mock game memory context (based on GameMemoryStore.get_context_for_prompt structure)
        mock_context = {
            "player_name": "Adventurer",
            "turn_count": 5,
            "current_room": "West of House",
            "current_scene": {
                "room_name": "West of House",
                "description_lines": ["You are standing in an open field west of a white house", "with a boarded front door."],
                "current_items": ["mailbox", "leaflet"],
                "scene_items": ["mailbox", "leaflet", "door"],
                "npcs": [],
                "visit_count": 2,
                "narrations": ["The classic starting location of the great underground empire."],
                "action_records": []
            },
            "player_state": {
                "inventory": ["brass lantern"],
                "score": 0,
                "moves": 5,
                "name": "Adventurer"
            },
            "turn_hints": {
                "command": "west",
                "engine_excerpt": "arrived from the forest path"
            }
        }
        print(f"✅ Mock context created")
        
        # Test meta-prompt generation for LLM
        prompt_spec = builder.build_meta_prompt(memory_context=mock_context)
        
        print(f"✅ Meta-prompt generated:")
        print(f"  - Meta prompt: '{prompt_spec.meta_prompt}'")
        print(f"  - Room: {prompt_spec.metadata['room_name']}")
        print(f"  - Template: {prompt_spec.metadata['template_used']}")
        print()
        
        # Test with minimal context
        minimal_context = {
            "current_scene": {
                "room_name": "Dark Cave"
            }
        }
        
        minimal_prompt = builder.build_meta_prompt(memory_context=minimal_context)
        print(f"✅ Minimal context handled:")
        print(f"  - Meta prompt: '{minimal_prompt.meta_prompt}'")
        print(f"  - Room: {minimal_prompt.metadata['room_name']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_scene_image_prompt_builder()
    sys.exit(0 if success else 1)