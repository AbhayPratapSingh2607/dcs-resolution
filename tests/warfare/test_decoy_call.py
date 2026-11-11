"""The decoy call: before the mission, a package sent against a decoyed site
gets one roll to see through the decoy, and DCS follows it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from dcs.mapping import Point
from dcs.task import AttackGroup, Bombing, OptFormation
from dcs.terrain import PersianGulf

from game.ato.flighttype import FlightType
from game.missiongenerator.aircraft.waypoints.pydcswaypointbuilder import (
    PydcsWaypointBuilder,
)
from game.warfare.deception import (
    SPOT_MAX,
    SPOT_RANGE_M,
    DecoyCall,
    see_through_chance,
)

TERRAIN = PersianGulf()


def _package(*types: FlightType) -> Any:
    return SimpleNamespace(flights=[SimpleNamespace(flight_type=t) for t in types])


def _site(x: float = 0.0, y: float = 0.0) -> Any:
    return SimpleNamespace(position=Point(x, y, TERRAIN))


def test_no_chance_when_the_real_site_is_far_from_the_decoy() -> None:
    chance, reasons = see_through_chance(
        _package(FlightType.DEAD, FlightType.SEAD_ESCORT),
        SimpleNamespace(isr=0.9),
        _site(),
        Point(SPOT_RANGE_M + 1000, 0, TERRAIN),
    )
    assert chance == 0.0
    assert "km from the decoy" in reasons[0]


def test_a_sead_element_and_a_close_site_help() -> None:
    picture = SimpleNamespace(isr=0.6)
    near = Point(3000, 0, TERRAIN)
    far = Point(15000, 0, TERRAIN)
    alone, _ = see_through_chance(_package(FlightType.DEAD), picture, _site(), near)
    sead, reasons = see_through_chance(
        _package(FlightType.DEAD, FlightType.SEAD_ESCORT), picture, _site(), near
    )
    distant, _ = see_through_chance(
        _package(FlightType.DEAD, FlightType.SEAD_ESCORT), picture, _site(), far
    )
    assert 0 < alone < sead <= SPOT_MAX
    assert distant < sead
    assert "ELINT from the SEAD element" in reasons


def _builder(call: Any, client_count: int = 0) -> Any:
    builder: Any = object.__new__(PydcsWaypointBuilder)
    builder.package = MagicMock()
    builder.package.decoy_call = call
    builder.package.target.name = "SHOEBILL"
    builder.flight = MagicMock()
    builder.flight.flight_type = FlightType.DEAD
    builder.flight.client_count = client_count
    builder.mission = SimpleNamespace(terrain=TERRAIN)
    return builder


def _waypoint() -> Any:
    waypoint = MagicMock()
    waypoint.tasks = [OptFormation.finger_four_open(), AttackGroup(9), AttackGroup(9)]
    return waypoint


def _call(spotted: bool) -> DecoyCall:
    return DecoyCall(MagicMock(), 1, 113001.0, 37882.0, 0.46, spotted, [])


def test_an_ai_flight_that_took_the_decoy_bombs_it() -> None:
    waypoint = _waypoint()
    assert _builder(_call(spotted=False)).redirect_to_decoy(waypoint)
    attacks = [t for t in waypoint.tasks if isinstance(t, (AttackGroup, Bombing))]
    assert len(attacks) == 1 and isinstance(attacks[0], Bombing)
    assert round(attacks[0].params["x"]) == 113001
    assert round(attacks[0].params["y"]) == 37882
    # Non-attack tasks stay.
    assert any(isinstance(t, OptFormation) for t in waypoint.tasks)


def test_a_flight_that_saw_through_it_attacks_the_real_site() -> None:
    waypoint = _waypoint()
    assert not _builder(_call(spotted=True)).redirect_to_decoy(waypoint)
    assert sum(isinstance(t, AttackGroup) for t in waypoint.tasks) == 2


def test_players_make_their_own_call() -> None:
    waypoint = _waypoint()
    assert not _builder(_call(spotted=False), client_count=1).redirect_to_decoy(
        waypoint
    )
    assert sum(isinstance(t, AttackGroup) for t in waypoint.tasks) == 2


def test_the_debrief_reports_the_call() -> None:
    from game.commander.jfacc.briefing import _decoy_note

    package = SimpleNamespace(decoy_call=_call(spotted=False), has_players=False)
    assert "took a decoy" in _decoy_note(package)  # type: ignore[arg-type]
    package.decoy_call = _call(spotted=True)
    assert "saw through a decoy" in _decoy_note(package)  # type: ignore[arg-type]
    package.has_players = True
    assert _decoy_note(package) == ""  # type: ignore[arg-type]
