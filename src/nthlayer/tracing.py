from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

import structlog
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.ext.httpx import patch as patch_httpx

logger = structlog.get_logger()

T = TypeVar("T", bound=Callable[..., Any])


def init_xray(service_name: str = "nthlayer") -> None:
    """Initialize X-Ray tracing."""
    try:
        xray_recorder.configure(service=service_name)
        patch_httpx()
        logger.info("xray_initialized", service=service_name)
    except Exception as exc:
        logger.warning("xray_init_failed", error=str(exc))


def trace_async(name: str | None = None) -> Callable[[T], T]:
    """Decorator to trace async functions with X-Ray."""

    def decorator(func: T) -> T:
        segment_name = name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                with xray_recorder.capture(segment_name):
                    return await func(*args, **kwargs)
            except Exception as exc:
                xray_recorder.current_subsegment().put_annotation("error", str(exc))
                raise

        return wrapper  # type: ignore

    return decorator
