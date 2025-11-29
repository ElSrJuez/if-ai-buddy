import json
import logging
import os
from datetime import datetime
from typing import Any

_config: dict[str, Any] = {}
_SYSTEM_LOG_PATH = ""
_GAME_LOG_PATH = ""
_ENGINE_LOG_PATH = ""
_COMPLETIONS_LOG_PATH = ""
_debug_enabled = False

system_logger = logging.getLogger("mysystemlog")
game_logger = logging.getLogger("mygamelog")
engine_logger = logging.getLogger("myenginelog")
completions_logger = logging.getLogger("mycompletionslog")


def init(player_name: str, config_file: str = "config.json") -> None:
    """Initialize logging: ensures config-driven paths and log levels."""
    global _config, _SYSTEM_LOG_PATH, _GAME_LOG_PATH, _ENGINE_LOG_PATH, _COMPLETIONS_LOG_PATH, _debug_enabled
    with open(config_file, "r", encoding="utf-8") as f:
        _config = json.load(f)

    log_level = _resolve_log_level(_require("loglevel"))
    _debug_enabled = log_level <= logging.DEBUG

    _SYSTEM_LOG_PATH = str(_require("system_log"))
    _GAME_LOG_PATH = str(_require("game_jsonl"))
    _ENGINE_LOG_PATH = _format_template(
        _require("game_engine_jsonl_filename_template"), player_name
    )
    _COMPLETIONS_LOG_PATH = _format_template(
        _require("llm_completion_jsonl_filename_template"), player_name
    )

    _ensure_parent_dir(_SYSTEM_LOG_PATH)
    _ensure_parent_dir(_GAME_LOG_PATH)
    _ensure_parent_dir(_ENGINE_LOG_PATH)
    _ensure_parent_dir(_COMPLETIONS_LOG_PATH)

    _configure_logger(system_logger, _SYSTEM_LOG_PATH, log_level, text_format=True)
    _configure_logger(game_logger, _GAME_LOG_PATH, logging.DEBUG)
    _configure_logger(engine_logger, _ENGINE_LOG_PATH, logging.DEBUG)
    _configure_logger(completions_logger, _COMPLETIONS_LOG_PATH, logging.DEBUG)


def _configure_logger(logger: logging.Logger, path: str, level: int, *, text_format: bool = False) -> None:
    logger.handlers.clear()
    logger.setLevel(level)
    handler = logging.FileHandler(path, encoding="utf-8")
    if text_format:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False


def _require(key: str) -> Any:
    if key not in _config:
        raise ValueError(f"Missing '{key}' in configuration file")
    return _config[key]


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _format_template(template: str, player_name: str) -> str:
    return template.format(player=player_name)


def _resolve_log_level(value: Any) -> int:
    name = str(value).upper()
    if not hasattr(logging, name):
        raise ValueError(f"Invalid loglevel '{value}' in configuration")
    level = getattr(logging, name)
    if not isinstance(level, int):
        raise ValueError(f"Invalid loglevel '{value}' in configuration")
    return level


def is_debug_enabled() -> bool:
    return _debug_enabled


def system_log(message: str) -> None:
    system_logger.error(str(message))


def system_warn(message: str) -> None:
    system_logger.warning(str(message))


def system_info(message: str) -> None:
    system_logger.info(str(message))


def system_debug(message: str) -> None:
    if _debug_enabled:
        system_logger.debug(str(message))


def game_log_json(data: dict) -> None:
    _game_log_json(data)


def log_player_input(command: str, *, pid: int | None = None) -> None:
    if not _debug_enabled:
        return
    _engine_log_json({"type": "input", "command": command, "pid": pid})


def log_player_output(transcript: str, *, pid: int | None = None) -> None:
    if not _debug_enabled:
        return
    _engine_log_json({"type": "output", "transcript": transcript, "pid": pid})


def log_completion_event(event: dict) -> None:
    if not _debug_enabled:
        return
    event = dict(event)
    event["timestamp"] = _timestamp()
    completions_logger.info(json.dumps(event))


def _game_log_json(data: dict) -> None:
    entry = dict(data)
    entry["timestamp"] = _timestamp()
    game_logger.info(json.dumps(entry))


def _engine_log_json(data: dict) -> None:
    entry = dict(data)
    entry["timestamp"] = _timestamp()
    engine_logger.info(json.dumps(entry))


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"