"""The debrief that follows the plan (F16): key packages first, with goal,
result and losses; routine lines summed."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.commander.jfacc.briefing import plan_debrief

TOT = datetime(2026, 6, 1, 12, 0)
BLUE = SimpleNamespace(is_blue=True)


def _package(task: FlightType, target: Any, minutes: int = 0, count: int = 4) -> Any:
    package = SimpleNamespace(
        target=target,
        time_over_target=TOT + timedelta(minutes=minutes),
        has_players=False,
        planning_info={"reason": f"{task.value} on {target.name}"},
        primary_task=task,
        flights=[],
    )
    flight = SimpleNamespace(
        flight_type=task,
        count=count,
        package=package,
        squadron=SimpleNamespace(player=BLUE),
        alert=False,
    )
    package.flights.append(flight)
    return package


def _debriefing(packages: list[Any], **kwargs: Any) -> Any:
    game = SimpleNamespace(
        blue=SimpleNamespace(ato=SimpleNamespace(packages=packages)),
        red=SimpleNamespace(ato=SimpleNamespace(packages=[])),
    )
    data: dict[str, Any] = dict(
        game=game,
        flights_flown=[],
        air_losses=SimpleNamespace(player=[], enemy=[]),
        combat_credits=[],
        ground_losses=SimpleNamespace(enemy_ground_objects=[], player_ground_objects=[]),
        simulated=False,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _name(package: Any) -> str:
    return f"{package.primary_task.value} {package.target.name}"


def test_key_packages_report_goal_result_and_losses(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    sam = SimpleNamespace(name="SA-11 site", is_dead=True)
    dead = _package(FlightType.DEAD, sam)
    cap = _package(FlightType.BARCAP, SimpleNamespace(name="Station"), count=2)
    hit = SimpleNamespace(theater_unit=SimpleNamespace(ground_object=sam))
    loss = SimpleNamespace(flight=dead.flights[0])
    debriefing = _debriefing(
        [cap, dead],
        air_losses=SimpleNamespace(player=[loss], enemy=[]),
        ground_losses=SimpleNamespace(
            enemy_ground_objects=[hit, hit], player_ground_objects=[]
        ),
    )
    result = plan_debrief(debriefing, name_of=_name)
    assert [r.name for r in result.key] == ["DEAD SA-11 site"]
    key = result.key[0]
    assert key.goal == "DEAD on SA-11 site"
    assert key.result == "target destroyed, 1 of 4 aircraft lost"
    assert result.routine == ["1 CAP station: no losses"]


def test_simulated_turn_reports_unflown_packages(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    strike = _package(FlightType.STRIKE, SimpleNamespace(name="Bridge", is_dead=False))
    flown = _package(FlightType.CAS, SimpleNamespace(name="Front"), minutes=10)
    credit = SimpleNamespace(flight=flown.flights[0], kind="cas_kill")
    debriefing = _debriefing(
        [strike, flown],
        simulated=True,
        flights_flown=[flown.flights[0]],
        combat_credits=[credit, credit],
    )
    results = {r.name: r.result for r in plan_debrief(debriefing, name_of=_name).key}
    assert results["Strike Bridge"] == "not flown"
    assert results["CAS Front"] == "2 successful attacks, all aircraft back"


def test_finished_packages_removed_from_the_ato_are_still_reported(
    monkeypatch: Any,
) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    gone = _package(FlightType.SWEEP, SimpleNamespace(name="Sukhumi"))
    credit = SimpleNamespace(flight=gone.flights[0], kind="air_kill")
    debriefing = _debriefing(
        [], simulated=True, flights_flown=[gone.flights[0]], combat_credits=[credit]
    )
    key = plan_debrief(debriefing, name_of=_name).key
    assert [r.result for r in key] == ["1 air kill, all aircraft back"]
