import logging
from typing import Any

import structlog


def configure_logging(level: int | str = logging.INFO) -> None:
    """Configure structlog/standard logging bridge."""

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, format="%(message)s")


def bind_context(**kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Bind contextual fields for downstream logs."""

    logger = structlog.get_logger()
    return logger.bind(**kwargs)
