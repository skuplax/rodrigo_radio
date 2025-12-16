"""Centralized logging system with smart filtering and volume throttling."""
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

# Track last logged volume for throttling
_last_logged_volume: Optional[float] = None
_volume_threshold = 5.0  # Log volume changes >= 5%


def should_log_volume_change(new_volume: float, is_mute_toggle: bool = False) -> bool:
    """
    Public function to check if volume change should be logged.
    
    Args:
        new_volume: New volume percentage
        is_mute_toggle: Whether this is a mute/unmute event
        
    Returns:
        True if should log, False otherwise
    """
    return _should_log_volume_change(new_volume, is_mute_toggle)


def _should_log_volume_change(new_volume: float, is_mute_toggle: bool = False) -> bool:
    """
    Determine if a volume change should be logged.
    
    Only logs significant changes (>= 5%) or mute/unmute events.
    
    Args:
        new_volume: New volume percentage
        is_mute_toggle: Whether this is a mute/unmute event
        
    Returns:
        True if should log, False otherwise
    """
    global _last_logged_volume
    
    if is_mute_toggle:
        _last_logged_volume = new_volume
        return True
    
    if _last_logged_volume is None:
        _last_logged_volume = new_volume
        return True
    
    volume_diff = abs(new_volume - _last_logged_volume)
    if volume_diff >= _volume_threshold:
        _last_logged_volume = new_volume
        return True
    
    return False


def _should_filter_log(record: logging.LogRecord) -> bool:
    """
    Filter out redundant or unnecessary logs.
    
    Filters:
    - Meta-logging (logs about logging operations)
    - httpx internal logs
    - DEBUG logs in production
    
    Args:
        record: Log record to check
        
    Returns:
        True if should filter out, False if should log
    """
    msg = record.getMessage().lower()
    logger_name = record.name.lower()
    action = getattr(record, 'action', '').lower()
    
    # Filter meta-logging (logs about logging)
    if any(keyword in msg or keyword in logger_name or keyword in action 
           for keyword in ['supabase', 'log', 'synced', 'syncing', 'buffer']):
        # But allow ERROR logs about logging failures
        if record.levelno >= logging.ERROR:
            return False
        # Filter out INFO/DEBUG logs about logging operations
        if 'error' not in msg and 'failure' not in msg:
            return True
    
    # Filter httpx internal logs
    if 'httpx' in logger_name or 'httpx' in msg:
        if '_send_single_request' in action or '_send_single_request' in msg:
            return True
    
    # Filter DEBUG logs in production (keep for development)
    if record.levelno == logging.DEBUG:
        # Allow DEBUG logs if explicitly needed (can be configured)
        return False  # Keep DEBUG for now, can be made configurable
    
    return False


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    return logger


def log_volume_change(logger: logging.Logger, volume: float, is_mute_toggle: bool = False) -> bool:
    """
    Log a volume change if it's significant.
    
    Args:
        logger: Logger instance
        volume: New volume percentage
        is_mute_toggle: Whether this is a mute/unmute event
        
    Returns:
        True if logged, False if filtered out
    """
    if _should_log_volume_change(volume, is_mute_toggle):
        # Create a LogRecord with a proper action name to avoid meta-logging filter
        # Use extra parameter to set action
        if is_mute_toggle:
            logger.info(f"Volume mute toggle: {volume}%", extra={'action': 'volume_mute_toggle'})
        else:
            logger.info(f"Volume changed to {volume}%", extra={'action': 'volume_change'})
        return True
    return False


def get_current_timestamps() -> tuple[datetime, datetime]:
    """
    Get current UTC and local timestamps.
    
    Returns:
        Tuple of (utc_timestamp, local_timestamp)
    """
    utc_now = datetime.now(timezone.utc)
    local_now = utc_now.astimezone()
    return utc_now, local_now


def timestamp_from_float(unix_timestamp: float) -> tuple[datetime, datetime]:
    """
    Convert Unix timestamp (float) to UTC and local datetime objects.
    
    Args:
        unix_timestamp: Unix timestamp as float
        
    Returns:
        Tuple of (utc_timestamp, local_timestamp)
    """
    utc_dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    local_dt = utc_dt.astimezone()
    return utc_dt, local_dt
