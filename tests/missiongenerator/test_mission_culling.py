"""Culling of what the player would never meet: parked untasked aircraft at
bases far from the mission, missile sites that don't fire, and the culling
zones recomputed for what is left in the mission once the bubble holds the
rest back."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from game.missiongenerator.aircraft.aircraftgenerator import AircraftGenerator
from game.missiongenerator.tgogenerator import MissileSiteGenerator
from game.theater.player import Player


def _aircraft_generator(culled: bool, client_slots: bool = False) -> Any:
    gen: Any = object.__new__(AircraftGenerator)
    gen.game = SimpleNamespace(
        position_culled=lambda pos: culled,
        settings=SimpleNamespace(untasked_opfor_client_slots=client_slots),
    )
    return gen


def _base(red: bool = True) -> Any:
    return SimpleNamespace(
        position=object(), captured=Player.RED if red else Player.BLUE
    )


def test_ramp_of_a_far_base_is_culled() -> None:
    base = _base()
    assert _aircraft_generator(culled=True)._ramp_culled(base, set())
    assert not _aircraft_generator(culled=False)._ramp_culled(base, set())


def test_the_players_base_and_red_client_slots_are_kept() -> None:
    base = _base()
    assert not _aircraft_generator(culled=True)._ramp_culled(base, {id(base)})
    gen = _aircraft_generator(culled=True, client_slots=True)
    assert not gen._ramp_culled(base, set())
    assert gen._ramp_culled(_base(red=False), set())


def _missile_site(fire: bool, culled: bool) -> Any:
    gen: Any = object.__new__(MissileSiteGenerator)
    gen.ground_object = SimpleNamespace(position=object())
    gen.game = MagicMock()
    gen.game.settings.generate_fire_tasks_for_missile_sites = fire
    gen.game.position_culled.return_value = culled
    return gen


def test_missile_sites_are_culled_unless_they_fire() -> None:
    assert _missile_site(fire=False, culled=True).culled
    assert not _missile_site(fire=False, culled=False).culled
    assert not _missile_site(fire=True, culled=True).culled
