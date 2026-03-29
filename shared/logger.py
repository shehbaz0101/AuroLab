"""
shared/logger.py

Structured logging configuration for AuroLab.
Uses structlog with JSON output in production, human-readable in development.

Usage (in any service):
    from shared.logger import get_logger
    log = get_logger(__name__)
    log.info("event_name", key="value", count=42)
"""

from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging() -> None:
    """
    Call once at application startup (in main.py lifespan).
    Sets up structlog processors for the chosen environment.
    """
    env = os.getenv("ENV", "prod").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Shared processors for all environments
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    if env == "dev":
        # Human-readable coloured output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
        )
    else:
        # JSON output for production (log aggregators, CloudWatch, etc.)
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to route through structlog
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers
    for noisy in ["httpx", "httpcore", "chromadb", "urllib3", "multipart"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a bound logger for a module."""
    return structlog.get_logger(name)