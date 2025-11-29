from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from module import my_config, my_logging
from module.game_controller import GameController
from module.rest_helper import DfrotzClient
from module.ui_runner import run_ui

CONFIG_PATH = Path("config/config.json")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IF AI Buddy")
    parser.add_argument("--game", help="Name of the z-machine game (without extension)")
    parser.add_argument(
        "--base-url",
        help="Base URL for the dfrotz REST wrapper",
    )
    parser.add_argument(
        "--label",
        help="Label to associate with the dfrotz session",
    )
    parser.add_argument(
        "--player",
        help="Player name for log files",
    )
    return parser


def require_config_field(config: dict[str, Any], key: str) -> Any:
    if key not in config:
        raise KeyError(f"Missing configuration value: {key}")
    return config[key]


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    config = my_config.load_config(str(CONFIG_PATH))
    player_name = args.player or str(require_config_field(config, "player_name"))
    base_url = args.base_url or str(require_config_field(config, "dfrotz_base_url"))
    game_name = args.game or str(require_config_field(config, "default_game"))
    session_label = args.label or player_name

    rest_client = DfrotzClient(base_url)
    controller = GameController(
        config={**config, "player_name": player_name, "default_game": game_name},
        rest_client=rest_client,
        game_name=game_name,
        session_label=session_label,
    )

    my_logging.init(controller.player_name, str(CONFIG_PATH))

    run_ui(controller)


if __name__ == "__main__":
    main()
