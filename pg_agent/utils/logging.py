import logging

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