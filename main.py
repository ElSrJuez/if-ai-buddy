"""Bootstrap script for IF AI Buddy.

Loads configuration, initializes logging, and hands control to the game controller.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from module import my_config, my_logging
from module.game_controller import GameController


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
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = my_config.load_config(str(config_path))
    player_name = config.get("player_name", "Adventurer")
    my_logging.init(player_name=player_name, config_file=str(config_path))

    controller = GameController(config)
    controller.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - we want a loud failure per principles
        print(f"Fatal error: {exc}", file=sys.stderr)
        raise
