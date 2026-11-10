from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from dcs.mapping import Point
from dcs.task import AttackGroup, WeaponType

from game.ato import FlightType
from game.missiongenerator.aircraft.aircraftbehavior import AircraftBehavior
from game.missiongenerator.aircraft.defendedtarget import target_area_defended
from game.missiongenerator.aircraft.waypoints.baiingress import BaiIngressBuilder
from game.theater import TheaterGroundObject
from game.utils import nautical_miles

CANNON = WeaponType.Cannon.value


def _tgo(x: float, has_aa: bool, threat_nm: float = 0) -> MagicMock:
    tgo = MagicMock(spec=TheaterGroundObject)
    tgo.position = Point(x, 0, None)  # type: ignore[arg-type]
    tgo.has_aa = has_aa
    tgo.max_threat_range.return_value = nautical_miles(threat_nm)
    group = MagicMock()
    group.group_name = "target-group"
    tgo.groups = [group]
    return tgo


def _flight(target: Any, enemy_tgos: list[Any], enabled: bool = True) -> MagicMock:
    flight = MagicMock()
    flight.client_count = 0
    flight.package.target = target
    game = flight.coalition.game
    game.settings.ai_avoid_gun_runs_in_defended_areas = enabled
    control_point = MagicMock()
    control_point.ground_objects = enemy_tgos
    game.theater.control_points_for.return_value = [control_point]
    return flight


def test_undefended_target() -> None:
    target = _tgo(0, has_aa=False)
    far_sam = _tgo(nautical_miles(30).meters, has_aa=True, threat_nm=20)
    assert not target_area_defended(_flight(target, [target, far_sam]))


def test_target_with_its_own_aa_is_defended() -> None:
    target = _tgo(0, has_aa=True, threat_nm=1)
    assert target_area_defended(_flight(target, [target]))


def test_short_range_aaa_near_target_counts() -> None:
    # 2nm AAA is below the 3nm floor of the coalition threat zones, but a gun run
    # flies straight through it.
    target = _tgo(0, has_aa=False)
    aaa = _tgo(nautical_miles(2.5).meters, has_aa=True, threat_nm=2)
    assert target_area_defended(_flight(target, [target, aaa]))


def test_sam_covering_target_counts() -> None:
    target = _tgo(0, has_aa=False)
    sam = _tgo(nautical_miles(15).meters, has_aa=True, threat_nm=20)
    assert target_area_defended(_flight(target, [target, sam]))


def test_setting_disables_check() -> None:
    target = _tgo(0, has_aa=True, threat_nm=1)
    assert not target_area_defended(_flight(target, [target], enabled=False))


def _bai_tasks(defended: bool) -> list[AttackGroup]:
    builder: Any = object.__new__(BaiIngressBuilder)
    builder.register_special_ingress_points = MagicMock()
    builder.flight = MagicMock()
    builder.flight.is_helo = False
    builder.package = MagicMock()
    builder.package.target = _tgo(0, has_aa=defended)
    miz_group = MagicMock()
    miz_group.id = 7
    builder.mission = MagicMock()
    builder.mission.find_group.return_value = miz_group
    waypoint = MagicMock()
    waypoint.tasks = []
    waypoint.alt = 4000
    with patch(
        "game.missiongenerator.aircraft.waypoints.baiingress.target_area_defended",
        return_value=defended,
    ):
        builder.add_tasks(waypoint)
    return [t for t in waypoint.tasks if isinstance(t, AttackGroup)]


def test_bai_on_undefended_target_uses_auto_weapons() -> None:
    attacks = _bai_tasks(defended=False)
    assert [a.params["weaponType"] for a in attacks] == [WeaponType.Auto.value]


def test_bai_on_defended_target_never_uses_gun() -> None:
    attacks = _bai_tasks(defended=True)
    assert len(attacks) == 2
    for attack in attacks:
        assert attack.params["weaponType"] & CANNON == 0
        assert attack.params["groupId"] == 7
    guided, unguided = attacks
    # Guided weapons are released from ingress altitude, not from a dive.
    assert guided.params["altitudeEnabled"] and guided.params["altitude"] == 4000
    # A single unguided pass, then on to egress.
    assert unguided.params["attackQtyLimit"] and unguided.params["attackQty"] == 1


@pytest.mark.parametrize(
    "task,clients,defended,expected",
    [
        (FlightType.BAI, 0, True, True),
        (FlightType.STRIKE, 0, True, True),
        (FlightType.BAI, 0, False, False),
        (FlightType.BAI, 1, True, False),
        (FlightType.CAS, 0, True, False),
    ],
)
def test_must_avoid_gun_runs(
    task: FlightType, clients: int, defended: bool, expected: bool
) -> None:
    behavior = AircraftBehavior(task, MagicMock())
    flight = MagicMock()
    flight.client_count = clients
    with patch(
        "game.missiongenerator.aircraft.aircraftbehavior.target_area_defended",
        return_value=defended,
    ):
        assert behavior.must_avoid_gun_runs(flight) is expected
