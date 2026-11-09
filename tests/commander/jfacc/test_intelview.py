"""The planner sees the enemy only through its own intelligence picture
(game/commander/jfacc/intelview.py): changing the enemy's hidden true state
must not change what the planner believes."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

from dcs.vehicles import AirDefence

from game.commander.jfacc import intelview
from game.commander.jfacc.targetclass import sam_weight
from game.theater.player import Player
from game.utils import meters
from game.warfare.intel import Contact, IntelPicture


def _unit(unit_id: int, dcs_type: Any, reach_km: float) -> Any:
    return SimpleNamespace(
        id=unit_id,
        type=dcs_type,
        is_anti_air=True,
        threat_range=meters(reach_km * 1000),
        alive=True,
    )


def _site() -> Any:
    launcher = _unit(1, AirDefence.Kub_2P25_ln, 25)
    radar = _unit(2, AirDefence.Kub_1S91_str, 0)
    group = SimpleNamespace(units=[launcher, radar])
    return SimpleNamespace(
        id="site",
        groups=[group],
        units=[launcher, radar],
        task=None,
        has_live_radar_sam=True,
    )


class _WarState:
    seed = 3

    def __init__(self, picture: IntelPicture, enabled: bool = True) -> None:
        self._picture = picture
        self.enabled = enabled

    def intel_enabled(self, game: Any) -> bool:
        return self.enabled

    def picture(self, game: Any, player: Player) -> IntelPicture:
        return self._picture

    def rng(self, game: Any, salt: str) -> random.Random:
        return random.Random(f"{self.seed}:{game.turn}:{salt}")


def _game(picture: IntelPicture, squadrons: list[Any] = (), enabled: bool = True) -> Any:  # type: ignore[assignment]
    enemy = SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter(squadrons)))
    return SimpleNamespace(
        turn=4,
        war_state=_WarState(picture, enabled),
        coalition_for=lambda player: SimpleNamespace(opponent=enemy),
    )


def test_radar_killed_without_bda_is_still_believed_alive() -> None:
    site = _site()
    picture = IntelPicture()
    picture.contacts[site.id] = Contact(site.id, confidence=0.9)
    game = _game(picture)
    assert intelview.believed_live_radar_sam(game, Player.BLUE, site)
    reach = intelview.believed_radar_reach_m(game, Player.BLUE, site)
    # The tracking radar dies, but nobody saw it: the planner's view
    # doesn't change.
    site.units[1].alive = False
    site.has_live_radar_sam = False
    assert intelview.believed_radar_reach_m(game, Player.BLUE, site) == reach
    assert sam_weight(site, live=intelview.believed_live_radar_sam(game, Player.BLUE, site)) > 0
    # Once BDA reports the radar destroyed, the launcher is believed blind.
    picture.contacts[site.id].believed_dead.add(2)
    assert not intelview.believed_live_radar_sam(game, Player.BLUE, site)


def test_radar_truth_is_used_without_intel() -> None:
    site = _site()
    site.groups = [
        SimpleNamespace(max_threat_range=lambda radar_only=False: meters(0))
    ]
    game = _game(IntelPicture(), enabled=False)
    assert not intelview.believed_live_radar_sam(game, Player.BLUE, site)


def _squadron(name: str, count: int) -> Any:
    return SimpleNamespace(
        name=name,
        owned_aircraft=count,
        location=SimpleNamespace(id=f"base-{name}"),
    )


def test_aircraft_counts_are_estimates_stable_within_a_turn() -> None:
    picture = IntelPicture(isr=0.4)
    squadrons = [_squadron(f"sq{i}", 20) for i in range(12)]
    game = _game(picture, squadrons)
    first = dict((s.name, n) for s, n in intelview.enemy_squadrons(game, Player.BLUE))
    again = dict((s.name, n) for s, n in intelview.enemy_squadrons(game, Player.BLUE))
    assert first == again
    # A poor picture gets counts wrong, within the ISR spread.
    assert any(n != 20 for n in first.values())
    assert all(14 <= n <= 26 for n in first.values())
    # Good imagery of a base sharpens its estimate.
    for squadron in squadrons:
        picture.airbase_quality[squadron.location.id] = 1.0
    assert all(n == 20 for _, n in intelview.enemy_squadrons(game, Player.BLUE))


def test_aircraft_counts_are_exact_without_intel() -> None:
    squadrons = [_squadron("a", 7), _squadron("b", 0)]
    game = _game(IntelPicture(isr=0.1), squadrons, enabled=False)
    assert [(s.name, n) for s, n in intelview.enemy_squadrons(game, Player.BLUE)] == [
        ("a", 7)
    ]
