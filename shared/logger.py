import logging
import sys

from shared.constants import APP_NAME


def get_logger(name: str = APP_NAME) -> logging.Logger:
    """Return a configured logger instance.

    Uses a simple format for development. Swap the formatter for
    `python-json-logger` in production to get structured JSON output.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # avoid duplicate handlers on re-import

    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


logger = get_logger()
