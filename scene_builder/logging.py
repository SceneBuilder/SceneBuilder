"""Logging configuration for SceneBuilder."""

import sys

import logfire
from loguru import logger

from .config import LOGFIRE_SERVICE_NAME


def configure_logging(level="INFO", sink=sys.stderr, format="{level: <9} {message}", enable_logfire=True):
    """
    Configures the Loguru logger and optionally Pydantic Logfire.

    This function removes the default Loguru handler and adds a new one with
    the specified parameters, providing a simple way to set up logging.

    Args:
        level (str, optional): The minimum logging level to output.
            Defaults to "INFO".
        sink (file-like object, optional): The destination for logs.
            Defaults to `sys.stderr`.
        format (str, optional): The Loguru format string for the log messages.
            Defaults to "{level: <9} {message}".
        enable_logfire (bool, optional): Whether to enable Logfire integration.
            Defaults to True.

    Returns:
        The configured logger instance.
    """
    logger.remove()
    logger.add(sink, format=format, level=level)
    
    if enable_logfire:
        logfire.configure(
            send_to_logfire='if-token-present',
            service_name=LOGFIRE_SERVICE_NAME,
        )
        logfire.instrument_pydantic_ai()
        logger.info(f"Logfire instrumentation enabled for Pydantic AI (service: {LOGFIRE_SERVICE_NAME})")
    
    return logger
