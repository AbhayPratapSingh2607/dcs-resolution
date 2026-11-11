"""FAC(A) (V3): which flights can be FAC(A), when one is on station, the
planner's marking and the combat model's bonus."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.task import AFAC, CAS

from game.ato.flighttype import FlightType
from game.commander.jfacc import faca
from game.commander.jfacc.planner import JfaccPlanner
from game.sim.combat.model.attack import AttackRun
from game.sim.combat.model.profiles import Guidance


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def distance_to_point(self, other: "_Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


def _flight(tasks: list[Any], fac: bool = False, **kw: Any) -> Any:
    flight = SimpleNamespace(
        unit_type=SimpleNamespace(
            dcs_unit_type=SimpleNamespace(tasks=tasks), display_name="A-10C"
        ),
        flight_type=FlightType.CAS,
        **kw,
    )
    if fac:
        flight.fac_a = True
    return flight


def test_only_types_with_the_afac_task_become_fac() -> None:
    capable = _flight([CAS, AFAC])
    other = _flight([CAS])
    assert faca.mark_fac(capable) and faca.is_fac(capable)
    assert not faca.mark_fac(other) and not faca.is_fac(other)


def test_fac_on_station_needs_a_live_airborne_fac_over_the_same_target(
    monkeypatch: Any,
) -> None:
    import game.sim.combat.model.engine as engine

    monkeypatch.setattr(
        engine, "distance_km", lambda a, b: a.distance_to_point(b) / 1000
    )
    front = SimpleNamespace(position=_Point(0, 0))
    other_front = SimpleNamespace(position=_Point(0, 0))

    def make(target: Any, x: float, alive: bool = True, airborne: bool = True) -> Any:
        state = SimpleNamespace(
            in_flight=airborne, estimate_position=lambda: _Point(x, 0)
        )
        return _flight(
            [CAS, AFAC],
            fac=True,
            alive=alive,
            state=state,
            package=SimpleNamespace(target=target),
        )

    def game(*flights: Any) -> Any:
        packages = [SimpleNamespace(flights=[f]) for f in flights]
        return SimpleNamespace(
            coalition_for=lambda p: SimpleNamespace(
                ato=SimpleNamespace(packages=packages)
            )
        )

    assert faca.fac_on_station(game(make(front, 10_000)), None, front)  # type: ignore[arg-type]
    assert not faca.fac_on_station(game(make(front, 80_000)), None, front)  # type: ignore[arg-type]
    assert not faca.fac_on_station(game(make(front, 0, alive=False)), None, front)  # type: ignore[arg-type]
    assert not faca.fac_on_station(game(make(front, 0, airborne=False)), None, front)  # type: ignore[arg-type]
    assert not faca.fac_on_station(game(make(other_front, 0)), None, front)  # type: ignore[arg-type]


def test_planner_marks_the_second_cas_element() -> None:
    lead = _flight([CAS, AFAC])
    fac = _flight([CAS, AFAC])
    escort = SimpleNamespace(flight_type=FlightType.SEAD_ESCORT)
    package = SimpleNamespace(
        flights=[lead, fac, escort], planning_rationale="", planning_info={}
    )
    JfaccPlanner._mark_fac_a(SimpleNamespace(package=package))  # type: ignore[arg-type]
    assert faca.is_fac(fac) and not faca.is_fac(lead)
    assert "FAC(A)" in package.planning_rationale
    # Only one CAS element placed: nobody is the FAC(A).
    alone = _flight([CAS, AFAC])
    single = SimpleNamespace(flights=[alone], planning_rationale="", planning_info={})
    JfaccPlanner._mark_fac_a(SimpleNamespace(package=single))  # type: ignore[arg-type]
    assert not faca.is_fac(alone)


def test_a_fac_on_station_designates_for_laser_weapons() -> None:
    run = object.__new__(AttackRun)
    env = SimpleNamespace(laser_factor=lambda altitude: 1.0)
    run.model = SimpleNamespace(env=env, airframes=lambda f: [], iter_package_airframes=lambda f, km: iter(()))  # type: ignore[attr-defined]
    run.flight = SimpleNamespace()  # type: ignore[attr-defined]
    airframe = SimpleNamespace(has_tgp=False)
    run._fac = False  # type: ignore[attr-defined]
    alone = run._guidance_factor(airframe, Guidance.LASER, 3000, None)  # type: ignore[arg-type]
    run._fac = True  # type: ignore[attr-defined]
    talked_on = run._guidance_factor(airframe, Guidance.LASER, 3000, None)  # type: ignore[arg-type]
    assert alone == 0.3 and talked_on == 1.0
