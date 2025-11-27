import os
import json
from datetime import datetime
import logging

# init log file names
_GAME_LOG_FILENAME = ""
_SYSTEM_LOG_FILENAME = ""

# Module-level loggers for system and game logs
game_logger = logging.getLogger('mygamelog')
system_logger = logging.getLogger('mysystemlog')

# Remove manual filename globals

def init(player_name: str, config_file: str = "config.json") -> None:
    """Initialize logging: loads config, ensures log directory, and configures log handlers."""
    global _config, _GAME_LOG_FILENAME, _SYSTEM_LOG_FILENAME
    # Load configuration
    with open(config_file, 'r', encoding='utf-8') as f:
        _config = json.load(f)
    # Determine log directory
    log_dir = _config.get("input_jsonl_path", "")
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    # Setup log file paths
    _GAME_LOG_FILENAME = os.path.join(log_dir, f"{player_name}.jsonl")
    _SYSTEM_LOG_FILENAME = os.path.join(log_dir, f"{player_name}.log")
    # Clear existing handlers
    for handler in list(game_logger.handlers):
        game_logger.removeHandler(handler)
    for handler in list(system_logger.handlers):
        system_logger.removeHandler(handler)
    # Configure game logger (JSON lines)
    game_logger.setLevel(logging.INFO)
    gh = logging.FileHandler(_GAME_LOG_FILENAME, encoding='utf-8')
    gh.setFormatter(logging.Formatter('%(message)s'))
    game_logger.addHandler(gh)
    game_logger.propagate = False
    # Configure system logger (timestamped text)
    system_logger.setLevel(logging.INFO)
    sh = logging.FileHandler(_SYSTEM_LOG_FILENAME, encoding='utf-8')
    sh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    system_logger.addHandler(sh)
    system_logger.propagate = False

def game_log(message: str) -> None:
    """Log a game message as JSON with timestamp."""
    # Create JSON structure for message
    data = {
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    game_logger.info(json.dumps(data))

def system_log(message: str) -> None:
    """Log a system message with timestamp."""
    system_logger.info(str(message))

def game_log_json(data: dict) -> None:
    """Log a game message as JSON with timestamp."""
    data["timestamp"] = datetime.utcnow().isoformat() + 'Z'
    game_logger.info(json.dumps(data))