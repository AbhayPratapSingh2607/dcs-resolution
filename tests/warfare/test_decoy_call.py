"""The decoy call: before the mission, a package sent against a decoyed site
gets one roll to see through the decoy, and DCS follows it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from dcs.mapping import Point
from dcs.task import AttackGroup, Bombing, Expend, OptFormation, WeaponType
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


def _builder(call: Any, client_count: int = 0, decoy_in_mission: bool = True) -> Any:
    builder: Any = object.__new__(PydcsWaypointBuilder)
    builder.package = MagicMock()
    builder.package.decoy_call = call
    target = builder.package.target
    target.name = "SHOEBILL"
    target.position = Point(100000.0, 25000.0, TERRAIN)
    target.groups = [
        SimpleNamespace(group_name="sam"),
        SimpleNamespace(group_name="pd"),
    ]
    builder.flight = MagicMock()
    builder.flight.flight_type = FlightType.DEAD
    builder.flight.client_count = client_count
    groups = {
        "sam": SimpleNamespace(id=9, name="sam", units=[SimpleNamespace(id=91)]),
        "pd": SimpleNamespace(id=10, name="pd", units=[SimpleNamespace(id=101)]),
        "Decoy SHOEBILL 2": SimpleNamespace(id=50, name="Decoy SHOEBILL 2", units=[]),
    }
    if not decoy_in_mission:
        del groups["Decoy SHOEBILL 2"]
    builder.mission = SimpleNamespace(terrain=TERRAIN, find_group=groups.get)
    return builder


def _waypoint() -> Any:
    waypoint = MagicMock()
    waypoint.tasks = [
        OptFormation.finger_four_open(),
        AttackGroup(9, weapon_type=WeaponType.ARM, expend=Expend.All),
        AttackGroup(10, weapon_type=WeaponType.ARM, expend=Expend.All),
        AttackGroup(9, weapon_type=WeaponType.GuidedBombs),
        AttackGroup(10, weapon_type=WeaponType.GuidedBombs),
    ]
    return waypoint


def _call(spotted: bool) -> DecoyCall:
    # Decoy index 1: the decoy group "Decoy SHOEBILL 2".
    return DecoyCall(MagicMock(), 1, 113001.0, 37882.0, 0.46, spotted, [])


def test_an_ai_flight_that_took_the_decoy_attacks_the_decoy_group() -> None:
    waypoint = _waypoint()
    assert _builder(_call(spotted=False)).redirect_to_decoy(waypoint)
    attacks = [t for t in waypoint.tasks if isinstance(t, AttackGroup)]
    # Its own tasks, with the same weapons, at the decoy, once each.
    assert [t.params["groupId"] for t in attacks] == [50, 50]
    assert [t.params["weaponType"] for t in attacks] == [
        WeaponType.ARM.value,
        WeaponType.GuidedBombs.value,
    ]
    assert any(isinstance(t, OptFormation) for t in waypoint.tasks)


def test_a_point_attack_moves_to_the_decoy() -> None:
    waypoint = MagicMock()
    waypoint.tasks = [Bombing(Point(100000.0, 25000.0, TERRAIN))]
    assert _builder(_call(spotted=False)).redirect_to_decoy(waypoint)
    assert round(waypoint.tasks[0].params["x"]) == 113001
    assert round(waypoint.tasks[0].params["y"]) == 37882


def test_without_the_decoy_in_the_mission_it_attacks_the_real_site() -> None:
    waypoint = _waypoint()
    assert not _builder(_call(spotted=False), decoy_in_mission=False).redirect_to_decoy(
        waypoint
    )
    assert {
        t.params["groupId"] for t in waypoint.tasks if isinstance(t, AttackGroup)
    } == {
        9,
        10,
    }


def test_a_flight_that_saw_through_it_attacks_the_real_site() -> None:
    waypoint = _waypoint()
    assert not _builder(_call(spotted=True)).redirect_to_decoy(waypoint)
    assert sum(isinstance(t, AttackGroup) for t in waypoint.tasks) == 4


def test_players_make_their_own_call() -> None:
    waypoint = _waypoint()
    assert not _builder(_call(spotted=False), client_count=1).redirect_to_decoy(
        waypoint
    )
    assert sum(isinstance(t, AttackGroup) for t in waypoint.tasks) == 4


def test_the_debrief_reports_the_call() -> None:
    from game.commander.jfacc.briefing import _decoy_note

    package = SimpleNamespace(decoy_call=_call(spotted=False), has_players=False)
    assert "took a decoy" in _decoy_note(package)  # type: ignore[arg-type]
    package.decoy_call = _call(spotted=True)
    assert "saw through a decoy" in _decoy_note(package)  # type: ignore[arg-type]
    package.has_players = True
    assert _decoy_note(package) == ""  # type: ignore[arg-type]
