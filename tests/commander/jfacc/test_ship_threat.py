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


def _planner(monkeypatch: Any, ship_at: tuple[float, float], reach_nm: float) -> Any:
    from dcs import Point

    from game.commander.jfacc import planner as planner_module
    from game.commander.jfacc.planner import JfaccPlanner

    ship = SimpleNamespace(
        name="FRIGATE",
        position=Point(*ship_at, None),  # type: ignore[arg-type]
        max_threat_range=lambda: nautical_miles(reach_nm),
    )
    sam = SimpleNamespace(name="SAM", position=Point(100_000, 0, None))  # type: ignore[arg-type]
    monkeypatch.setattr(planner_module, "_air_defense_ship", lambda t: t is ship)
    planner: Any = JfaccPlanner.__new__(JfaccPlanner)
    planner.nominations = [
        SimpleNamespace(target=ship, priority=0.3),
        SimpleNamespace(target=sam, priority=0.7),
    ]
    base = SimpleNamespace(position=Point(0, 0, None))  # type: ignore[arg-type]
    planner.composer = SimpleNamespace(origin_for=lambda target: base)
    return planner, ship


def test_a_ship_on_the_way_to_a_target_guards_the_route(monkeypatch: Any) -> None:
    planner, ship = _planner(monkeypatch, (50_000, 10_000), 8.6)
    assert planner._route_guard_ships() == {id(ship)}


def test_a_ship_far_from_every_route_does_not(monkeypatch: Any) -> None:
    planner, _ = _planner(monkeypatch, (50_000, 80_000), 8.6)
    assert planner._route_guard_ships() == set()
