import logging
import os
from pathlib import Path
from typing import Optional

def get_log_level(level_name: str) -> int:
    """Convert log level name to logging constant."""
    return {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }.get(level_name.lower(), logging.INFO)

def setup_logging(log_level: int = logging.INFO, log_file: Optional[str] = None, console_logging: bool = True) -> None:
    """Configure logging for the application.
    
    Args:
        log_level: The logging level to use (e.g. logging.DEBUG, logging.INFO, etc.)
                  Default is INFO level.
        log_file: Optional path to log file. If provided, logs will be written to file.
                 If None, only console logging is used (unless console_logging=False).
        console_logging: Whether to log to console. If False, only logs to file.
                        Default is True.
    """
    # Clear any existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set up handlers based on configuration
    handlers = []
    
    # Set up console handler if console_logging is enabled
    if console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    # Set up file handler if log_file is provided
    if log_file:
        # Ensure log file directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # If no handlers are configured, we need at least one to avoid issues
    if not handlers:
        # Create a null handler to prevent any logging output
        null_handler = logging.NullHandler()
        handlers.append(null_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True  # Force reconfiguration
    )
    
    # Optionally silence some chatty libraries
    # logging.getLogger('httpx').setLevel(logging.WARNING)
    # logging.getLogger('openai').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)  # return logger
