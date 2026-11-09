"""MongoDB async client management."""

from __future__ import annotations

import inspect

from pymongo import AsyncMongoClient

_client: AsyncMongoClient | None = None


async def connect_db(uri: str) -> None:
    """Create and store the global AsyncMongoClient."""
    global _client
    _client = AsyncMongoClient(uri, w="majority", tz_aware=True)


async def close_db() -> None:
    """Close the global client if it exists."""
    global _client
    if _client is not None:
        res = _client.close()
        if inspect.isawaitable(res):
            await res
        _client = None


def get_client() -> AsyncMongoClient:
    """Return the raw client (needed for transaction sessions)."""
    if _client is None:
        raise RuntimeError("Database client not initialised. Call connect_db() first.")
    return _client


def get_db(db_name: str):
    """Return a MongoDB database handle."""
    if _client is None:
        raise RuntimeError("Database client not initialised. Call connect_db() first.")
    return _client[db_name]
