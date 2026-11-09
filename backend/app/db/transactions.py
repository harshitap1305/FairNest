"""MongoDB multi-document transaction helper."""

from __future__ import annotations

from typing import Any, Awaitable, Callable


async def run_in_txn(client, callback: Callable[..., Awaitable[Any]]) -> Any:
    """
    Run callback(session) inside a retrying transaction.

    PyMongo's AsyncClientSession.with_transaction() handles:
    - Transient transaction errors (automatically retried)
    - Unknown commit errors (commit retried)
    """
    async with client.start_session() as session:
        return await session.with_transaction(callback)
