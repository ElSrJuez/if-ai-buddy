"""Bootstrap script for IF AI Buddy.

Loads configuration, initializes logging, and hands control to the game controller.
Follows configuration-driven, fail-fast principles per coding guidelines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from module import my_config, my_logging
from module.config_registry import resolve_path, resolve_template_path
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
    parser.add_argument(
        "--purge-data",
        action="store_true",
        help="Delete configured log files and memory DBs before startup",
    )
    return parser.parse_args(argv)


def _purge_run_data(config: dict[str, Any]) -> None:
    project_root = Path(__file__).resolve().parent
    # Config validation requires player_name; keep a safe fallback anyway.
    player = str(config.get("player_name") or "Adventurer")

    # Only delete what the config explicitly points to.
    path_keys = [
        "system_log",
        "gameapi_jsonl",
        "rest_jsonl",
    ]

    # Paths with {player} formatting.
    template_keys = [
        "common_llm_layer_jsonl",
        "common_llm_simple_interaction_history_jsonl",
        "game_engine_jsonl_filename_template",
        "llm_completion_jsonl_filename_template",
        "memory_jsonl_filename_template",
    ]

    paths: set[Path] = set()
    for key in path_keys:
        if key in config:
            resolved = resolve_path(config, key, project_root=project_root)
            paths.add(resolved)

    for key in template_keys:
        if key in config:
            resolved = resolve_template_path(
                config,
                key,
                {"player": player},
                project_root=project_root,
            )
            paths.add(resolved)

    if "memory_db_path_template" in config:
        memory_path = resolve_template_path(
            config,
            "memory_db_path_template",
            {"player": player},
            project_root=project_root,
        )
        paths.add(memory_path)

    for path in paths:
        try:
            if not path.exists():
                continue
            # Safety: do not delete directories. If a config key accidentally points
            # at a folder, fail safe (skip) rather than wiping contents.
            if path.is_dir():
                print(
                    f"--purge-data skipped directory path (expected file): {path}",
                    file=sys.stderr,
                )
                continue
            path.unlink()
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            print(
                f"--purge-data could not delete {path}: {exc}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"--purge-data error deleting {path}: {exc}",
                file=sys.stderr,
            )


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

    if args.purge_data:
        _purge_run_data(config)

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
        controller = GameController(config)
        controller.run()
    except Exception as exc:
        my_logging.system_log(f"Fatal error: {exc}")
        raise


if __name__ == "__main__":
    main()
