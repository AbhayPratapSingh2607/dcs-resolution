from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from dcs.mapping import Point
from dcs.task import AttackGroup, OptRTBOnOutOfAmmo, WeaponType

from game.ato import FlightType
from game.data.units import UnitClass
from game.missiongenerator.aircraft.aircraftbehavior import (
    GROUND_ATTACK_ORDNANCE,
    AircraftBehavior,
)
from game.missiongenerator.aircraft.defendedtarget import target_area_defended
from game.missiongenerator.aircraft.waypoints.baiingress import BaiIngressBuilder
from game.theater import FrontLine, TheaterGroundObject
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
    flight.is_helo = False
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


def test_helicopters_are_exempt() -> None:
    target = _tgo(0, has_aa=True, threat_nm=1)
    flight = _flight(target, [target])
    flight.is_helo = True
    assert not target_area_defended(flight)


def _front_line(enemy_armor: dict[Any, int]) -> MagicMock:
    front_line = MagicMock(spec=FrontLine)
    front_line.position = Point(0, 0, None)  # type: ignore[arg-type]
    front_line.control_point_friendly_to.return_value.base.armor = enemy_armor
    return front_line


def _unit_type(unit_class: UnitClass) -> MagicMock:
    unit_type = MagicMock()
    unit_type.unit_class = unit_class
    return unit_type


def test_front_line_with_enemy_shorad_is_defended() -> None:
    armor = {_unit_type(UnitClass.TANK): 10, _unit_type(UnitClass.SHORAD): 2}
    assert target_area_defended(_flight(_front_line(armor), []))


def test_front_line_with_only_armor_is_undefended() -> None:
    # A depleted AAA entry (count 0) does not count.
    armor = {_unit_type(UnitClass.TANK): 10, _unit_type(UnitClass.AAA): 0}
    assert not target_area_defended(_flight(_front_line(armor), []))


@pytest.mark.parametrize("defended", [True, False])
def test_cas_winchester_and_gun(defended: bool) -> None:
    behavior = AircraftBehavior(FlightType.CAS, MagicMock())
    flight = MagicMock()
    flight.client_count = 0
    flight.unit_type.always_keeps_gun = True
    group = MagicMock()
    unit = MagicMock()
    unit.gun = 100
    group.units = [unit]
    group.points[0].tasks = []
    with patch(
        "game.missiongenerator.aircraft.aircraftbehavior.target_area_defended",
        return_value=defended,
    ):
        behavior.configure_ground_attack_behavior(
            flight, group, rtb_winchester=OptRTBOnOutOfAmmo.Values.Unguided
        )
    [rtb] = [t for t in group.points[0].tasks if isinstance(t, OptRTBOnOutOfAmmo)]
    if defended:
        assert unit.gun == 0
        # Leaves once A/G ordnance is gone, without waiting on the gun or AAMs.
        assert rtb.value == GROUND_ATTACK_ORDNANCE
        assert int(rtb.value) & CANNON == 0
        assert int(rtb.value) & WeaponType.AAM.value == 0
    else:
        assert unit.gun == 100
        assert rtb.value == OptRTBOnOutOfAmmo.Values.Unguided


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
        (FlightType.CAS, 0, True, True),
        (FlightType.ARMED_RECON, 0, True, True),
        (FlightType.OCA_AIRCRAFT, 0, True, True),
        (FlightType.DEAD, 0, True, False),
        (FlightType.SEAD, 0, True, False),
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
