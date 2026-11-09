"""Mobile SAM sites relocating between turns (game/commander/jfacc/iads.py)."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.mapping import Point

from game.commander.jfacc import iads
from game.commander.jfacc.campaignstate import SideCampaign
from game.commander.jfacc.iads import MoveRules, SiteMover, shift_site
from game.commander.jfacc.observations import ObservationLog
from game.data.groups import GroupTask
from game.theater import Player
from game.warfare.intel import Contact


def _pt(x: float, y: float) -> Point:
    return Point(x, y, None)  # type: ignore[arg-type]


class _Cp:
    def __init__(self, name: str, x: float, y: float, owner: Player) -> None:
        self.id = name
        self.name = name
        self.position = _pt(x, y)
        self.captured = owner
        self.is_fleet = False


def _site(name: str, x: float, y: float, cp: _Cp, reach_m: float = 30_000) -> Any:
    units = [SimpleNamespace(position=_pt(x + dx, y + dy)) for dx, dy in ((0, 0), (80, 40), (-60, 90))]
    return SimpleNamespace(
        id=name,
        name=name,
        task=GroupTask.MERAD,
        position=_pt(x, y),
        units=units,
        control_point=cp,
        max_threat_range=lambda: SimpleNamespace(meters=reach_m),
    )


class _Theater:
    """Red owns everything north of x = 0, blue south of it; the sea is
    east of y = 60 km."""

    def __init__(self, cps: list[_Cp], front: Point) -> None:
        self.cps = cps
        self.front = front
        self.farp_terrain = None

    def control_points_for(self, player: Player) -> list[_Cp]:
        return [cp for cp in self.cps if cp.captured == player]

    def conflicts(self) -> list[Any]:
        return [SimpleNamespace(position=self.front)]

    def closest_control_point(self, point: Point) -> _Cp:
        return min(self.cps, key=lambda cp: cp.position.distance_to_point(point))

    def is_on_land(self, point: Point) -> bool:
        return point.y < 60_000


@pytest.fixture
def world(monkeypatch: Any) -> Any:
    red_base = _Cp("Maykop", 100_000, 0, Player.RED)
    blue_base = _Cp("Kutaisi", -100_000, 0, Player.BLUE)
    sites = [_site("sa11", 70_000, 10_000, red_base), _site("sa6", 120_000, -30_000, red_base)]
    monkeypatch.setattr(iads, "_radar_sams", lambda game, player: sites)
    contact = Contact("sa11")  # type: ignore[arg-type]
    contact.offset_x, contact.offset_y = 400.0, -300.0  # 400 m east, 300 m south
    war_state = SimpleNamespace(
        intel={True: SimpleNamespace(contacts={"sa11": contact})},
        deception={"sa11": [(2000.0, 1000.0)]},
    )
    game = SimpleNamespace(
        turn=5,
        theater=_Theater([red_base, blue_base], _pt(0, 0)),
        war_state=war_state,
    )
    return SimpleNamespace(game=game, sites=sites, red_base=red_base, contact=contact)


def _absolute(site: Any, offset: tuple[float, float]) -> tuple[float, float]:
    east, north = offset
    return site.position.x + north, site.position.y + east


def test_shift_keeps_the_enemy_contact_and_decoys_in_place(world: Any) -> None:
    site = world.sites[0]
    seen_before = world.contact.estimated_position(site)
    decoy_before = _absolute(site, world.game.war_state.deception["sa11"][0])
    shift_site(world.game, site, dx=8000, dy=-3000)
    assert (site.position.x, site.position.y) == (78_000, 7_000)
    assert (site.units[1].position.x, site.units[1].position.y) == (78_080, 7_040)
    seen_after = world.contact.estimated_position(site)
    assert seen_after.x == pytest.approx(seen_before.x)
    assert seen_after.y == pytest.approx(seen_before.y)
    decoy_after = _absolute(site, world.game.war_state.deception["sa11"][0])
    assert decoy_after == pytest.approx(decoy_before)


def _mover(world: Any, side: SideCampaign, **rules: float) -> SiteMover:
    return SiteMover(world.game, Player.RED, side, MoveRules(**rules))  # type: ignore[arg-type]


def test_hunted_site_moves_to_valid_ground(world: Any) -> None:
    side = SideCampaign()
    side.attacked = {"sa11": 2.0}
    moves = _mover(world, side, move_share=0.5).run()
    assert [m.tgo_id for m in moves] == ["sa11"]
    site = world.sites[0]
    assert moves[0].reason == "relocating away from enemy attacks"
    # Still red ground, behind the front, on land, within road range.
    assert site.position.x > 15_000
    assert all(u.position.y < 60_000 for u in site.units)
    assert 3 <= moves[0].distance_km <= 25 / 1.3 + 0.01


def test_site_that_fired_only_scoots(world: Any) -> None:
    side = SideCampaign()
    side.fired_sites = {"sa11": 4}
    moves = _mover(world, side, move_share=0.5).run()
    assert moves[0].reason == "shoot and scoot"
    assert moves[0].distance_km <= 6 / 1.3 + 0.01


def test_quiet_site_stays_without_a_reason(world: Any) -> None:
    assert _mover(world, SideCampaign(), move_share=1.0).run() == []
    assert world.sites[0].position.x == 70_000


def test_site_moves_toward_the_observed_axis(world: Any) -> None:
    side = SideCampaign()
    log = ObservationLog(side)
    base = world.red_base
    for _ in range(12):
        # Blue comes in from the west (heading 270) at Maykop.
        log.add_point([base], base.position.x, base.position.y - 80_000, 1.0)
    site = world.sites[1]
    # sa6 sits just east of Maykop, on the wrong side of the base.
    shift_site(world.game, site, base.position.x - site.position.x, 8_000 - site.position.y)
    moves = _mover(world, side, move_share=1.0).run()
    moved = {m.tgo_id: m for m in moves}
    assert "sa6" in moved
    assert moved["sa6"].reason == "covering the observed threat axis"
    # Now west of the base, toward the observed axis.
    assert site.position.y < base.position.y


def test_moves_respect_the_share(world: Any) -> None:
    side = SideCampaign()
    side.attacked = {"sa11": 2.0, "sa6": 2.0}
    moves = _mover(world, side, move_share=0.3).run()
    assert len(moves) == 1
    assert moves[0].tgo_id == "sa11"  # listed first; equal urgency


def test_western_profile_has_no_moves() -> None:
    from game.commander.jfacc.profile import load_profile

    western = load_profile("western")
    soviet = load_profile("soviet")
    assert western is not None and soviet is not None
    assert not western.section("iads").get("moves")
    rules = MoveRules.from_profile(soviet.section("iads")["moves"])
    assert rules.move_share == pytest.approx(0.35)
    assert rules.road_move_km == pytest.approx(25)  # inherited from russian_modern


def test_decoys_go_toward_the_threat_axis(world: Any) -> None:
    import random

    from game.commander.jfacc.iads import near_decoys, planned_decoy_offset

    side = SideCampaign()
    log = ObservationLog(side)
    base = world.red_base
    for _ in range(12):
        # Blue comes from the south (heading 180) at Maykop.
        log.add_point([base], base.position.x - 80_000, base.position.y, 1.0)
    site = world.sites[0]
    rng = random.Random(3)
    offsets = [planned_decoy_offset(world.game, site, side, rng) for _ in range(20)]
    assert all(o is not None for o in offsets)
    norths = [north for _, north in offsets]  # type: ignore[misc]
    assert sum(1 for n in norths if n < 0) >= 15  # mostly south of the site
    assert all(1500 <= math.hypot(e, n) <= 5000 for e, n in offsets)  # type: ignore[misc]
    assert near_decoys(offsets) == 20  # type: ignore[arg-type]


def test_moved_site_gets_fresh_decoys(world: Any) -> None:
    from game.commander.jfacc.iads import near_decoys

    site = world.sites[0]
    shift_site(world.game, site, dx=15_000, dy=0)
    # The old decoy stayed behind, 15 km away now.
    assert near_decoys(world.game.war_state.deception["sa11"]) == 0
