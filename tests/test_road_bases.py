"""Road bases (game.warfare.roadbases): squadrons on a cratered airfield fly part
of their aircraft from road strips, and those flights start in the air."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

import pytest

from game import opening
from game.ato.flighttype import FlightType
from game.ato.starttype import StartType
from game.opening import OpeningPlan, SalvoShot, Surprise
from game.theater.controlpoint import RunwayStatus
from game.theater.player import Player
from game.warfare import roadbases


def _game(surprise: Surprise = Surprise.PARTIAL, turn: int = 1, on: bool = True) -> Any:
    return SimpleNamespace(
        turn=turn,
        opening=OpeningPlan(begun=True, surprise=surprise),
        settings=SimpleNamespace(strategic_surprise=surprise, road_base_operations=on),
    )


def _squadron(
    game: Any,
    untasked: int = 10,
    helicopter: bool = False,
    task: FlightType = FlightType.STRIKE,
    variant: str = "Su-24M",
    player: Player = Player.RED,
) -> Any:
    location = SimpleNamespace(coalition=SimpleNamespace(game=game))
    return SimpleNamespace(
        location=location,
        untasked_aircraft=untasked,
        aircraft=SimpleNamespace(helicopter=helicopter, variant_id=variant),
        primary_task=task,
        player=player,
    )


def test_red_road_share_follows_the_surprise_and_grows() -> None:
    expected = roadbases.road_share(_game(Surprise.NONE), Player.RED)
    caught = roadbases.road_share(_game(Surprise.FULL), Player.RED)
    assert expected > caught
    later = roadbases.road_share(_game(Surprise.FULL, turn=3), Player.RED)
    assert caught < later <= roadbases.ORGANISED_SHARE
    assert roadbases.road_share(_game(Surprise.FULL), Player.BLUE) == 0.0


def test_blue_airfields_are_never_road_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    from game.theater.controlpoint import Airfield

    game = _game(Surprise.NONE)

    class _Field(Airfield):
        def __init__(self, owner: Player) -> None:
            self._owner = owner

        @property
        def captured(self) -> Player:  # type: ignore[override]
            return self._owner

        @property
        def coalition(self) -> Any:  # type: ignore[override]
            return SimpleNamespace(game=game)

        def runway_is_operational(self) -> bool:
            return False

    assert roadbases.is_road_base(_Field(Player.RED))
    assert not roadbases.is_road_base(_Field(Player.BLUE))


def test_road_capacity_on_a_cratered_field(monkeypatch: pytest.MonkeyPatch) -> None:
    game = _game(Surprise.NONE)
    monkeypatch.setattr(roadbases, "is_road_base", lambda cp: True)
    assert roadbases.road_capacity(_squadron(game, 10)) == 5
    # Helicopters don't need the runway; bombers and tankers can't use a road.
    assert roadbases.road_capacity(_squadron(game, 6, helicopter=True)) == 6
    assert roadbases.road_capacity(_squadron(game, 4, variant="Tu-160")) == 0
    assert roadbases.road_capacity(_squadron(game, 4, task=FlightType.REFUELING)) == 0

    monkeypatch.setattr(roadbases, "is_road_base", lambda cp: False)
    assert roadbases.road_capacity(_squadron(game, 10)) is None


def test_road_base_flights_start_in_the_air(monkeypatch: pytest.MonkeyPatch) -> None:
    flight = SimpleNamespace(
        squadron=SimpleNamespace(location=object()),
        start_type=StartType.COLD,
        from_road_base=False,
    )
    monkeypatch.setattr(roadbases, "is_road_base", lambda cp: True)
    assert roadbases.mark_road_base_flight(flight)  # type: ignore[arg-type]
    assert flight.from_road_base and flight.start_type is StartType.IN_FLIGHT

    monkeypatch.setattr(roadbases, "is_road_base", lambda cp: False)
    assert not roadbases.mark_road_base_flight(flight)  # type: ignore[arg-type]
    assert not flight.from_road_base


def test_sortie_ledger_caps_road_base_squadrons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime

    from game.commander.jfacc import sorties

    monkeypatch.setattr(roadbases, "road_capacity", lambda squadron: 3)
    profile = SimpleNamespace(mc_rate=1.0, max_sorties_per_airframe=2)
    ledger = sorties.SortieLedger(
        profile, datetime(2020, 1, 1), datetime(2020, 1, 1, 6), 1  # type: ignore[arg-type]
    )

    class Squadron:
        untasked_aircraft = 12
        name = "1st"
        aircraft = SimpleNamespace(variant_id="Su-24M")

    squadron = Squadron()
    assert ledger.mission_capable(squadron) == 3  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "surprise,closed_turns",
    [(Surprise.NONE, 1), (Surprise.PARTIAL, 2), (Surprise.FULL, 4)],
)
def test_salvo_runway_repair_follows_the_surprise(
    surprise: Surprise, closed_turns: int
) -> None:
    game = _game(surprise)
    status = RunwayStatus()
    cp = SimpleNamespace(runway_status=status, captured=Player.RED, squadrons=[])
    shot = SalvoShot("Krymsk", "airfield", 4, 2, 0, 0)
    opening._hit_airfield(game, cp, 2, shot, random.Random(1))  # type: ignore[arg-type]
    assert shot.runway_cut and status.damaged
    # Turn 0 ends right after Begin Campaign, then the turns are played.
    status.process_turn()
    open_turn = None
    for turn in range(1, 8):
        if not status.damaged:
            open_turn = turn
            break
        status.process_turn()
    assert open_turn == closed_turns + 1


def test_reaction_lines_follow_the_surprise() -> None:
    cut = [SalvoShot("Krymsk", "airfield", 4, 2, 1, 1, runway_cut=True)]
    ready = " ".join(opening.reaction_lines(_game(Surprise.NONE), cut))
    caught = " ".join(opening.reaction_lines(_game(Surprise.FULL), cut))
    assert "next turn" in ready and "counter-strike" in ready
    assert "4 turns" in caught and "counter-strike" not in caught


def test_no_counter_strike_expected_with_fire_missions_off() -> None:
    cut = [SalvoShot("Krymsk", "airfield", 4, 2, 1, 1, runway_cut=True)]
    game = _game(Surprise.NONE)
    game.settings.fire_missions = False
    assert "counter-strike" not in " ".join(opening.reaction_lines(game, cut))
