"""Bases taken in a fast-forwarded turn, where no DCS capture trigger fires."""

from types import SimpleNamespace
from typing import Any, Optional, cast
from unittest.mock import MagicMock
from uuid import uuid4

from game.ground_forces.combat_stance import CombatStance
from game.sim.missionresultsprocessor import (
    MissionResultsProcessor,
    fast_forward_captures,
)
from game.theater import Player


class FakeBase:
    def __init__(self, strength: float, armor: int) -> None:
        self.strength = strength
        self.total_armor = armor


class FakeCp:
    def __init__(
        self,
        name: str,
        owner: Player,
        strength: float = 1.0,
        armor: int = 20,
        fleet: bool = False,
    ) -> None:
        self.id = uuid4()
        self.name = name
        self.captured = owner
        self.base = FakeBase(strength, armor)
        self.is_fleet = fleet
        self.stances: dict[Any, CombatStance] = {}

    def is_friendly_to(self, other: "FakeCp") -> bool:
        return self.captured == other.captured

    def __str__(self) -> str:
        return self.name


def _game(blue: FakeCp, red: FakeCp) -> Any:
    front = SimpleNamespace(blue_cp=blue, red_cp=red)
    return SimpleNamespace(theater=SimpleNamespace(conflicts=lambda: [front]))


def _front(
    blue_strength: float = 1.0,
    blue_armor: int = 20,
    red_stance: Optional[CombatStance] = CombatStance.BREAKTHROUGH,
    red_armor: int = 20,
) -> tuple[FakeCp, FakeCp]:
    blue = FakeCp("Gudauta", Player.BLUE, blue_strength, blue_armor)
    red = FakeCp("Sochi", Player.RED, 1.0, red_armor)
    if red_stance is not None:
        red.stances[blue.id] = red_stance
    blue.stances[red.id] = CombatStance.DEFENSIVE
    return blue, red


def test_spent_undefended_base_falls_to_attacker() -> None:
    blue, red = _front(blue_strength=0.0, blue_armor=0)
    captures = fast_forward_captures(_game(blue, red))
    assert [(c.control_point, c.captured_by_player) for c in captures] == [
        (blue, Player.RED)
    ]


def test_base_with_strength_left_holds() -> None:
    """The front hasn't reached the base yet."""
    blue, red = _front(blue_strength=0.2, blue_armor=0)
    assert fast_forward_captures(_game(blue, red)) == []


def test_base_holds_while_its_armor_matches_the_attack() -> None:
    blue, red = _front(blue_strength=0.0, blue_armor=14, red_armor=20)
    assert fast_forward_captures(_game(blue, red)) == []


def test_spent_base_falls_to_a_clearly_stronger_attacker() -> None:
    """Sukhumi in a test save: front spent, 24 armor left against 36."""
    blue, red = _front(blue_strength=0.0, blue_armor=24, red_armor=36)
    captures = fast_forward_captures(_game(blue, red))
    assert [c.control_point for c in captures] == [blue]


def test_defensive_attacker_does_not_take_the_base() -> None:
    blue, red = _front(blue_strength=0.0, blue_armor=0, red_stance=CombatStance.DEFENSIVE)
    assert fast_forward_captures(_game(blue, red)) == []


def test_attacker_needs_a_force_left() -> None:
    blue, red = _front(blue_strength=0.0, blue_armor=0, red_armor=2)
    assert fast_forward_captures(_game(blue, red)) == []


def test_only_simulated_debriefings_capture() -> None:
    """DCS missions report captures from their own triggers."""
    blue, red = _front(blue_strength=0.0, blue_armor=0)
    processor = MissionResultsProcessor(cast(Any, _game(blue, red)))

    dcs = MagicMock(simulated=False, base_captures=[])
    processor.commit_fast_forward_captures(dcs)
    assert dcs.base_captures == []

    simulated = MagicMock(simulated=True, base_captures=[])
    processor.commit_fast_forward_captures(simulated)
    assert [c.control_point for c in simulated.base_captures] == [blue]

    # Not reported twice.
    processor.commit_fast_forward_captures(simulated)
    assert len(simulated.base_captures) == 1
