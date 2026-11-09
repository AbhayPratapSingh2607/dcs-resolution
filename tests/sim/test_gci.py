"""GCI scrambles of ground alert fighters (game/sim/gci.py)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from dcs.mapping import Point

from game.ato.flightstate import Takeoff
from game.ato.flightstate.onalert import OnAlert
from game.sim import gci
from game.sim.gci import GciController, cluster
from game.theater import Player

NOW = datetime(2020, 6, 1, 8, 0)


def _pt(x: float, y: float) -> Point:
    return Point(x, y, None)  # type: ignore[arg-type]


class _State:
    def __init__(self, in_flight: bool) -> None:
        self.in_flight = in_flight


class _Plan:
    def __init__(self, package: Any) -> None:
        self.package = package

    def takeoff_time(self) -> datetime:
        return self.package.time_over_target - timedelta(minutes=20)

    def estimate_takeoff_time(self) -> timedelta:
        return timedelta(minutes=2)


def _flight(
    player: Player, x: float, y: float, count: int = 2, alert: bool = False
) -> Any:
    package = SimpleNamespace(
        time_over_target=NOW + timedelta(hours=5),
        target=SimpleNamespace(position=_pt(x, y)),
        alert_radius_m=80 * 1852.0,
    )
    flight = SimpleNamespace(
        squadron=SimpleNamespace(player=player, settings=None),
        alive=True,
        alert=alert,
        alert_released=False,
        count=count,
        package=package,
        position=_pt(x, y),
        unit_type=SimpleNamespace(display_name="MiG-29A"),
        departure=SimpleNamespace(name="Maykop"),
    )
    flight.flight_plan = _Plan(package)
    flight.set_state = lambda state: setattr(flight, "state", state)
    flight.state = OnAlert(flight, None) if alert else _State(in_flight=True)  # type: ignore[arg-type]
    return flight


class _Awareness:
    def __init__(self, sources: list[Any], seen: Optional[set[int]] = None) -> None:
        self.sources = sources
        self.seen = seen

    def covers(self, position: Point, altitude: float, rcs: float) -> bool:
        return self.seen is None or (position.x, position.y) in self.seen


class _Model:
    def __init__(self, awareness: dict[bool, _Awareness]) -> None:
        self._awareness = awareness
        self.logged: list[str] = []

    def awareness(self, player: Player, time: datetime) -> _Awareness:
        return self._awareness[player.is_blue]

    def airframes(self, flight: Any) -> list[Any]:
        lead = SimpleNamespace(
            position=flight.position, altitude_m=5000.0, effective_rcs=5.0
        )
        return [lead] * flight.count

    def log(self, time: datetime, domain: Any, side: str, text: str) -> None:
        self.logged.append(text)


@pytest.fixture(autouse=True)
def _limits(monkeypatch: Any) -> None:
    monkeypatch.setattr(GciController, "_max_per_raid", lambda self, blue: 2)
    monkeypatch.setattr(GciController, "_max_odds", lambda self, blue: 3.0)


def _controller(red_radar: bool = True) -> tuple[GciController, _Model]:
    model = _Model(
        {False: _Awareness(["ewr"] if red_radar else []), True: _Awareness(["awacs"])}
    )
    return GciController(None, model), model  # type: ignore[arg-type]


def test_cluster_groups_nearby_contacts() -> None:
    a, b, c = object(), object(), object()
    raids = cluster([(a, 0, 0, 4), (b, 20_000, 0, 2), (c, 200_000, 0, 2)])  # type: ignore[list-item]
    assert [r.aircraft for r in raids] == [6, 2]
    assert raids[0].flights == [a, b]


def test_raid_in_sector_scrambles_the_nearest_alerts() -> None:
    controller, model = _controller()
    near = _flight(Player.RED, 0, 0, alert=True)
    other = _flight(Player.RED, 30_000, 0, alert=True)
    far = _flight(Player.RED, 600_000, 0, alert=True)
    raid = _flight(Player.BLUE, 60_000, 10_000, count=8)
    released = controller.tick(NOW, [near, other, far, raid])
    # A raid of eight gets two pairs (the side's limit), nearest first.
    assert released == [other, near]
    for flight in released:
        assert isinstance(flight.state, Takeoff)
        assert flight.alert_released
        assert flight.flight_plan.takeoff_time() == NOW
    assert isinstance(far.state, OnAlert)
    assert len(controller.scrambles) == 2
    assert "GCI scrambles" in model.logged[0]
    # The same raid gets no more pairs on later ticks.
    assert controller.tick(NOW + timedelta(minutes=1), [far, raid]) == []


def test_small_raid_gets_one_pair() -> None:
    controller, _ = _controller()
    alerts = [_flight(Player.RED, 0, 0, alert=True) for _ in range(3)]
    pair = _flight(Player.BLUE, 50_000, 0, count=2)
    assert len(controller.tick(NOW, alerts + [pair])) == 1


def test_no_scramble_into_a_raid_beyond_the_odds() -> None:
    controller, _ = _controller()
    lone_pair = _flight(Player.RED, 0, 0, alert=True)
    sweep = _flight(Player.BLUE, 50_000, 0, count=8)
    # 8 raiders against 2 interceptors is beyond 3:1: the pair stays down.
    assert controller.tick(NOW, [lone_pair, sweep]) == []
    assert isinstance(lone_pair.state, OnAlert)
    # A second pair in the sector brings it to 2:1.
    second = _flight(Player.RED, 10_000, 0, alert=True)
    assert len(controller.tick(NOW, [lone_pair, second, sweep])) == 2


def test_no_scramble_outside_the_sector_or_without_radar() -> None:
    controller, _ = _controller()
    alert = _flight(Player.RED, 0, 0, alert=True)
    distant = _flight(Player.BLUE, 400_000, 0, count=4)
    assert controller.tick(NOW, [alert, distant]) == []

    blind, _ = _controller(red_radar=False)
    close = _flight(Player.BLUE, 20_000, 0, count=4)
    assert blind.tick(NOW, [alert, close]) == []
    assert isinstance(alert.state, OnAlert)


def test_unseen_raid_is_not_scrambled_against() -> None:
    model = _Model({False: _Awareness(["ewr"], seen=set()), True: _Awareness([])})
    controller = GciController(None, model)  # type: ignore[arg-type]
    alert = _flight(Player.RED, 0, 0, alert=True)
    low = _flight(Player.BLUE, 20_000, 0, count=4)
    assert controller.tick(NOW, [alert, low]) == []


def test_alerts_do_not_scramble_against_their_own_side() -> None:
    controller, _ = _controller()
    alert = _flight(Player.RED, 0, 0, alert=True)
    friendly = _flight(Player.RED, 20_000, 0, count=4)
    assert controller.tick(NOW, [alert, friendly]) == []


def test_alert_flights_start_on_alert_and_are_not_flown() -> None:
    from game.ato.flightstate.flightstate import FlightState

    flight = _flight(Player.RED, 0, 0, alert=True)
    flight.state = None
    FlightState.reinitialize(SimpleNamespace(flight=flight, settings=None), NOW)  # type: ignore[arg-type]
    assert isinstance(flight.state, OnAlert)
    assert gci.is_on_alert(flight)
    assert flight.state.is_waiting_for_start
