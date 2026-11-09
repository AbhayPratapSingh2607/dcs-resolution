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
