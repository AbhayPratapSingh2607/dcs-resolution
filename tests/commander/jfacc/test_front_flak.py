"""Ground fire over the front in the CAS risk estimate (casestimate._front_flak):
helicopters and low deliveries take the full exposure, stand-off weapons keep
the aircraft out of most of it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.commander.jfacc.casestimate import _front_flak
from game.data.weapons import WeaponGroup
from game.theater.player import Player


def _front(units: int) -> Any:
    from game.dcs.groundunittype import GroundUnitType

    from dcs import vehicles

    unit = next(GroundUnitType.for_dcs_type(vehicles.Armor.BTR_80))
    red_cp = SimpleNamespace(
        base=SimpleNamespace(armor={unit: units}, total_armor=units),
        connected_points=[],
        captured=Player.RED,
        frontline_unit_count_limit=units,
    )
    return SimpleNamespace(red_cp=red_cp, blue_cp=SimpleNamespace())


def _weapons(group: str) -> list[Any]:
    return list(WeaponGroup.named(group).weapons)[:1]


def _game() -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(combat_model_lethality=1.0),
        coalition_for=lambda player: SimpleNamespace(
            faction=SimpleNamespace(name="Iraq 1991")
        ),
    )


def test_helicopter_rockets_are_far_more_exposed_than_standoff_jets() -> None:
    front = _front(40)
    helo = _front_flak(
        _game(),
        front,
        Player.BLUE,
        True,
        _weapons("LAU-131 7xMPP APKWS"),
    )
    jet = _front_flak(_game(), front, Player.BLUE, False, _weapons("AGM-65D"))
    assert helo > 3 * jet > 0


def test_no_enemy_at_the_front_no_ground_fire() -> None:
    assert _front_flak(_game(), _front(0), Player.BLUE, True, []) == 0.0
