"""
Configuration Manager for FA CS Automator

Handles loading configuration from user-accessible config files.
This allows deployed applications to be configured without modifying code.

Config file locations (checked in order):
1. ./config.json (next to executable)
2. %APPDATA%/FA CS Automator/config.json (Windows)
3. ~/.config/fa-cs-automator/config.json (Linux/Mac)

If no config file exists, a template is created on first run.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Default configuration template
DEFAULT_CONFIG = {
    "_comment": "FA CS Automator Configuration - Edit this file to configure the application",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "use_ai_classification": True,
    "fallback_to_rules": True,
    "log_level": "INFO",
    "server_port": 8000,
}


def get_config_paths() -> list[Path]:
    """Get list of possible config file locations, in priority order."""
    paths = []

    # 1. Next to executable (for packaged app)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / "config.json")
        # Also check parent for electron app structure (resources folder)
        paths.append(exe_dir.parent / "config.json")
        paths.append(exe_dir.parent.parent / "config.json")
        # Electron resources path
        paths.append(exe_dir.parent.parent.parent / "config.json")

    # 2. Current working directory
    paths.append(Path.cwd() / "config.json")

    # 3. Platform-specific user config directory
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA')
        if appdata:
            paths.append(Path(appdata) / "FA CS Automator" / "config.json")
    else:
        # Linux/Mac
        home = Path.home()
        paths.append(home / ".config" / "fa-cs-automator" / "config.json")

    # 4. Next to api.py (development)
    paths.append(Path(__file__).parent.parent / "config.json")

    return paths


def get_template_path() -> Optional[Path]:
    """Find the config template file."""
    template_paths = []

    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        template_paths.extend([
            exe_dir / "config.template.json",
            exe_dir.parent / "config.template.json",
            exe_dir.parent.parent / "config.template.json",
            exe_dir.parent.parent.parent / "config.template.json",
        ])

    template_paths.append(Path(__file__).parent.parent / "config.template.json")

    for path in template_paths:
        if path.exists():
            return path
    return None


def find_config_file() -> Optional[Path]:
    """Find the first existing config file."""
    for path in get_config_paths():
        if path.exists():
            logger.info(f"Found config file: {path}")
            return path
    return None


def get_default_config_path() -> Path:
    """Get the default path where config should be created."""
    if getattr(sys, 'frozen', False):
        # Packaged app - create next to executable
        return Path(sys.executable).parent / "config.json"
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            config_dir = Path(appdata) / "FA CS Automator"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "config.json"

    # Fallback to home directory
    if sys.platform == 'win32':
        config_dir = Path.home() / "FA CS Automator"
    else:
        config_dir = Path.home() / ".config" / "fa-cs-automator"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def create_config_template(path: Path) -> None:
    """Create a config template file."""
    import shutil

    path.parent.mkdir(parents=True, exist_ok=True)

    # Try to copy from bundled template first
    template_path = get_template_path()
    if template_path and template_path.exists():
        shutil.copy(template_path, path)
        logger.info(f"Created config from template at: {path}")
    else:
        # Fall back to default config
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        logger.info(f"Created default config at: {path}")

    logger.info("Please edit this file to add your OpenAI API key")


def load_config() -> Dict[str, Any]:
    """
    Load configuration from file.
    Creates a template if no config exists.
    Returns merged config (file + defaults).
    """
    config = DEFAULT_CONFIG.copy()

    config_path = find_config_file()

    if config_path is None:
        # No config file found - create template
        default_path = get_default_config_path()
        logger.warning(f"No config file found. Creating template at: {default_path}")
        create_config_template(default_path)
        config_path = default_path

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            file_config = json.load(f)

        # Merge file config with defaults
        for key, value in file_config.items():
            if not key.startswith('_'):  # Skip comments
                config[key] = value

        logger.info(f"Loaded config from: {config_path}")

    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")

    return config


def apply_config_to_environment(config: Dict[str, Any]) -> None:
    """
    Apply config values to environment variables.
    This ensures compatibility with existing code that reads from env.
    """
    env_mappings = {
        'openai_api_key': 'OPENAI_API_KEY',
        'openai_model': 'OPENAI_MODEL',
        'log_level': 'LOG_LEVEL',
        'server_port': 'SERVER_PORT',
        'tax_rules_s3_bucket': 'TAX_RULES_S3_BUCKET',
        'tax_rules_s3_key': 'TAX_RULES_S3_KEY',
        'tax_rules_s3_region': 'TAX_RULES_S3_REGION',
    }

    for config_key, env_key in env_mappings.items():
        if config_key in config and config[config_key]:
            # Only set if not already set (env vars take precedence)
            if not os.environ.get(env_key):
                os.environ[env_key] = str(config[config_key])
                logger.debug(f"Set {env_key} from config file")


def initialize_config() -> Dict[str, Any]:
    """
    Main entry point - load config and apply to environment.
    Call this early in application startup.
    """
    config = load_config()
    apply_config_to_environment(config)

    # Log config status (without sensitive values)
    has_api_key = bool(config.get('openai_api_key') or os.environ.get('OPENAI_API_KEY'))
    logger.info(f"Config initialized - OpenAI API key: {'configured' if has_api_key else 'NOT CONFIGURED'}")

    if not has_api_key:
        logger.warning("OpenAI API key not configured. AI classification will use fallback rules.")
        logger.warning(f"To configure, edit: {find_config_file() or get_default_config_path()}")

    return config


# Singleton config instance
_config: Optional[Dict[str, Any]] = None


def get_config() -> Dict[str, Any]:
    """Get the current config (loads if not already loaded)."""
    global _config
    if _config is None:
        _config = initialize_config()
    return _config
