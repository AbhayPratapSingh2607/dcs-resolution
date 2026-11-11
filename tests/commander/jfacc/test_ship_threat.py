"""Air defense ships count in the route threat: a warship carries its radars
and missiles on one hull, so it is its own TELAR."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs import ships, vehicles

from game.commander.jfacc.intelview import _group_radar_reach, _ship_reach
from game.utils import nautical_miles


def _unit(unit_type: Any, reach_nm: float, uid: int = 1) -> Any:
    return SimpleNamespace(
        id=uid,
        type=unit_type,
        alive=True,
        is_anti_air=True,
        threat_range=nautical_miles(reach_nm),
    )


def test_a_frigate_has_radar_reach() -> None:
    group = SimpleNamespace(units=[_unit(ships.REZKY, 8.6)])
    assert _ship_reach(group, set()) > 15_000
    assert _group_radar_reach(group, set()) > 15_000


def test_a_ship_believed_sunk_has_none() -> None:
    group = SimpleNamespace(units=[_unit(ships.REZKY, 8.6, uid=7)])
    assert _group_radar_reach(group, {7}) == 0


def test_land_guns_are_not_ships() -> None:
    group = SimpleNamespace(units=[_unit(vehicles.AirDefence.ZSU_23_4_Shilka, 1.5)])
    assert _ship_reach(group, set()) == 0
