"""Bootstrap script for IF AI Buddy.

Loads configuration, initializes logging, and hands control to the game controller.
Follows configuration-driven, fail-fast principles per coding guidelines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from module import my_config, my_logging
from module.game_controller import GameController
from module.llm_factory_FoundryLocal import create_llm_client

def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "config.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the IF AI Buddy TUI")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to config.json (defaults to ./config/config.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config_path = args.config
    
    # Validate config file exists
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Load config (fail fast if invalid)
    config = my_config.load_config(str(config_path))
    schema_paths = my_config.get_schema_paths()

    # Extract player name for logging setup
    player_name = config.get("player_name", "Adventurer")

    # Initialize logging (fail fast if config is invalid)
    try:
        my_logging.init(player_name=player_name, config=config)
    except Exception as exc:
        print(f"Failed to initialize logging: {exc}", file=sys.stderr)
        raise

    # Log startup
    my_logging.system_info("IF AI Buddy starting")
    my_logging.system_info(f"Config loaded from {config_path}")
    my_logging.system_info(
        f"Schema paths resolved: game_engine={schema_paths['game_engine']}, ai_engine={schema_paths['ai_engine']}"
    )

    try:
        # Create LLM client (fail fast if config is invalid)
        llm_client = create_llm_client(config)
        my_logging.system_debug(f"LLM client created for provider: {config.get('llm_provider', 'foundry')}")
        
        # Create and run controller
        controller = GameController(config, llm_client)
        controller.run()
    except Exception as exc:
        my_logging.system_log(f"Fatal error: {exc}")
        raise


if __name__ == "__main__":
    main()
