"""The fight goes on after you quit (P6): the quit time from the state file
and which packages the combat model carries on with."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.commander.jfacc.campaignstate import AirCampaignState
from game.debriefing import StateData
from game.sim import atoperiod
from game.unitmap import UnitMap

START = datetime(2020, 6, 1, 6, 0)


class _Plan:
    def __init__(self, startup: datetime, land: datetime) -> None:
        self._startup = startup
        self.landing_time = land

    def startup_time(self) -> datetime:
        return self._startup


def _flight(startup_min: int, land_min: int, count: int = 2) -> Any:
    return SimpleNamespace(
        count=count,
        client_count=0,
        flight_plan=_Plan(START + timedelta(minutes=startup_min), START + timedelta(minutes=land_min)),
    )


def _package(*flights: Any, players: bool = False) -> Any:
    return SimpleNamespace(flights=list(flights), has_players=players)


def _game(blue: list[Any], red: list[Any] | None = None, offset: int = 120) -> Any:
    state = AirCampaignState()
    state.note_period(1, START, START + timedelta(hours=6))
    state.window_offset_min = offset
    return SimpleNamespace(
        turn=1,
        air_campaign=state,
        blue=SimpleNamespace(ato=SimpleNamespace(packages=blue), player=SimpleNamespace(is_blue=True)),
        red=SimpleNamespace(ato=SimpleNamespace(packages=red or []), player=SimpleNamespace(is_blue=False)),
        settings=SimpleNamespace(desired_player_mission_duration=timedelta(minutes=60)),
    )


def _debriefing(elapsed: float | None, losses: list[Any] | None = None) -> Any:
    return SimpleNamespace(
        state_data=SimpleNamespace(elapsed_seconds=elapsed),
        air_losses=SimpleNamespace(losses=list(losses or [])),
    )


def test_state_file_carries_the_elapsed_mission_time() -> None:
    data = StateData.from_json({"mission_ended": True, "elapsed_seconds": 1234.5}, UnitMap())
    assert data.elapsed_seconds == 1234.5
    # Older plugins, or a malformed value: unknown.
    assert StateData.from_json({"mission_ended": True}, UnitMap()).elapsed_seconds is None
    assert StateData.from_json({"elapsed_seconds": "soon"}, UnitMap()).elapsed_seconds is None


def test_quit_time_is_the_window_start_plus_the_elapsed_time() -> None:
    game = _game([])
    # Window 08:00-09:00.
    assert atoperiod.quit_time(game, _debriefing(20 * 60)) == START + timedelta(hours=2, minutes=20)  # type: ignore[arg-type]
    # No elapsed time (a crash): flown to the end of the window.
    assert atoperiod.quit_time(game, _debriefing(None)) == START + timedelta(hours=3)  # type: ignore[arg-type]
    assert atoperiod.quit_time(game, None) == START + timedelta(hours=3)  # type: ignore[arg-type]
    # Never past the window: later flights are held back and fought from its end.
    assert atoperiod.quit_time(game, _debriefing(5 * 3600)) == START + timedelta(hours=3)  # type: ignore[arg-type]


def test_unfinished_packages_are_the_ones_still_flying_at_the_quit() -> None:
    landed = _package(_flight(100, 135))
    flying = _package(_flight(110, 170))
    not_yet = _package(_flight(150, 230))
    yours = _package(_flight(120, 180), players=True)
    shot_down = _package(_flight(115, 175, count=2))
    red_flying = _package(_flight(100, 160))
    game = _game([landed, flying, not_yet, yours, shot_down], [red_flying])
    losses = [SimpleNamespace(flight=shot_down.flights[0])] * 2
    when = START + timedelta(hours=2, minutes=20)
    found = atoperiod.unfinished_packages(game, _debriefing(20 * 60, losses), when)  # type: ignore[arg-type]
    assert found == [flying, not_yet, red_flying]


def test_nothing_to_resolve_without_a_window() -> None:
    game = _game([])
    game.air_campaign.period_turn = -1
    assert atoperiod.resolve_remainder(game, SimpleNamespace(), None) is None  # type: ignore[arg-type]
