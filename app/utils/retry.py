"""Exponential backoff and retry helper for network requests."""

import asyncio
import random
import logging
from typing import Callable, Any, TypeVar, Coroutine
import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_statuses: tuple = (429, 500, 502, 503, 504),
    **kwargs: Any
) -> T:
    """Execute an async function with exponential backoff and randomized jitter on rate-limits."""
    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            last_exception = e
            if e.response.status_code in retry_statuses and attempt < max_retries:
                jitter = random.uniform(0.1, 0.5)
                wait_time = (delay * (backoff_factor ** (attempt - 1))) + jitter
                logger.warning(
                    f"Received HTTP {e.response.status_code} (Rate Limit / Server Error). "
                    f"Retrying in {wait_time:.2f}s (Attempt {attempt}/{max_retries})..."
                )
                await asyncio.sleep(wait_time)
            else:
                raise
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, OSError) as e:
            last_exception = e
            if attempt < max_retries:
                jitter = random.uniform(0.1, 0.5)
                wait_time = (delay * (backoff_factor ** (attempt - 1))) + jitter
                logger.warning(f"Network / DNS glitch ({e}). Retrying in {wait_time:.2f}s (Attempt {attempt}/{max_retries})...")
                await asyncio.sleep(wait_time)
            else:
                raise
        except Exception as e:
            # Non-network error, don't retry blindly
            raise e

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop termination")
