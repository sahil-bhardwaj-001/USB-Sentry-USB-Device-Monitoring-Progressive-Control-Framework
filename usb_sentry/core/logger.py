import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from rich.logging import RichHandler
from rich.console import Console
from platformdirs import user_log_dir

# Setup rich console
console = Console()

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'value'):  # Handle Enums
            return obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name
        }
        
        # Include specific fields used in auditing
        for key in ['event', 'src', 'dest', 'path', 'device_info', 'user']:
            if hasattr(record, key):
                 log_obj[key] = getattr(record, key)
                 
        return json.dumps(log_obj, cls=CustomJSONEncoder)

def setup_logger(name: str = "usb_sentry", verbose: bool = False):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    
    # Local log dir relative to the package
    base_dir = Path(__file__).parent.parent
    
    # Determine platform subfolder
    if sys.platform == 'win32':
        platform_subfolder = "windows"
    elif sys.platform == 'linux':
        platform_subfolder = "linux"
    else:
        platform_subfolder = "other"

    log_dir = base_dir / "logs" / platform_subfolder
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "usb_sentry.json.log"

    # File Handler (JSON)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # Console Handler (Rich)
    console_handler = RichHandler(console=console, markup=True)
    logger.addHandler(console_handler)

    return logger, log_file

logger, log_file_path = setup_logger()
