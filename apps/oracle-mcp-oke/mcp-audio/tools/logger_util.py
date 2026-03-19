import logging
import os


_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    """Configure global logging once with consistent column-style format."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    )
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger with standard configuration applied."""
    configure_logging()
    return logging.getLogger(name)
