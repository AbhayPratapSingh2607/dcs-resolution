"""The map stream folds queued updates into one, so the map doesn't fall behind
a fast forward."""

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from game.server.eventstream.eventstream import EventStream
from game.sim.gameupdateevents import GameUpdateEvents


def _flight() -> Any:
    return SimpleNamespace(id=uuid4())


def _drain() -> list[GameUpdateEvents]:
    async def run() -> list[GameUpdateEvents]:
        out = []
        while EventStream._carry is not None or not EventStream._queue.empty():
            out.append(await EventStream.get_merged())
        return out

    return asyncio.run(run())


def test_queued_position_updates_merge_into_one() -> None:
    EventStream.drain()
    flight = _flight()
    for x in range(5):
        EventStream.put_nowait(
            GameUpdateEvents().update_flight_position(flight, (x, 0))  # type: ignore[arg-type]
        )
    sent = _drain()
    assert len(sent) == 1
    assert sent[0].updated_flight_positions[-1] == (flight, (4, 0))


def test_a_new_turn_is_not_merged() -> None:
    EventStream.drain()
    flight = _flight()
    EventStream.put_nowait(GameUpdateEvents().update_flight_position(flight, (1, 0)))  # type: ignore[arg-type]
    turn = GameUpdateEvents()
    turn.new_turn = True
    EventStream.put_nowait(turn)
    EventStream.put_nowait(GameUpdateEvents().update_flight_position(flight, (2, 0)))  # type: ignore[arg-type]
    sent = _drain()
    assert [e.new_turn for e in sent] == [False, True, False]


def test_merge_keeps_the_latest_glide() -> None:
    first = GameUpdateEvents()
    later = GameUpdateEvents()
    later.glide = True
    assert first.merge(later).glide
