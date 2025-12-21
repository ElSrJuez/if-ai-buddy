import json
import logging
import os
from datetime import datetime
from typing import Any, Mapping

_config: dict[str, Any] = {}
_SYSTEM_LOG_PATH = ""
_GAME_LOG_PATH = ""
_ENGINE_LOG_PATH = ""
_COMPLETIONS_LOG_PATH = ""
_REST_LOG_PATH = ""
_GAMEAPI_LOG_PATH = ""
_ENGINE_TEMPLATE = ""
_COMPLETIONS_TEMPLATE = ""
_current_player = ""
_debug_enabled = False

system_logger = logging.getLogger("mysystemlog")
game_logger = logging.getLogger("mygamelog")
engine_logger = logging.getLogger("myenginelog")
completions_logger = logging.getLogger("mycompletionslog")
rest_logger = logging.getLogger("myrestlog")
# Logger for GameAPI events
gameapi_logger = logging.getLogger("mygameapilog")


def init(
    player_name: str,
    *,
    config: Mapping[str, Any] | None = None,
    config_file: str | None = "config.json",
) -> None:
    """Initialize logging: ensures config-driven paths and log levels."""
    global _config, _SYSTEM_LOG_PATH, _GAME_LOG_PATH, _ENGINE_LOG_PATH, _COMPLETIONS_LOG_PATH
    global _REST_LOG_PATH, _GAMEAPI_LOG_PATH, _ENGINE_TEMPLATE, _COMPLETIONS_TEMPLATE
    global _current_player, _debug_enabled
    if config is None:
        if not config_file:
            raise ValueError("Either config or config_file must be provided")
        from module import my_config as _my_config

        loaded = _my_config.load_config(config_file)
    else:
        loaded = dict(config)

    _config = loaded

    log_level = _resolve_log_level(_require("loglevel"))
    _debug_enabled = log_level <= logging.DEBUG

    _SYSTEM_LOG_PATH = str(_require("system_log"))
    _GAME_LOG_PATH = str(_require("gameapi_jsonl"))
    _REST_LOG_PATH = str(_require("rest_jsonl"))
    _GAMEAPI_LOG_PATH = _GAME_LOG_PATH
    _ENGINE_TEMPLATE = str(_require("game_engine_jsonl_filename_template"))
    _COMPLETIONS_TEMPLATE = str(_require("llm_completion_jsonl_filename_template"))

    _init_player_scoped_logs(player_name)

    _ensure_parent_dir(_SYSTEM_LOG_PATH)
    _ensure_parent_dir(_GAME_LOG_PATH)
    _ensure_parent_dir(_REST_LOG_PATH)

    _configure_logger(system_logger, _SYSTEM_LOG_PATH, log_level, text_format=True)
    _configure_logger(game_logger, _GAME_LOG_PATH, logging.DEBUG)
    _configure_logger(rest_logger, _REST_LOG_PATH, logging.DEBUG)
    # Configure GameAPI JSONL logging
    _configure_logger(gameapi_logger, _GAMEAPI_LOG_PATH, logging.DEBUG)


def _init_player_scoped_logs(player_name: str) -> None:
    global _ENGINE_LOG_PATH, _COMPLETIONS_LOG_PATH, _current_player
    if not _ENGINE_TEMPLATE or not _COMPLETIONS_TEMPLATE:
        raise RuntimeError("Logging templates have not been initialized")

    engine_path = _format_template(_ENGINE_TEMPLATE, player_name)
    completions_path = _format_template(_COMPLETIONS_TEMPLATE, player_name)

    _ensure_parent_dir(engine_path)
    _ensure_parent_dir(completions_path)

    _ENGINE_LOG_PATH = engine_path
    _COMPLETIONS_LOG_PATH = completions_path
    _current_player = player_name

    _configure_logger(engine_logger, _ENGINE_LOG_PATH, logging.DEBUG)
    _configure_logger(completions_logger, _COMPLETIONS_LOG_PATH, logging.DEBUG)


def update_player_logs(player_name: str) -> None:
    """Re-open engine/completion JSONL files when the player name changes."""
    my_logging_msg = f"Reinitializing player-scoped logs for '{player_name}'"
    system_info(my_logging_msg)
    _init_player_scoped_logs(player_name)


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
    """Log player command input.
    
    Base: Always log command summary.
    Debug: Additionally log full transcript context.
    """
    # Always log minimal event result
    _engine_log_json({"type": "input", "command": command, "pid": pid})
    # Debug tier: full transcript context already captured in output log


def log_player_output(transcript: str, *, pid: int | None = None) -> None:
    """Log engine output transcript.
    
    Base: Always log transcript summary.
    Debug: Full transcript already captured.
    """
    # Always log minimal event result
    _engine_log_json({"type": "output", "transcript": transcript, "pid": pid})


