"""Fire missions (game.warfare.firemissions): launchers and their capacity, the
commander's plan, resolution in the combat model, and the DCS hand-over."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.mapping import Point
from dcs.terrain import Caucasus

from game.opening import OpeningPlan, Surprise
from game.sim.simulationresults import SimulationResults
from game.theater.player import Player
from game.warfare import firemissions as fm

TERRAIN = Caucasus()
START = datetime(2004, 1, 7, 19, 0)


class Unit:
    def __init__(self, name: str = "unit") -> None:
        self.name = name
        self.alive = True
        self.unit_type = None

    def kill(self, events: Any) -> None:
        self.alive = False

    def revive(self, events: Any) -> None:
        self.alive = True


def _target(units: int = 3, x: float = 50_000) -> Any:
    return SimpleNamespace(
        id=f"tgo-{x}",
        name=f"SITE {x:.0f}",
        position=Point(x, 0, TERRAIN),
        units=[Unit() for _ in range(units)],
        is_dead=False,
        sea_object=False,
        control_point=SimpleNamespace(name="Sochi-Adler"),
    )


def _launcher(
    kind: fm.LauncherKind = fm.LauncherKind.SHIP, capacity: int = 8
) -> fm.Launcher:
    return fm.Launcher(
        key="group:0001 | SHIP",
        kind=kind,
        name="SHIP",
        position=Point(0, 0, TERRAIN),
        range_m=1_000_000,
        capacity=capacity,
        weapon="Tomahawk",
        player=Player.BLUE,
        group_name="0001 | SHIP",
    )


def _game(turn: int = 2, surprise: Surprise = Surprise.PARTIAL) -> Any:
    return SimpleNamespace(
        turn=turn,
        settings=SimpleNamespace(
            fire_missions=True,
            strategic_surprise=surprise,
            desired_player_mission_duration=timedelta(hours=1),
        ),
        opening=OpeningPlan(begun=True, surprise=surprise),
        conditions=SimpleNamespace(start_time=START),
    )


def test_capacity_is_shared_by_the_turns_missions() -> None:
    game = _game()
    launcher = _launcher(capacity=8)
    target = _target()
    first = fm.plan_mission(game, launcher, target, 6, START)
    assert fm.rounds_left(game, launcher) == 2
    # More than is left is capped.
    second = fm.plan_mission(game, launcher, target, 6, START)
    assert second.rounds == 2 and fm.rounds_left(game, launcher) == 0
    fm.remove_mission(game, first)
    assert fm.rounds_left(game, launcher) == 6
    # Next turn the launcher fires again; old missions are dropped.
    game.turn = 3
    fm.drop_old_missions(game)
    assert fm.missions_this_turn(game) == []
    assert fm.rounds_left(game, launcher) == 8


def test_rounds_for_the_target() -> None:
    from game.theater import ControlPoint

    ship = _launcher()
    assert fm.rounds_for(ship, _target(units=1)) == 2
    assert fm.rounds_for(ship, _target(units=6)) == 4
    scud = _launcher(fm.LauncherKind.MISSILE)
    assert fm.rounds_for(scud, _target()) == 1
    guns = _launcher(fm.LauncherKind.ARTILLERY, capacity=20)
    assert fm.rounds_for(guns, _target()) == 20


def test_artillery_reach_from_its_firing_position() -> None:
    # MLRS (32 km) sits 17 km back; a 22 km howitzer with the tanks.
    assert fm.artillery_reach(32_000) == 15_000
    assert fm.artillery_reach(22_000) == 19_000
    assert fm.artillery_reach(2_000) == 0


def _resolving(
    monkeypatch: pytest.MonkeyPatch, game: Any, target: Any, launcher: fm.Launcher
) -> None:
    monkeypatch.setattr(fm, "launcher_by_key", lambda g, p, key: launcher)
    monkeypatch.setattr(fm, "target_of", lambda g, m: target)
    monkeypatch.setattr(fm, "_air_defense", lambda g, t, p: 1.0)


def test_the_combat_model_fires_due_missions_and_can_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game()
    launcher = _launcher()
    target = _target(units=4)
    _resolving(monkeypatch, game, target, launcher)
    early = fm.plan_mission(game, launcher, target, 4, START + timedelta(minutes=10))
    late = fm.plan_mission(game, launcher, target, 4, START + timedelta(hours=3))
    results = SimulationResults(seed=3)
    sim = fm.FireMissionSimulation(game, results)  # type: ignore[arg-type]
    sim.tick(START + timedelta(minutes=30), None)  # type: ignore[arg-type]
    assert early.status is fm.FireStatus.FIRED and late.status is fm.FireStatus.PLANNED
    killed = [u for u in target.units if not u.alive]
    assert killed and results.ground_losses == killed
    assert "fired 4 Tomahawk" in results.log.entries[-1].text
    # Aborting the mission resets the turn: the units live and it is planned again.
    results.revert(None)  # type: ignore[arg-type]
    assert all(u.alive for u in target.units)
    assert early.status is fm.FireStatus.PLANNED


def test_missions_in_dcs_are_left_to_dcs_unless_the_player_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game()
    launcher = _launcher()
    target = _target(units=4)
    _resolving(monkeypatch, game, target, launcher)
    in_dcs = fm.plan_mission(game, launcher, target, 2, START + timedelta(minutes=10))
    after_quit = fm.plan_mission(
        game, launcher, target, 2, START + timedelta(minutes=50)
    )
    in_dcs.status = after_quit.status = fm.FireStatus.IN_MISSION
    sim = fm.FireMissionSimulation(game, SimulationResults())  # type: ignore[arg-type]
    sim.tick(START + timedelta(hours=1), None)  # type: ignore[arg-type]
    assert in_dcs.status is after_quit.status is fm.FireStatus.IN_MISSION

    committed: list[Any] = []

    class Processor:
        def __init__(self, game: Any) -> None:
            pass

        def commit_resolved_period(self, debriefing: Any, events: Any) -> None:
            committed.append(debriefing)

    class FakeDebriefing:
        def __init__(self, *args: Any) -> None:
            pass

        def merge_simulation_results(self, results: Any) -> None:
            self.results = results

    import importlib

    debriefing_module = importlib.import_module("game.debriefing")
    processor_module = importlib.import_module("game.sim.missionresultsprocessor")
    monkeypatch.setattr(debriefing_module, "Debriefing", FakeDebriefing)
    monkeypatch.setattr(processor_module, "MissionResultsProcessor", Processor)
    done = fm.resolve_pending(game, None, quit=START + timedelta(minutes=30))  # type: ignore[arg-type]
    assert done == [after_quit] and committed
    assert in_dcs.status is fm.FireStatus.FIRED
    assert in_dcs.result == "fired in the DCS mission"
    assert after_quit.status is fm.FireStatus.FIRED


def test_a_mission_whose_launcher_is_gone_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game()
    target = _target()
    mission = fm.plan_mission(game, _launcher(), target, 2, START)
    monkeypatch.setattr(fm, "launcher_by_key", lambda g, p, key: None)
    monkeypatch.setattr(fm, "target_of", lambda g, m: target)
    fm.resolve(game, mission, SimulationResults(), None, random.Random(1))  # type: ignore[arg-type]
    assert mission.status is fm.FireStatus.CANCELLED
    assert "launcher is gone" in mission.result


@pytest.mark.parametrize(
    "surprise,fires",
    [(Surprise.NONE, True), (Surprise.PARTIAL, True), (Surprise.FULL, False)],
)
def test_red_counter_strike_on_turn_1_follows_the_surprise(
    monkeypatch: pytest.MonkeyPatch, surprise: Surprise, fires: bool
) -> None:
    game = _game(turn=1, surprise=surprise)
    launcher = fm.Launcher(
        key="group:0002 | SCUD",
        kind=fm.LauncherKind.MISSILE,
        name="SCUD",
        position=Point(0, 0, TERRAIN),
        range_m=300_000,
        capacity=4,
        weapon="Scud",
        player=Player.RED,
    )
    monkeypatch.setattr(fm, "launchers", lambda g, p: [launcher])
    monkeypatch.setattr(
        fm,
        "targets_for",
        lambda g, l: [(10_000.0 * i, _target(x=10_000 * i)) for i in range(1, 6)],
    )
    monkeypatch.setattr(
        fm, "period_bounds", lambda g: (START, START + timedelta(hours=6))
    )
    planned = fm.plan_ai_fire_missions(game, Player.RED)  # type: ignore[arg-type]
    assert bool(planned) is fires
    if surprise is Surprise.NONE:
        assert sum(m.rounds for m in planned) == 4
    elif surprise is Surprise.PARTIAL:
        assert sum(m.rounds for m in planned) == 2
    assert all(m.auto and not m.player_blue for m in planned)
    assert all(START <= m.time <= START + timedelta(hours=6) for m in planned)


def test_no_fire_missions_on_turn_0_or_when_off() -> None:
    game = _game(turn=0)
    assert fm.plan_ai_fire_missions(game, Player.RED) == []  # type: ignore[arg-type]
    game = _game()
    game.settings.fire_missions = False
    assert fm.plan_ai_fire_missions(game, Player.RED) == []  # type: ignore[arg-type]


def test_old_saves_get_a_fire_plan() -> None:
    game = SimpleNamespace()
    assert fm.fire_plan_of(game).missions == []  # type: ignore[arg-type]
    plan = fm.FirePlan.__new__(fm.FirePlan)
    plan.__setstate__({})
    assert plan.missions == []
