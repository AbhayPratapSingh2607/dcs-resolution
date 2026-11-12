from __future__ import annotations

from asyncio import Queue
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from game.sim import GameUpdateEvents


class EventStream:
    _queue: Queue[GameUpdateEvents] = Queue()
    #: An update taken off the queue that couldn't be merged; sent next.
    _carry: Optional[GameUpdateEvents] = None

    @classmethod
    def drain(cls) -> None:
        cls._carry = None
        while not cls._queue.empty():
            cls._queue.get_nowait()
            cls._queue.task_done()

    @classmethod
    async def put(cls, events: GameUpdateEvents) -> None:
        await cls._queue.put(events)

    @classmethod
    def put_nowait(cls, events: GameUpdateEvents) -> None:
        # The queue has infinite size so this should never need to block anyway. If for
        # some reason the queue is full this will throw QueueFull.
        cls._queue.put_nowait(events)

    @classmethod
    async def get(cls) -> GameUpdateEvents:
        events = await cls._queue.get()
        cls._queue.task_done()
        return events

    @classmethod
    async def get_merged(cls) -> GameUpdateEvents:
        """The next update, with every mergeable update queued behind it
        folded in. While fast forwarding the sim queues updates faster than
        the map can take them; sending them one by one made the map fall
        further and further behind."""
        if cls._carry is not None:
            events, cls._carry = cls._carry, None
        else:
            events = await cls.get()
        if not events.mergeable:
            return events
        while not cls._queue.empty():
            later = cls._queue.get_nowait()
            cls._queue.task_done()
            if not later.mergeable:
                cls._carry = later
                break
            events.merge(later)
        return events

    @staticmethod
    @contextmanager
    def event_context() -> Iterator[GameUpdateEvents]:
        events = GameUpdateEvents()
        yield events
        EventStream.put_nowait(events)
