"""Logging utilities for debugging and monitoring."""

import logging
from typing import List
from datetime import datetime


def setup_debug_logging(verbose: bool = False) -> logging.Logger:
    """Set up debug logging with timestamped files."""
    if not verbose:
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"debug_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def log_validation_signals(signals: List[str], url: str, logger: logging.Logger):
    """Log validation failure signals."""
    if not logger:
        return
        
    logger.debug(f"Validation signals for {url}: {', '.join(signals)}")


def log_http_validation(status_code: int, final_url: str, url: str, logger: logging.Logger):
    """Log HTTP validation details."""
    if not logger:
        return
        
    logger.debug(f"HTTP validation for {url}: status={status_code}, final_url={final_url}")