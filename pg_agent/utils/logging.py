import logging

def get_log_level(level_name: str) -> int:
    """Convert log level name to logging constant."""
    return {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }.get(level_name.lower(), logging.INFO)

def setup_logging(log_level: int = logging.INFO) -> None:
    """Configure logging for the application.
    
    Args:
        log_level: The logging level to use (e.g. logging.DEBUG, logging.INFO, etc.)
                  Default is INFO level.
    """
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Optionally silence some chatty libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING) 