def log_completion_event(event: dict) -> None:
    """Log LLM completion event.
    
    Base: Always log model, latency, success/failure.
    Debug: Additionally log full payload and diagnostics.
    """
    entry = dict(event)
    entry["timestamp"] = _timestamp()
    
    # Always log minimal result: model, latency, key payload fields
    minimal_entry = {
        "timestamp": entry["timestamp"],
        "model": entry.get("model"),
        "latency": entry.get("latency"),
        "tokens": entry.get("tokens"),
    }
    completions_logger.info(json.dumps(minimal_entry))
    
    # Debug tier: include full details
    if _debug_enabled:
        debug_entry = dict(entry)
        debug_entry["_debug_full_event"] = True
        completions_logger.info(json.dumps(debug_entry))
    
    # Flush immediately to ensure disk write
    for handler in completions_logger.handlers:
        handler.flush()


def _ensure_logger_ready(logger: logging.Logger, fallback_path: str) -> None:
    """Ensure a logger has at least one handler, using a fallback path if needed."""
    if not logger.handlers:
        # Logger not configured yet; add a fallback handler
        _ensure_parent_dir(fallback_path)
        handler = logging.FileHandler(fallback_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False


def _game_log_json(data: dict) -> None:
    entry = dict(data)
    entry["timestamp"] = _timestamp()
    game_logger.info(json.dumps(entry))


def _engine_log_json(data: dict) -> None:
    entry = dict(data)
    entry["timestamp"] = _timestamp()
    # Safety net: ensure logger has handlers, even if init() wasn't called yet
    _ensure_logger_ready(engine_logger, _ENGINE_LOG_PATH or "log/game_engine.jsonl")
    engine_logger.info(json.dumps(entry))
    # Flush immediately to ensure disk write
    for handler in engine_logger.handlers:
        handler.flush()


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ------ Two-tier logging: Base (always) + Debug (when enabled) ------

def log_rest_event(event: dict) -> None:
    """Log REST helper event (request/response).
    
    Base: Always log method, url, status_code.
    Debug: Additionally log full payload and response body.
    """
    entry = dict(event)
    entry["timestamp"] = _timestamp()
    
    # Safety net: ensure logger has handlers, even if init() wasn't called yet
    _ensure_logger_ready(rest_logger, _REST_LOG_PATH or "log/rest_helper.jsonl")
    
    # Always log minimal result: method, url, status (if response)
    minimal_entry = {
        "timestamp": entry["timestamp"],
        "stage": entry.get("stage"),
        "method": entry.get("method"),
        "url": entry.get("url"),
        "status_code": entry.get("status_code"),
    }
    rest_logger.info(json.dumps(minimal_entry))
    
    # Debug tier: include full request/response payloads
    if _debug_enabled:
        debug_entry = dict(entry)
        debug_entry["_debug_full_event"] = True
        rest_logger.info(json.dumps(debug_entry))
    
    # Flush immediately to ensure disk write
    for handler in rest_logger.handlers:
        handler.flush()


def log_gameapi_event(event: Mapping[str, Any]) -> None:
    """Log GameAPI event (parsed request/response).
    
    Base: Always log command and parsed metadata outcome.
    Debug: Additionally log full request/response stages with payloads.
    """
    entry = dict(event)
    entry["timestamp"] = _timestamp()
    stage = entry.get("stage", "unknown")
    
    # Safety net: ensure logger has handlers, even if init() wasn't called yet
    _ensure_logger_ready(gameapi_logger, _GAMEAPI_LOG_PATH or "log/gameapi.jsonl")
    
    if stage == "parsed":
        # Always log the parsed outcome: what we extracted and concluded
        minimal_entry = {
            "timestamp": entry["timestamp"],
            "stage": "parsed",
            "command": entry.get("command"),
            "pid": entry.get("pid"),
            "metadata": entry.get("metadata"),  # room, score, moves, inventory, exception info
        }
        gameapi_logger.info(json.dumps(minimal_entry))
        
        # Debug tier: include request and response details
        if _debug_enabled:
            debug_entry = dict(entry)
            debug_entry["_debug_full_event"] = True
            gameapi_logger.info(json.dumps(debug_entry))
        
        # Flush immediately to ensure disk write
        for handler in gameapi_logger.handlers:
            handler.flush()
    elif _debug_enabled:
        # For request/response stages, only log if debug is enabled
        gameapi_logger.info(json.dumps(entry))
        # Flush immediately to ensure disk write
        for handler in gameapi_logger.handlers:
            handler.flush()


def log_memory_event(event_type: str, data: Mapping[str, Any] | None = None) -> None:
    """Log a memory-related event (episodic turn, state update, etc.) to game JSONL."""
    entry = dict(data or {})
    entry["type"] = event_type
    if _current_player:
        entry.setdefault("player", _current_player)
    _game_log_json(entry)


def log_memory_conflict(description: str, evidence: str) -> None:
    """Log a memory conflict (contradiction between state and game output)."""
    system_warn(f"Memory conflict: {description} (evidence: {evidence})")
    log_memory_event(
        "conflict",
        {
            "description": description,
            "evidence": evidence,
        },
    )


def log_state_change(field: str, old_value: Any, new_value: Any) -> None:
    """Log a state field change."""
    log_memory_event(
        "state_change",
        {
            "field": field,
            "old_value": str(old_value)[:100],
            "new_value": str(new_value)[:100],
        },
    )
