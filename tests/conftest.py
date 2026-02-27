"""Root test configuration."""

import logging

import structlog


def pytest_configure(config):
    """Configure structlog for tests to suppress debug/info output."""
    logging.basicConfig(level=logging.WARNING, force=True)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
