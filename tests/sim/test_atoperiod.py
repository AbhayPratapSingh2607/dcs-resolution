"""The 6 hour ATO period and the DCS window (game.sim.atoperiod)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from game.commander.jfacc.campaignstate import AirCampaignState
from game.sim import atoperiod

START = datetime(2020, 6, 1, 6, 0)


class _Plan:
    def __init__(self, startup: datetime, land: datetime) -> None:
        self._startup = startup
        self.landing_time = land

    def startup_time(self) -> datetime:
        return self._startup


class _BrokenPlan:
    def startup_time(self) -> datetime:
        raise RuntimeError("no plan")


def _package(*windows: tuple[int, int], players: bool = False) -> SimpleNamespace:
    flights = [
        SimpleNamespace(
            flight_plan=_Plan(
                START + timedelta(minutes=a), START + timedelta(minutes=b)
            )
        )
        for a, b in windows
    ]
    return SimpleNamespace(flights=flights, has_players=players)


def _game(*packages: SimpleNamespace) -> SimpleNamespace:
    state = AirCampaignState()
    state.note_period(1, START, START + timedelta(hours=6))
    blue = SimpleNamespace(
        ato=SimpleNamespace(packages=list(packages)),
        player=SimpleNamespace(is_blue=True),
    )
    red = SimpleNamespace(
        ato=SimpleNamespace(packages=[]), player=SimpleNamespace(is_blue=False)
    )
    settings = SimpleNamespace(desired_player_mission_duration=timedelta(minutes=60))
    return SimpleNamespace(
        turn=1, air_campaign=state, blue=blue, red=red, settings=settings
    )


def test_package_span_covers_all_flights() -> None:
    package = _package((10, 100), (5, 90), (20, 140))
    first, last = atoperiod.package_span(package)  # type: ignore[arg-type]
    assert first == START + timedelta(minutes=5)
    assert last == START + timedelta(minutes=140)


def test_package_span_skips_flights_without_plan() -> None:
    package = _package((10, 100))
    package.flights.append(SimpleNamespace(flight_plan=_BrokenPlan()))
    assert atoperiod.package_span(package) == (  # type: ignore[arg-type]
        START + timedelta(minutes=10),
        START + timedelta(minutes=100),
    )
    assert atoperiod.package_span(SimpleNamespace(flights=[])) == (None, None)  # type: ignore[arg-type]


def test_window_offset_is_clamped() -> None:
    game = _game()
    assert atoperiod.max_window_offset_min(game) == 300  # type: ignore[arg-type]
    atoperiod.set_window_offset(game, 10_000)  # type: ignore[arg-type]
    assert game.air_campaign.window_offset_min == 300
    start, end = atoperiod.window(game)  # type: ignore[arg-type,misc]
    assert start == START + timedelta(hours=5)
    assert end == START + timedelta(hours=6)


def test_defer_and_restore_packages_after_window() -> None:
    early = _package((0, 60))
    straddling = _package((30, 150))
    late = _package((200, 300))
    late_players = _package((200, 300), players=True)
    game = _game(early, straddling, late, late_players)
    atoperiod.set_window_offset(game, 60)  # type: ignore[arg-type]
    in_window = atoperiod.packages_in_window(game)  # type: ignore[arg-type]
    assert straddling in in_window and early not in in_window
    assert atoperiod.defer_after_window(game) == 1  # type: ignore[arg-type]
    assert late not in game.blue.ato.packages
    # Player packages are always flown.
    assert late_players in game.blue.ato.packages
    assert atoperiod.has_deferred(game)  # type: ignore[arg-type]
    assert atoperiod.restore_deferred(game) == [late]  # type: ignore[arg-type]
    assert late in game.blue.ato.packages
    assert not atoperiod.has_deferred(game)  # type: ignore[arg-type]
