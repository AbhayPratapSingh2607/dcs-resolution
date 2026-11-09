"""An air engagement in which nobody fired must not restart every tick.

A CAP whose commit region holds an enemy it can't catch (an AWACS turning
away, a CAP out of reach) used to start a new empty engagement each tick:
135 of 362 engagements in one fast-forwarded turn.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from game.sim.combat.aircombat import AirCombat
from game.sim.combat.combatinitiator import CombatInitiator
from game.sim.combat.model.engine import QUIET_ENGAGEMENT_COOLDOWN, CombatModel
from game.theater import Player

NOW = datetime(2026, 1, 1, 12, 0)


def _flight(blue: bool) -> Any:
    state = SimpleNamespace(
        in_flight=True,
        is_at_ip=False,
        avoid_further_combat=False,
        vulnerable_to_intercept=True,
        vulnerable_to_sam=False,
        estimate_position=lambda: None,
        a2a_commit_region=lambda: None,
    )
    return SimpleNamespace(
        squadron=SimpleNamespace(player=Player.BLUE if blue else Player.RED),
        state=state,
    )


def _model() -> CombatModel:
    model = CombatModel.__new__(CombatModel)
    model.quiet_pairs = {}
    return model


class FakeZones:
    def __init__(self, interceptors: list[Any]) -> None:
        self.interceptors = interceptors

    def covers(self, position: Any) -> bool:
        return bool(self.interceptors)

    def iter_intercepting_flights(self, position: Any) -> Any:
        return iter(self.interceptors)


class NoSams:
    def covers(self, position: Any) -> bool:
        return False


def test_quiet_pair_is_remembered_until_the_cooldown_ends() -> None:
    model = _model()
    awacs, cap = _flight(blue=False), _flight(blue=True)
    model.mark_quiet([cap, awacs], NOW)

    assert model.recently_quiet(awacs, cap, NOW + timedelta(minutes=1))
    assert model.recently_quiet(cap, awacs, NOW + timedelta(minutes=1))
    assert not model.recently_quiet(awacs, cap, NOW + QUIET_ENGAGEMENT_COOLDOWN)


def test_same_side_flights_are_not_paired() -> None:
    model = _model()
    a, b, red = _flight(True), _flight(True), _flight(False)
    model.mark_quiet([a, b, red], NOW)
    assert not model.recently_quiet(a, b, NOW)
    assert model.recently_quiet(a, red, NOW)
    assert model.recently_quiet(b, red, NOW)


def test_initiator_skips_recently_quiet_interceptors() -> None:
    model = _model()
    awacs = _flight(blue=False)
    quiet_cap, fresh_cap = _flight(blue=True), _flight(blue=True)
    model.mark_quiet([quiet_cap, awacs], NOW)
    initiator = CombatInitiator(cast(Any, None), [], cast(Any, None), model)
    quiet = initiator._quiet_filter(NOW + timedelta(seconds=30))

    # Only the quiet CAP covers the AWACS: no new engagement.
    assert (
        CombatInitiator.check_flight_for_new_combat(
            awacs, cast(Any, FakeZones([quiet_cap])), cast(Any, NoSams()), quiet
        )
        is None
    )

    # A fresh CAP still engages; the quiet one stays out.
    combat = CombatInitiator.check_flight_for_new_combat(
        awacs,
        cast(Any, FakeZones([quiet_cap, fresh_cap])),
        cast(Any, NoSams()),
        quiet,
    )
    assert isinstance(combat, AirCombat)
    assert list(combat.iter_flights()) == [awacs, fresh_cap]


def test_without_a_model_nothing_is_filtered() -> None:
    awacs, cap = _flight(blue=False), _flight(blue=True)
    initiator = CombatInitiator(cast(Any, None), [], cast(Any, None), None)
    assert initiator._quiet_filter(NOW) is None
    combat = CombatInitiator.check_flight_for_new_combat(
        awacs, cast(Any, FakeZones([cap])), cast(Any, NoSams()), None
    )
    assert isinstance(combat, AirCombat)
