import yaml
from pathlib import Path
from typing import Any, Dict

# Default configuration if file is missing
DEFAULT_CONFIG = {
    "app": {
        "name": "USB Sentry",
        "version": "1.0.0"
    },
    "interactive": {
        "geometry": "100x30",
        "theme": "default"
    },
    "logging": {
        "level": "INFO",
        "console_output": True
    }
}

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    Falls back to defaults if file is missing or invalid.
    """
    # Try to find config.yaml in the project root
    # this file: usb_sentry/core/config.py
    # project root: usb_sentry/core/../../
    
    base_dir = Path(__file__).resolve().parent.parent.parent
    file_path = base_dir / config_path

    if not file_path.exists():
        return DEFAULT_CONFIG

    try:
        with open(file_path, "r") as f:
            config = yaml.safe_load(f)
            if not config:
                return DEFAULT_CONFIG
            
            # Merge with defaults
            merged = DEFAULT_CONFIG.copy()
            
            def deep_update(d, u):
                for k, v in u.items():
                    if isinstance(v, dict):
                        d[k] = deep_update(d.get(k, {}), v)
                    else:
                        d[k] = v
                return d
            
            return deep_update(merged, config)
            
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG

# Global config instance
config = load_config()
