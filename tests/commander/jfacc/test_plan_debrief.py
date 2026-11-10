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


def _debriefing(packages: list[Any], game: Any = None, **kwargs: Any) -> Any:
    if game is None:
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


def _windowed_game(packages: list[Any], window_offset_min: int = 120) -> Any:
    from game.commander.jfacc.campaignstate import AirCampaignState

    state = AirCampaignState()
    start = TOT - timedelta(hours=2)
    state.note_period(1, start, start + timedelta(hours=6))
    state.window_offset_min = window_offset_min
    return SimpleNamespace(
        turn=1,
        air_campaign=state,
        settings=SimpleNamespace(desired_player_mission_duration=timedelta(minutes=60)),
        blue=SimpleNamespace(ato=SimpleNamespace(packages=packages)),
        red=SimpleNamespace(ato=SimpleNamespace(packages=[])),
    )


def test_turn_is_reported_by_part_around_the_dcs_window(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    # Window 12:00-13:00 of a 10:00-16:00 period.
    before = _package(FlightType.DEAD, SimpleNamespace(name="EWR", is_dead=False), minutes=-60)
    mission = _package(FlightType.STRIKE, SimpleNamespace(name="Bridge", is_dead=False), minutes=20)
    after = _package(FlightType.BAI, SimpleNamespace(name="Convoy", is_dead=False), minutes=150)
    cap_early = _package(FlightType.BARCAP, SimpleNamespace(name="Station"), minutes=-90, count=2)
    cap_late = _package(FlightType.BARCAP, SimpleNamespace(name="Station"), minutes=200, count=2)
    game = _windowed_game([before, mission, after, cap_early, cap_late])
    # The DCS results: the strike flew (not simulated), nothing lost.
    # The combat model fought the DEAD before the window (a loss) and the
    # BAI after it (in the remainder debriefing, a success).
    loss = SimpleNamespace(flight=before.flights[0])
    remainder = _debriefing(
        [],
        game=game,
        simulated=True,
        flights_flown=[after.flights[0], cap_late.flights[0]],
        combat_credits=[SimpleNamespace(flight=after.flights[0], kind="strike_success")],
    )
    debriefing = _debriefing(
        [],
        game=game,
        flights_flown=[before.flights[0], cap_early.flights[0]],
        air_losses=SimpleNamespace(player=[loss], enemy=[]),
        remainder=remainder,
    )
    result = plan_debrief(debriefing, name_of=_name)
    assert [p.name for p in result.parts] == [
        "Before the mission",
        "The mission",
        "After the mission",
    ]
    by_part = {p.name: p for p in result.parts}
    assert [r.name for r in by_part["Before the mission"].key] == ["DEAD EWR"]
    assert by_part["Before the mission"].key[0].result == "no effect reported, 1 of 4 aircraft lost"
    assert by_part["Before the mission"].simulated
    assert by_part["Before the mission"].routine == ["1 CAP station: no losses"]
    assert [r.name for r in by_part["The mission"].key] == ["Strike Bridge"]
    assert not by_part["The mission"].simulated
    assert by_part["The mission"].key[0].flown
    assert [r.result for r in by_part["After the mission"].key] == [
        "1 successful attack, all aircraft back"
    ]
    assert by_part["After the mission"].title == "After the mission (combat model, 13:00–16:00)"
    # The flat lists still hold everything.
    assert len(result.key) == 3
    assert result.routine == ["2 CAP stations: no losses"]


def test_fast_forwarded_turn_is_one_part(monkeypatch: Any) -> None:
    import game.commander.jfacc.planner as planner

    monkeypatch.setattr(planner, "counts_toward_target", lambda p: True)
    strike = _package(FlightType.STRIKE, SimpleNamespace(name="Bridge", is_dead=False))
    game = _windowed_game([strike])
    debriefing = _debriefing([], game=game, simulated=True, flights_flown=[strike.flights[0]])
    result = plan_debrief(debriefing, name_of=_name)
    assert [p.name for p in result.parts] == ["The turn"]
    assert result.parts[0].simulated
    assert result.parts[0].key[0].flown


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
