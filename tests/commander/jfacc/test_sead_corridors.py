"""SEAD corridors (item 1): HARM shooters suppress the airspace along their
route around their TOT, and a package whose ingress lies in that corridor at
its TOT doesn't need its own HARM escort."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

from dcs.mapping import Point
from dcs.terrain import Caucasus
from shapely.geometry import LineString

from game.ato.flighttype import FlightType
from game.commander.jfacc.composer import (
    FlightRequest,
    PackageComposer,
    PackageRequest,
    SeadCorridor,
)
from game.commander.jfacc.threat import RouteThreat

TOT = datetime(2026, 6, 1, 12, 30)
NM = 1852.0
TERRAIN = Caucasus()


def _point(x_nm: float, y_nm: float) -> Point:
    return Point(x_nm * NM, y_nm * NM, TERRAIN)


def _composer(origin: Point) -> Any:
    composer = cast(Any, PackageComposer.__new__(PackageComposer))
    composer.packages_cfg = {"ingress_exposure_nm": 40}
    composer.origin_for = lambda target: SimpleNamespace(position=origin)
    composer.corridors = []
    return composer


def _corridor(x0: float, x1: float, start: datetime, shooters: int = 4) -> SeadCorridor:
    line = LineString([(x0 * NM, 0.0), (x1 * NM, 0.0)])
    return SeadCorridor(
        line.buffer(12 * NM), start, start + timedelta(minutes=30), shooters
    )


def _strike(target: Point, task: FlightType = FlightType.STRIKE) -> PackageRequest:
    return PackageRequest(
        target=cast(Any, SimpleNamespace(position=target, name="T")),
        flights=[FlightRequest(task, 4), FlightRequest(FlightType.SEAD_ESCORT, 4)],
        category_name="strike",
        reason="test",
        threat=RouteThreat(sam_weight=6.0, target_defended=True),
    )


def test_ingress_inside_an_active_corridor_is_covered() -> None:
    composer = _composer(origin=_point(0, 0))
    composer.corridors.append(_corridor(0, 100, TOT - timedelta(minutes=10)))
    assert composer.corridor_cover(_strike(_point(80, 0)), TOT) == 4


def test_corridor_outside_its_time_window_doesnt_cover() -> None:
    composer = _composer(origin=_point(0, 0))
    composer.corridors.append(_corridor(0, 100, TOT + timedelta(minutes=5)))
    assert composer.corridor_cover(_strike(_point(80, 0)), TOT) == 0


def test_ingress_from_another_direction_isnt_covered() -> None:
    composer = _composer(origin=_point(80, -60))
    composer.corridors.append(_corridor(0, 100, TOT - timedelta(minutes=10)))
    assert composer.corridor_cover(_strike(_point(80, 0)), TOT) == 0


def test_shooters_add_up_to_a_cap() -> None:
    composer = _composer(origin=_point(0, 0))
    for _ in range(3):
        composer.corridors.append(_corridor(0, 100, TOT - timedelta(minutes=10)))
    assert composer.corridor_cover(_strike(_point(80, 0)), TOT) == 8


def test_suppression_packages_bring_their_own() -> None:
    composer = _composer(origin=_point(0, 0))
    composer.corridors.append(_corridor(0, 100, TOT - timedelta(minutes=10)))
    assert composer.corridor_cover(_strike(_point(80, 0), FlightType.DEAD), TOT) == 0


def _opener_planner(weights: list[float], rollback: bool = True) -> Any:
    from game.commander.jfacc.planner import JfaccPlanner
    from game.commander.jfacc.profile import load_profile
    from game.theater.theatergroundobject import SamGroundObject

    planner = cast(Any, JfaccPlanner.__new__(JfaccPlanner))
    planner.profile = load_profile("western")
    planner.player = "blue"
    sites = []
    for i, weight in enumerate(weights):
        site = SamGroundObject.__new__(SamGroundObject)
        site.__dict__.update(id=f"sam{i}", name=f"SAM {i}", _weight=weight)
        sites.append(site)
    planner.nominations = [
        SimpleNamespace(target=site, priority=1.0) for site in sites
    ]
    planner.composer = SimpleNamespace(
        rollback_allowed=rollback,
        opener_targets=set(),
        threat_for=lambda target, exclude=None: RouteThreat(
            sam_weight=target.__dict__["_weight"]
        ),
    )
    return planner


def test_dense_iads_gets_rollback_openers_on_its_lightest_sites() -> None:
    planner = _opener_planner([14.0, 11.0, 20.0, 12.5])
    planner._choose_rollback_openers()
    assert planner.composer.opener_targets == {"sam1", "sam3"}


def test_no_openers_when_the_normal_allowance_can_start_the_rollback() -> None:
    planner = _opener_planner([14.0, 6.0])
    planner._choose_rollback_openers()
    assert planner.composer.opener_targets == set()


def test_no_openers_outside_rollback_phases() -> None:
    planner = _opener_planner([14.0, 11.0], rollback=False)
    planner._choose_rollback_openers()
    assert planner.composer.opener_targets == set()


def test_openers_are_forced_when_no_sam_site_was_attacked() -> None:
    # The straight-line threat put one site inside the normal allowance, but
    # its planned route was heavier and the first pass attacked nothing.
    planner = _opener_planner([14.0, 6.0, 9.0])
    planner.suppressed = {}
    planner._choose_rollback_openers()
    assert planner._rollback_stalled()
    planner._choose_rollback_openers(force=True)
    assert planner.composer.opener_targets == {"sam1", "sam2"}
    assert not planner._rollback_stalled()


def test_no_forced_openers_once_a_sam_site_was_attacked() -> None:
    planner = _opener_planner([14.0, 6.0])
    planner.suppressed = {"sam1": TOT}
    assert not planner._rollback_stalled()
