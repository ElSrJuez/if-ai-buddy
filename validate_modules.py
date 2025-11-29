"""Quick validation script to test imports and basic module structure."""

import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

def test_imports():
    """Test that all modules import correctly."""
    print("Testing imports...")
    
    try:
        from module import my_config, my_logging
        print("✓ Config and logging modules imported")
    except Exception as e:
        print(f"✗ Failed to import config/logging: {e}")
        return False
    
    try:
        from module.rest_helper import DfrotzClient
        print("✓ REST helper imported")
    except Exception as e:
        print(f"✗ Failed to import REST helper: {e}")
        return False
    
    try:
        from module.game_api import GameAPI
        print("✓ Game API imported")
    except Exception as e:
        print(f"✗ Failed to import Game API: {e}")
        return False
    
    try:
        from module.ai_buddy_memory import GameMemoryStore
        print("✓ AI Buddy Memory imported")
    except Exception as e:
        print(f"✗ Failed to import AI Buddy Memory: {e}")
        return False
    
    try:
        from module.completions_helper import CompletionsHelper
        print("✓ Completions Helper imported")
    except Exception as e:
        print(f"✗ Failed to import Completions Helper: {e}")
        return False
    
    try:
        from module.ui_helper import IFBuddyTUI, create_app, StatusSnapshot
        print("✓ UI Helper imported")
    except Exception as e:
        print(f"✗ Failed to import UI Helper: {e}")
        return False
    
    try:
        from module.game_controller import GameController
        print("✓ Game Controller imported")
    except Exception as e:
        print(f"✗ Failed to import Game Controller: {e}")
        return False
    
    return True

def test_config():
    """Test that config loads correctly."""
    print("\nTesting config loading...")
    
    try:
        from module import my_config
        config = my_config.load_config("config/config.json")
        
        required_keys = [
            "player_name", "default_game", "dfrotz_base_url",
            "system_log", "game_jsonl", "loglevel", "llm_provider"
        ]
        
        missing = [k for k in required_keys if k not in config]
        if missing:
            print(f"✗ Missing config keys: {missing}")
            return False
        
        print(f"✓ Config loaded with {len(config)} keys")
        print(f"  - Player: {config.get('player_name')}")
        print(f"  - Game: {config.get('default_game')}")
        print(f"  - LLM Provider: {config.get('llm_provider')}")
        return True
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return False

def test_memory():
    """Test GameMemoryStore initialization."""
    print("\nTesting GameMemoryStore...")
    
    try:
        from module.ai_buddy_memory import GameMemoryStore
        memory = GameMemoryStore("TestPlayer")
        memory.add_turn("look", "You are in a white room.")
        memory.extract_and_promote_state("You are in a white room.")
        context = memory.get_context_for_prompt()
        
        print(f"✓ GameMemoryStore working")
        print(f"  - Episodic turns: {len(context['episodic_turns'])}")
        print(f"  - Current turn: {context['current_turn']}")
        return True
    except Exception as e:
        print(f"✗ Failed to test GameMemoryStore: {e}")
        return False

def test_status_snapshot():
    """Test StatusSnapshot."""
    print("\nTesting StatusSnapshot...")
    
    try:
        from module.ui_helper import StatusSnapshot, AIStatus, EngineStatus
        
        status = StatusSnapshot.default("Player", "Zork")
        updated = status.with_updates(moves=5, score=100)
        
        print(f"✓ StatusSnapshot working")
        print(f"  - Player: {updated.player}")
        print(f"  - Moves: {updated.moves}")
        print(f"  - Score: {updated.score}")
        return True
    except Exception as e:
        print(f"✗ Failed to test StatusSnapshot: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("IF AI Buddy - Module Validation")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Config", test_config),
        ("Memory", test_memory),
        ("Status", test_status_snapshot),
    ]
    
    results = []
    for name, test_func in tests:
        results.append((name, test_func()))
    
    print("\n" + "=" * 60)
    print("Summary:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
