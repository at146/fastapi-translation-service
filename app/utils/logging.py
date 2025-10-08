import logging
import pathlib
from logging.config import dictConfig

LOGGER_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "basic": {
            "class": "logging.Formatter",
            "datefmt": "%d-%m-%Y %H:%M:%S",
            "format": "%(asctime)s (%(name)s:%(filename)s:%(lineno)d) %(levelname)s - %(message)s",  # noqa: E501
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "basic",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "level": "DEBUG",
            "formatter": "basic",
            "filename": "logs/log.log",
            "when": "midnight",
            "backupCount": 31,
            "encoding": "utf-8",
        },
        "error_file": {
            "class": "logging.FileHandler",
            "level": "WARNING",
            "formatter": "basic",
            "filename": "logs/error_log.log",
            "mode": "a",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "": {
            "handlers": ["file", "error_file", "console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


def setup_logger() -> logging.Logger:
    pathlib.Path("logs").mkdir(parents=True, exist_ok=True)
    dictConfig(LOGGER_CONFIG)
    return logging.getLogger(__name__)
