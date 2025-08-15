"""Logging configuration for SceneBuilder."""

import sys

from loguru import logger


def configure_logging(level="INFO", sink=sys.stderr, format="{level: <9} {message}"):
    """
    Configures the Loguru logger.

    This function removes the default Loguru handler and adds a new one with
    the specified parameters, providing a simple way to set up logging.

    Args:
        level (str, optional): The minimum logging level to output.
            Defaults to "INFO".
        sink (file-like object, optional): The destination for logs.
            Defaults to `sys.stderr`.
        format (str, optional): The Loguru format string for the log messages.
            Defaults to "{level: <9} {message}".

    Returns:
        The configured logger instance.
    """
    logger.remove()
    logger.add(sink, format=format, level=level)
    return logger
