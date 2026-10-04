"""
In-memory event bus and SSE (Server-Sent Events) subscription broker for real-time vault mutations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Set

logger = logging.getLogger("capsule.sync.event_bus")


class EventBus:
    """Pub/sub event broker for live capsule updates."""

    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        logger.debug("New event subscriber connected (total: %d)", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)
        logger.debug("Subscriber disconnected (remaining: %d)", len(self._subscribers))

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts an event dictionary to all active subscribers."""
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full; dropping oldest event")
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("Failed to dispatch to subscriber: %s", exc)

    async def event_generator(self) -> AsyncGenerator[str, None]:
        """Async generator producing SSE-formatted data chunks."""
        q = self.subscribe()
        try:
            # Yield initial connection heartbeat
            init_msg = json.dumps({"status": "connected", "timestamp": datetime.now(timezone.utc).isoformat()})
            yield f"event: connect\ndata: {init_msg}\n\n"
            while True:
                payload = await q.get()
                event_type = payload.get("event", "message")
                data_str = json.dumps(payload.get("data", {}))
                yield f"event: {event_type}\ndata: {data_str}\n\n"
        finally:
            self.unsubscribe(q)


# Global singleton instance
vault_event_bus = EventBus()
