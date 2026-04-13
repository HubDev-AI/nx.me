"""Async helpers for blocking SDK calls.

The supabase-py SDK's .execute() is synchronous (blocking I/O).
When called from async def handlers, it blocks the asyncio event loop.
This module provides a wrapper to run blocking calls in a thread pool.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Callable, TypeVar

T = TypeVar("T")


async def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """Run a blocking function in the default executor (thread pool).

    Usage:
        result = await run_sync(repo.get_user, username)
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
