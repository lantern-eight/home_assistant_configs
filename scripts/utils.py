import logging
import os
import sys
from logging import Logger

from pythonjsonlogger import jsonlogger

# ANSI escape codes for level-based coloring (when stdout is a TTY)
_RESET = "\033[0m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"

_LEVEL_COLORS = {
    logging.CRITICAL: _RED,
    logging.ERROR: _RED,
    logging.WARNING: _YELLOW,
    logging.INFO: _GREEN,
    logging.DEBUG: _DIM,
}


class ColoredStreamHandler(logging.StreamHandler):
    """StreamHandler that colorizes the formatted log line by level when stream is a TTY."""

    def __init__(self, stream=None):
        super().__init__(stream or sys.stdout)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if self.stream and getattr(self.stream, "isatty", lambda: False)():
                color = _LEVEL_COLORS.get(record.levelno, _RESET)
                msg = f"{color}{msg}{_RESET}"
            if self.stream:
                self.stream.write(msg + self.terminator)
                self.flush()
        except Exception:
            self.handleError(record)


def init_logger() -> Logger:
    """Create and return a logger with JSON formatter and optional TTY coloring."""
    log_format = (
        "%(asctime)s %(levelname)s %(name)s %(message)s "
        "%(filename)s %(funcName)s %(lineno)d"
    )
    logger = logging.getLogger("ha_backup")
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    console_handler = ColoredStreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(log_format)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


LOGGER = init_logger()
