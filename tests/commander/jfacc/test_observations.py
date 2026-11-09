"""Learned threat axes from a side's own observations
(game/commander/jfacc/observations.py) and their use in the DCA layout."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.mapping import Point

from game.commander.jfacc import dca
from game.commander.jfacc.campaignstate import AirCampaignState, SideCampaign
from game.commander.jfacc.observations import (
    DECAY,
    Observation,
    ObservationLog,
    heading_deg,
    record_turn,
)
from game.theater import Player


def _cp(name: str, x: float, y: float) -> Any:
    return SimpleNamespace(
        id=name, name=name, position=Point(x, y, None), is_fleet=False  # type: ignore[arg-type]
    )


def _towards(cp: Any, heading: float, distance: float) -> tuple[float, float]:
    r = math.radians(heading)
    return cp.position.x + distance * math.cos(r), cp.position.y + distance * math.sin(r)


def test_heading_matches_dcs_convention() -> None:
    origin = Point(0, 0, None)  # type: ignore[arg-type]
    assert heading_deg(origin, 10, 0) == pytest.approx(0)  # north
    assert heading_deg(origin, 0, 10) == pytest.approx(90)  # east
    assert heading_deg(origin, 0, 10) == pytest.approx(
        origin.heading_between_point(Point(0, 10, None))  # type: ignore[arg-type]
    )


def test_axes_find_the_observed_bearing() -> None:
    side = SideCampaign()
    log = ObservationLog(side)
    base = _cp("Krymsk", 0, 0)
    for _ in range(8):
        log.add_point([base], *_towards(base, 225, 80_000), weight=1.0)
    log.add_point([base], *_towards(base, 90, 80_000), weight=1.0)
    axes = log.axes(base)
    assert axes[0].heading == pytest.approx(225, abs=6)
    assert axes[0].share > 0.8
    assert log.mass(base) == pytest.approx(9)


def test_observations_attach_to_the_nearest_asset_in_range() -> None:
    side = SideCampaign()
    log = ObservationLog(side)
    near, far = _cp("near", 0, 0), _cp("far", 200_000, 0)
    log.add_point([near, far], 20_000, 30_000, 1.0)
    assert set(side.observed_axes) == {"near"}
    log.add_point([near, far], 900_000, 0, 1.0)  # out of every asset's radius
    assert set(side.observed_axes) == {"near"}


def test_history_decays_once_per_turn() -> None:
    side = SideCampaign()
    log = ObservationLog(side)
    base = _cp("b", 0, 0)
    log.start_turn(1)
    log.add_point([base], 50_000, 0, 10.0)
    log.record_attack("sam-1", 2.0)
    log.start_turn(2)
    log.start_turn(2)  # idempotent within a turn
    assert log.mass(base) == pytest.approx(10 * DECAY)
    assert log.attack_weight("sam-1") == pytest.approx(2 * DECAY)
    log.start_turn(4)
    assert log.mass(base) == pytest.approx(10 * DECAY**3)


def _game(blue_cps: list[Any], red_cps: list[Any]) -> Any:
    def control_points_for(player: Player) -> list[Any]:
        return blue_cps if player.is_blue else red_cps

    return SimpleNamespace(
        turn=3,
        air_campaign=AirCampaignState(),
        theater=SimpleNamespace(control_points_for=control_points_for),
    )


def test_record_turn_uses_only_the_viewers_own_observations() -> None:
    red_base = _cp("Maykop", 0, 0)
    blue_base = _cp("Kutaisi", -300_000, 0)
    game = _game([blue_base], [red_base])
    sam = SimpleNamespace(id="sa-11", position=Point(10_000, -60_000, None))  # type: ignore[arg-type]
    debriefing = SimpleNamespace(
        observations=[
            # Red's radars saw a blue flight south-west of Maykop, twice.
            Observation(False, 101, *_towards(red_base, 200, 90_000), aircraft=4),
            Observation(False, 101, *_towards(red_base, 205, 70_000), aircraft=4),
            # Blue's AWACS saw a red flight; not red's knowledge.
            Observation(True, 202, *_towards(red_base, 20, 60_000), aircraft=2),
        ],
        air_loss_details=[],
        ground_losses=SimpleNamespace(
            player_ground_objects=[],
            enemy_ground_objects=[SimpleNamespace(theater_unit=SimpleNamespace(ground_object=sam))],
        ),
    )
    record_turn(game, debriefing)
    red = game.air_campaign.side(False)
    assert red.enemy_sorties_seen == 4  # one flight of four, seen twice
    assert red.attacked == {"sa-11": pytest.approx(0.5)}
    log = ObservationLog(red)
    axes = log.axes(red_base)
    assert 190 <= axes[0].heading <= 215
    blue = game.air_campaign.side(True)
    assert blue.enemy_sorties_seen == 2


def test_threat_axes_add_the_learned_axis(monkeypatch: Any) -> None:
    asset = _cp("Sochi", 0, 0)
    enemy_base = _cp("Senaki", *_towards(asset, 135, 150_000))
    monkeypatch.setattr(dca, "defended_assets", lambda game, player: [asset])
    monkeypatch.setattr(
        dca, "_enemy_fighter_bases", lambda game, player: iter([(enemy_base, 10.0)])
    )
    side = SideCampaign()
    log = ObservationLog(side)
    for _ in range(10):
        # The enemy comes in over the sea, far from the geometric axis.
        log.add_point([asset], *_towards(asset, 250, 100_000), weight=1.0)

    plain = dca.threat_axes(None, Player.RED, 200, 30, 3)  # type: ignore[arg-type]
    assert [round(a.heading) for a in plain] == [135]
    learned = dca.threat_axes(
        None, Player.RED, 200, 30, 3, learned=log, learned_weight=0.8  # type: ignore[arg-type]
    )
    headings = sorted(round(a.heading) for a in learned)
    assert headings[0] == 135
    assert 240 <= headings[1] <= 260
    observed = [a for a in learned if dca.OBSERVED in a.source_names]
    assert observed and observed[0].strength < learned[0].strength + 1e-9
    # Without the weight nothing is learned.
    assert len(dca.threat_axes(None, Player.RED, 200, 30, 3, learned=log)) == 1  # type: ignore[arg-type]
