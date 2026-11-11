"""A CAP station just outside a known SAM envelope isn't risk-free.

The CAP orbits for hours, turns and chases near the edge, and the site's
believed position can be off, so sites within a margin of the station count
at reduced weight (item 7: blue CAPs estimated 0% and lost 2-4% per sortie).
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from shapely.geometry import LineString

import game.commander.jfacc.assessment as assessment
import game.commander.jfacc.intelview as intelview
import game.commander.jfacc.threat as threat_module
import game.warfare.intel as intel
from game.commander.jfacc.threat import STATION_MARGIN_DEPTH, RouteThreat
from game.data.groups import GroupTask
from game.theater.theatergroundobject import SamGroundObject

NM = 1852.0
REACH = 20 * NM


def _site(x: float) -> SamGroundObject:
    site = SamGroundObject.__new__(SamGroundObject)
    object.__setattr__(site, "task", GroupTask.LORAD)
    site.__dict__["_test_position"] = SimpleNamespace(x=x, y=0.0)
    return site


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> SamGroundObject:
    tgo = _site(0.0)
    monkeypatch.setattr(
        SamGroundObject,
        "position",
        property(lambda s: s.__dict__["_test_position"]),
        raising=False,
    )
    monkeypatch.setattr(assessment, "enemy_tgos", lambda game, player: [tgo])
    monkeypatch.setattr(
        intelview, "believed_radar_reach_m", lambda game, player, t: REACH
    )
    monkeypatch.setattr(threat_module, "sam_weight", lambda t, live: 3.0)
    monkeypatch.setattr(intel, "is_mobile", lambda t: False)
    return tgo


def _exposure(station_x_nm: float, margin_nm: float) -> RouteThreat:
    game = cast(Any, SimpleNamespace(settings=SimpleNamespace(max_threat_range=100)))
    threat = RouteThreat()
    x = station_x_nm * NM
    route = LineString([(x, -10 * NM), (x, 10 * NM)])
    target = cast(Any, SimpleNamespace(position=SimpleNamespace(x=x, y=0.0)))
    threat_module._add_sam_exposure(
        game,
        cast(Any, None),
        threat,
        route,
        target,
        None,
        {},
        None,
        None,
        margin_nm * NM,
    )
    return threat


def test_station_outside_the_envelope_is_free_without_a_margin(site: Any) -> None:
    assert _exposure(25, 0).sam_weight == 0


def test_station_within_the_margin_counts_at_reduced_weight(site: Any) -> None:
    threat = _exposure(25, 15)
    expected = 3.0 * STATION_MARGIN_DEPTH * (1 - 5 / 15)
    assert threat.sam_weight == pytest.approx(expected)
    assert not threat.target_defended


def test_station_beyond_the_margin_is_free(site: Any) -> None:
    assert _exposure(40, 15).sam_weight == 0


def test_station_inside_the_envelope_is_unchanged_by_the_margin(site: Any) -> None:
    inside = _exposure(10, 15)
    assert inside.sam_weight == pytest.approx(_exposure(10, 0).sam_weight)
    assert inside.target_defended


def test_station_risk_is_a_fraction_of_a_strike_through_the_same_sams() -> None:
    from game.commander.jfacc.risk import estimate

    threat = RouteThreat(sam_weight=14.0, target_defended=True)
    strike = estimate(threat, 0, 0, 0, False)
    cap = estimate(threat, 0, 0, 2, False, station=True)
    # Iran 2015 (SAM crews below baseline): CAPs crossing SAM weight ~14
    # lost 2-4.3% per sortie. With baseline crews it's a little more.
    # An unescorted strike presses through the overlapping sites (quadratic
    # in the weight); the CAP turns away at the edge (linear).
    assert strike.sam_component > 5 * cap.sam_component
