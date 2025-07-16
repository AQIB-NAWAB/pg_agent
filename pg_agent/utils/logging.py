import logging

def setup_logging(verbose: bool):
    """Configure logging based on verbosity level.
    
    Args:
        verbose (bool): If True, sets logging level to INFO, otherwise WARNING
    """
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(),  # Console output only
        ]
    ) 